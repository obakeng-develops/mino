#!/usr/bin/env python3
"""Mino agent — runs on a user's server and reports container status.

Stdlib only. Talks to the Mino backend via the /api/v1/agent/beat endpoint.
"""

import argparse
import json
import logging
import os
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger("mino-agent")

# Bumped whenever the agent script changes. Reported on every beat so Mino can
# flag hosts running an out-of-date agent. The server compares it against the
# version of the script it currently serves.
AGENT_VERSION = "2026-07-26"


def run_docker_ps():
    try:
        proc = subprocess.run(
            ["docker", "ps", "-a", "--format", "{{json .}}"],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except FileNotFoundError:
        logger.error("docker not found in PATH")
        return []
    if proc.returncode != 0:
        logger.error("docker ps failed: %s", proc.stderr.strip())
        return []
    containers = []
    for line in proc.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            c = json.loads(line)
        except json.JSONDecodeError:
            continue
        state = c.get("State", "")
        health = c.get("HealthStatus", "")
        if state != "running":
            status = "down"
        elif health == "unhealthy":
            status = "degraded"
        else:
            status = "healthy"
        containers.append(
            {
                "name": c.get("Names", ""),
                "id": c.get("ID", ""),
                "image": c.get("Image", ""),
                "state": state,
                "health": health,
                "status": status,
            }
        )
    return containers


# The docker subcommand Mino may run for each whitelisted action.
_ACTION_CMD = {
    "restart_container": "restart",
    "stop_container": "stop",
    "start_container": "start",
}


def container_ip(name):
    """The container's IP on its Docker network, or None. Resolved here, at fix
    time, rather than carried in the action — a container's IP changes when it is
    recreated, so an IP decided by the backend minutes earlier can be stale."""
    try:
        proc = subprocess.run(
            [
                "docker", "inspect", "-f",
                "{{range .NetworkSettings.Networks}}{{.IPAddress}} {{end}}", name,
            ],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
    except Exception as exc:
        logger.error("docker inspect %s failed: %s", name, exc)
        return None
    if proc.returncode != 0:
        logger.warning("docker inspect %s: %s", name, proc.stderr.strip())
        return None
    ips = proc.stdout.split()
    return ips[0] if ips else None


def register_proxy_route(action):
    """Point a reverse-proxy hostname back at a running container.

    A container can be healthy while its public hostname is dead, because the
    proxy holds no route for it — so it serves no certificate and aborts the TLS
    handshake (browsers report ERR_SSL_PROTOCOL_ERROR). No restart fixes that;
    the route has to be registered again.

    ponytail: kamal-proxy only, which is what Mino's Docker hosts run. Another
    proxy means another branch here, keyed off the action.
    """
    target_name = action.get("container")
    ip = container_ip(target_name)
    if not ip:
        logger.error("no IP for %s — cannot register a proxy route to it", target_name)
        return False
    cmd = [
        "docker", "exec", action["proxy"], "kamal-proxy", "deploy", action["service"],
        "--target", f"{ip}:{action['port']}",
        "--host", action["host"],
    ]
    if action.get("tls"):
        cmd.append("--tls")
    # kamal-proxy probes the target before accepting it, and defaults that probe to
    # /up — a Rails convention. An app serving anything else never reports healthy
    # and the registration times out, so the path is configurable per service.
    if action.get("health_check_path"):
        cmd += ["--health-check-path", action["health_check_path"]]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=120, check=False)
    except Exception as exc:
        logger.error("proxy route registration failed: %s", exc)
        return False
    if proc.returncode != 0:
        logger.warning(
            "kamal-proxy deploy %s: %s", action["service"], (proc.stderr or proc.stdout).strip()
        )
        return False
    return True


def docker_action(action_name, name):
    cmd = _ACTION_CMD.get(action_name)
    if not cmd:
        logger.warning("unknown action %s for %s — skipping", action_name, name)
        return False
    try:
        proc = subprocess.run(
            ["docker", cmd, name],
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
        if proc.returncode != 0:
            logger.warning("docker %s %s: %s", cmd, name, proc.stderr.strip())
        return proc.returncode == 0
    except Exception as exc:
        logger.error("docker %s %s failed: %s", cmd, name, exc)
        return False


def run_docker_logs(name, tail=50):
    try:
        # Merge stderr into stdout: many images (nginx, postgres, most apps)
        # log to stderr, so capturing stdout alone returns nothing.
        proc = subprocess.run(
            ["docker", "logs", "--tail", str(tail), name],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=30,
            check=False,
        )
    except Exception as exc:
        logger.error("docker logs %s failed: %s", name, exc)
        return None
    if proc.returncode != 0:
        logger.warning("docker logs %s: %s", name, (proc.stdout or "").strip())
        return None
    return proc.stdout


def run_docker_exit(name):
    """Exit code + OOMKilled for a failed container — exit 137 / OOMKilled means a
    restart won't durably fix it. Returns (exit_code, oom_killed) or (None, None)."""
    try:
        proc = subprocess.run(
            ["docker", "inspect", "-f", "{{.State.ExitCode}} {{.State.OOMKilled}}", name],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
    except Exception as exc:
        logger.error("docker inspect %s failed: %s", name, exc)
        return None, None
    if proc.returncode != 0:
        return None, None
    parts = proc.stdout.strip().split()
    code = int(parts[0]) if parts and parts[0].lstrip("-").isdigit() else None
    oom = len(parts) > 1 and parts[1].lower() == "true"
    return code, oom


def send_beat(server, token, containers):
    url = f"{server.rstrip('/')}/api/v1/agent/beat"
    data = json.dumps({"containers": containers, "agent_version": AGENT_VERSION}).encode()
    req = urllib.request.Request(
        url,
        data=data,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        body = exc.read().decode()
        logger.error("beat failed %s: %s", exc.code, body)
        return None
    except Exception as exc:
        logger.error("beat failed: %s", exc)
        return None


def send_logs(server, token, lines):
    url = f"{server.rstrip('/')}/api/v1/agent/logs"
    data = json.dumps({"lines": lines}).encode()
    req = urllib.request.Request(
        url,
        data=data,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode())
    except Exception as exc:
        logger.error("log send failed: %s", exc)
        return None


def main():
    parser = argparse.ArgumentParser(description="Mino agent")
    parser.add_argument("--server", required=True, help="Mino backend URL")
    parser.add_argument("--token", required=True, help="Agent token")
    parser.add_argument("--interval", type=int, default=10, help="Heartbeat interval in seconds")
    parser.add_argument("--once", action="store_true", help="Send one beat and exit")
    args = parser.parse_args()

    logger.info("mino agent starting: server=%s interval=%ss", args.server, args.interval)

    pending_logs: set[str] = set()
    tail_proc = None
    tail_thread = None
    tail_stop = threading.Event()
    tail_lines = []
    tail_lock = threading.Lock()
    tail_container: str | None = None

    def tail_loop(container_name):
        nonlocal tail_lines
        logger.info("start tailing logs for %s", container_name)
        proc = subprocess.Popen(
            ["docker", "logs", "-f", "--since", "0s", container_name],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        nonlocal tail_proc
        tail_proc = proc
        try:
            for line in proc.stdout:
                if tail_stop.is_set():
                    break
                with tail_lock:
                    tail_lines.append(line.rstrip("\n"))
        finally:
            proc.terminate()
            try:
                proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                proc.kill()
            logger.info("stopped tailing logs for %s", container_name)

    def flush_lines():
        nonlocal tail_lines
        with tail_lock:
            batch = tail_lines
            tail_lines = []
        if batch:
            send_logs(args.server, args.token, batch)

    try:
        while True:
            containers = run_docker_ps()
            # If backend asked for logs last beat, fetch them now.
            if containers and pending_logs:
                for c in containers:
                    if c["name"] in pending_logs:
                        c["logs"] = run_docker_logs(c["name"])
                        c["exit_code"], c["oom_killed"] = run_docker_exit(c["name"])
                pending_logs.clear()

            if containers:
                response = send_beat(args.server, args.token, containers)
                if response:
                    # The backend sends approved action dicts ({"action": ...,
                    # "container": ...}); tolerate a bare name (an old restart).
                    for action in response.get("actions", response.get("restart", [])):
                        if isinstance(action, dict):
                            name = action.get("container")
                            act = action.get("action", "restart_container")
                        else:
                            name, act = action, "restart_container"
                        if not name:
                            continue
                        logger.info("running %s on %s", act, name)
                        if act == "register_proxy_route":
                            # The backend validates these before sending; check
                            # again so a malformed action logs instead of raising
                            # and killing the beat loop.
                            missing = [
                                k for k in ("proxy", "service", "host", "port")
                                if not action.get(k)
                            ]
                            if missing:
                                logger.error("proxy route action missing %s: %s", missing, action)
                                continue
                            ok = register_proxy_route(action)
                        else:
                            ok = docker_action(act, name)
                        if ok:
                            logger.info("%s ok: %s", act, name)
                        else:
                            logger.error("%s failed: %s", act, name)
                    pending_logs.update(response.get("fetch_logs", []))

                    want_tail = response.get("tail_logs", False)
                    if tail_thread and tail_container and not want_tail:
                        tail_stop.set()
                        tail_thread.join(timeout=3)
                        tail_thread = None
                        tail_container = None
                        flush_lines()
                    elif want_tail and containers:
                        target = None
                        for c in containers:
                            if c["status"] in ("down", "degraded"):
                                target = c["name"]
                                break
                        if target and target != tail_container:
                            if tail_thread:
                                tail_stop.set()
                                tail_thread.join(timeout=3)
                                tail_thread = None
                            tail_stop.clear()
                            tail_container = target
                            tail_lines = []
                            tail_thread = threading.Thread(target=tail_loop, args=(target,), daemon=True)
                            tail_thread.start()
                        elif target == tail_container:
                            flush_lines()
            if args.once:
                break
            time.sleep(args.interval)
    finally:
        tail_stop.set()
        if tail_thread:
            tail_thread.join(timeout=3)
        flush_lines()


if __name__ == "__main__":
    main()
