"""Action whitelist and container-name validation.

ponytail: only these actions may be issued by the control plane. New executors
(Kubernetes, systemd, etc.) add new actions here and implement them locally.

Every field here reaches a host as an argv element, so each one is validated
against a charset before it goes anywhere. Nothing runs through a shell, but a
value that starts with `-` would still be read as a flag by the tool we hand it
to, so leading dashes are rejected too.

Run `python3 -m app.actions` for the self-check.
"""
import logging
import re

logger = logging.getLogger("oncall.actions")

_ALLOWED_ACTIONS = {
    "restart_container",
    "stop_container",
    "start_container",
    "fetch_logs",
    "list_containers",
    # Re-register a reverse-proxy route for a hostname. The container can be
    # healthy while the public hostname is unreachable, because the proxy has no
    # route for it — nothing a restart fixes. See _validate_proxy_route.
    "register_proxy_route",
}

_CONTAINER_NAME_RE = re.compile(r"^[a-zA-Z0-9_.-]+$")
# A DNS hostname: labels of letters/digits/hyphens, dot-separated, no leading or
# trailing hyphen or dot. Deliberately stricter than the container charset (no
# underscores) — this is the name a certificate gets issued for.
_HOSTNAME_RE = re.compile(
    r"^(?!-)[a-zA-Z0-9-]{1,63}(?<!-)(\.(?!-)[a-zA-Z0-9-]{1,63}(?<!-))*$"
)
# An absolute URL path, for the proxy's health check. No query, no traversal.
_PATH_RE = re.compile(r"^/[a-zA-Z0-9/._~-]*$")


def is_allowed_action(action: dict) -> bool:
    if not isinstance(action, dict):
        return False
    name = action.get("action")
    if name not in _ALLOWED_ACTIONS:
        return False
    container = action.get("container")
    if container is not None and not _is_valid_container_name(container):
        logger.warning("disallowed container name in action: %r", action)
        return False
    if name == "register_proxy_route" and not _validate_proxy_route(action):
        return False
    return True


def _validate_proxy_route(action: dict) -> bool:
    """A proxy-route registration names the proxy container, the app container to
    point at, its port, the public hostname, and the proxy's service name."""
    container = action.get("container")
    if not _is_valid_container_name(container):
        logger.warning("proxy route action without a valid target container: %r", action)
        return False
    if not _is_valid_container_name(action.get("proxy")):
        logger.warning("proxy route action without a valid proxy container: %r", action)
        return False
    if not _is_valid_container_name(action.get("service")):
        logger.warning("proxy route action without a valid service name: %r", action)
        return False
    if not _is_valid_hostname(action.get("host")):
        logger.warning("proxy route action without a valid hostname: %r", action)
        return False
    port = action.get("port")
    # bool is an int subclass; True would otherwise pass as port 1.
    if isinstance(port, bool) or not isinstance(port, int) or not 1 <= port <= 65535:
        logger.warning("proxy route action without a valid port: %r", action)
        return False
    if not isinstance(action.get("tls", False), bool):
        logger.warning("proxy route action with a non-boolean tls flag: %r", action)
        return False
    # Optional: the path the proxy probes before it accepts the new target.
    # kamal-proxy defaults to /up (a Rails convention); an app that serves
    # something else never becomes "healthy" and the registration times out.
    path = action.get("health_check_path")
    if path is not None and not _is_valid_path(path):
        logger.warning("proxy route action with an invalid health check path: %r", action)
        return False
    return True


def _is_valid_container_name(name) -> bool:
    return (
        isinstance(name, str)
        and not name.startswith("-")
        and bool(_CONTAINER_NAME_RE.fullmatch(name))
    )


def _is_valid_hostname(name) -> bool:
    return isinstance(name, str) and len(name) <= 253 and bool(_HOSTNAME_RE.fullmatch(name))


def _is_valid_path(path) -> bool:
    return (
        isinstance(path, str)
        and ".." not in path
        and len(path) <= 2048
        and bool(_PATH_RE.fullmatch(path))
    )


def _self_check():
    good = {
        "action": "register_proxy_route",
        "proxy": "kamal-proxy",
        "service": "caready-backend-web",
        "container": "caready-backend-web-latest",
        "host": "api.careadyhealth.com",
        "port": 8000,
        "tls": True,
    }
    assert is_allowed_action(good)
    assert is_allowed_action({"action": "restart_container", "container": "web-1"})
    assert not is_allowed_action({"action": "rm_container", "container": "web-1"})
    assert not is_allowed_action({"action": "restart_container", "container": "web 1; rm -rf /"})
    # A value that would be read as a flag by the tool it is handed to.
    assert not is_allowed_action({"action": "restart_container", "container": "--force"})
    for field, bad in [
        ("proxy", "--force"),
        ("service", "not a name"),
        ("host", "-api.example.com"),
        ("host", "api example.com"),
        ("host", "api.example.com/../x"),
        ("port", 0),
        ("port", 70000),
        ("port", "8000"),
        ("port", True),
        ("tls", "yes"),
        ("health_check_path", "up"),  # must be absolute
        ("health_check_path", "/up?x=1"),
        ("health_check_path", "/../etc/passwd"),
        ("health_check_path", "/up /down"),
        ("health_check_path", 8000),
    ]:
        assert not is_allowed_action({**good, field: bad}), f"{field}={bad!r} should be rejected"
    for path in ("/", "/health", "/up", "/api/v1/health-check_1.json"):
        assert is_allowed_action({**good, "health_check_path": path}), path
    for field in ("proxy", "service", "container", "host", "port"):
        assert not is_allowed_action({k: v for k, v in good.items() if k != field}), (
            f"missing {field} should be rejected"
        )
    # tls is the one optional field; absent means plain HTTP.
    assert is_allowed_action({k: v for k, v in good.items() if k != "tls"})
    print("actions self-check ok")


if __name__ == "__main__":
    _self_check()
