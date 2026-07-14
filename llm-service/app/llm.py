import json
import logging

import httpx

from app.config import get_settings
from app.crypto import decrypt

logger = logging.getLogger("llm.diagnose")

BASE_URLS = {
    "deepseek": "https://api.deepseek.com",
    # OpenRouter speaks the OpenAI chat-completions API; diagnose() appends
    # /v1/chat/completions, giving https://openrouter.ai/api/v1/chat/completions.
    "openrouter": "https://openrouter.ai/api",
}


def _headers(api_key: str) -> dict:
    return {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }


# Per-platform remediation context. A service's `method` is its executor type:
# `agent`/`docker` run as Docker containers Mino can restart; `url` is an
# endpoint it can only alert on. Add a case here when an executor for a new
# platform (e.g. kubernetes) actually exists, so the model is told what Mino
# can and cannot do for that kind of service.
def _platform_guidance(method: str) -> str:
    if method == "url":
        return (
            "This service is an HTTP endpoint. Mino monitors it but CANNOT restart "
            "or change it; it can only alert a human. Your FIX must be something a "
            "person should check or do, not a command Mino can run."
        )
    if method == "fly":
        return (
            "This service is a Fly.io Machine. Mino can run exactly one of, through the "
            "Machines API: a `restart` (bounce it — the usual fix), a `stop` (halt one that "
            "is crash-looping or thrashing), or a `start` (bring up one that was stopped). If "
            "none of these will help, say a human is needed and what to check. Do NOT suggest "
            "flyctl, SSH, cloud consoles, or any tool Mino does not have."
        )
    return (
        "This service runs as a Docker container. Mino can run exactly one of: "
        "`docker restart` (bounce it — the usual fix), `docker stop` (stop a container "
        "that is crash-looping or thrashing the host, to stop the bleeding), or "
        "`docker start` (start one that was cleanly stopped). If none of these will help, "
        "say a human is needed and what to check. If the container was OOM-killed or exited "
        "137, a restart will NOT durably fix it — it will hit the same limit again; choose "
        "ACTION none and tell the person to raise the memory limit or fix the leak. Do NOT "
        "suggest kubectl, systemd, cloud consoles, or any tool Mino does not have."
    )


def _system_prompt(method: str) -> str:
    return (
        "You diagnose why a monitored service failed. Reason only from the logs and "
        "metadata below; if they don't show a clear cause, say so and keep confidence low. "
        "Give the single most likely root cause, then pick the one action (if any) that will fix it. "
        + _platform_guidance(method)
        + " Be concise. Respond with exactly four lines in this format:\n"
        "CAUSE: one-sentence likely root cause\n"
        "FIX: one concrete action within Mino's abilities described above\n"
        "ACTION: one of restart_container, stop_container, start_container, or none "
        "(none if no Mino action will help)\n"
        "CONFIDENCE: low | medium | high\n"
        "Do not add extra commentary."
    )


def _user_prompt(context: dict) -> str:
    lines = [
        f"Service: {context.get('service_name', 'unknown')}",
        f"Method: {context.get('method', 'unknown')}",
        f"Status: {context.get('status', 'unknown')}",
    ]
    if context.get("image"):
        lines.append(f"Image: {context['image']}")
    if context.get("container_state"):
        lines.append(f"Container state: {context['container_state']}")
    if context.get("container_health"):
        lines.append(f"Container health: {context['container_health']}")
    if context.get("exit_code") is not None:
        lines.append(f"Exit code: {context['exit_code']}")
    if context.get("oom_killed"):
        lines.append("OOM-killed: true (the kernel killed it for exceeding its memory limit)")
    if context.get("location"):
        lines.append(f"Location: {context['location']}")
    logs = context.get("logs")
    if logs:
        lines.append("")
        lines.append("Recent logs:")
        lines.append(logs[-4000:])
    return "\n".join(lines)


def _parse_response(text: str) -> dict:
    result = {"diagnosis": None, "suggested_fix": None, "confidence": None, "action": None}
    for line in text.strip().splitlines():
        if line.startswith("CAUSE:"):
            result["diagnosis"] = line.replace("CAUSE:", "").strip()
        elif line.startswith("FIX:"):
            result["suggested_fix"] = line.replace("FIX:", "").strip()
        elif line.startswith("ACTION:"):
            raw = line.replace("ACTION:", "").strip().lower()
            # The model only chooses; the server validates against the whitelist.
            result["action"] = "none"
            for cand in ("restart_container", "stop_container", "start_container"):
                if cand in raw:
                    result["action"] = cand
                    break
        elif line.startswith("CONFIDENCE:"):
            raw = line.replace("CONFIDENCE:", "").strip().lower()
            if raw in ("low", "medium", "high"):
                result["confidence"] = raw
    return result


async def diagnose(
    context: dict,
    api_key_encrypted: str | None,
    provider: str,
    model: str,
) -> dict | None:
    api_key = decrypt(api_key_encrypted)
    if not api_key:
        logger.info("skipping LLM diagnosis: no API key configured")
        return None

    settings = get_settings()
    base_url = BASE_URLS.get(provider, BASE_URLS.get(settings.default_provider, "https://api.deepseek.com")).rstrip("/")
    url = f"{base_url}/v1/chat/completions"
    payload = {
        "model": model or settings.default_model,
        "messages": [
            {"role": "system", "content": _system_prompt(context.get("method", "agent"))},
            {"role": "user", "content": _user_prompt(context)},
        ],
        "temperature": 0.2,
        "max_tokens": 2048,
    }

    try:
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(url, headers=_headers(api_key), json=payload)
            resp.raise_for_status()
            data = resp.json()
            message = data["choices"][0]["message"]
            text = message.get("content") or ""
            if not text.strip() and message.get("reasoning_content"):
                text = message["reasoning_content"]
            parsed = _parse_response(text)
            if not parsed["diagnosis"]:
                logger.warning("LLM response missing CAUSE: %s", text[:500])
                return None
            return parsed
    except Exception as exc:
        logger.warning("LLM diagnosis failed: %s", exc)
        return None
