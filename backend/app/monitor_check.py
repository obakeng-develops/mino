"""Self-check for the URL-fix path in monitor.py.

The logic worth pinning down: when a down endpoint counts as fixable, that a
proxy-route fix survives the model's "a restart won't help" verdict, and that a
queued fix reaches the host it was queued for. asyncio only, no test framework —
run `python3 -m app.monitor_check` from `backend/`.
"""

import asyncio

from app.monitor import ServiceMonitor, _service_identity

PROXY_FIX = {
    "action": "register_proxy_route",
    "proxy": "kamal-proxy",
    "service": "caready-backend-web",
    "container": "caready-backend-web-latest",
    "host": "api.careadyhealth.com",
    "port": 8000,
    "tls": True,
}


def check_url_fix_ready():
    m = ServiceMonitor()
    # A plain URL check: no host, no fix. Alert-only, as before.
    assert not m._url_fix_ready()

    # A fix but no host to run it: still alert-only.
    m._proposed_fix_action = PROXY_FIX
    assert not m._url_fix_ready()

    # A host but no fix: still alert-only.
    m._proposed_fix_action = None
    m._host_id = "host-1"
    assert not m._url_fix_ready()

    # Both: fixable.
    m._proposed_fix_action = PROXY_FIX
    assert m._url_fix_ready()

    # A fix off the whitelist never becomes runnable, even with a host.
    m._proposed_fix_action = {"action": "rm_rf", "container": "web"}
    assert not m._url_fix_ready()


def check_veto_scope():
    m = ServiceMonitor()
    m._llm_action = "none"

    # "No action will help" is a judgement about bouncing a container, so it
    # vetoes a restart...
    m._proposed_fix_action = {"action": "restart_container", "container": "web"}
    assert m._fix_vetoed()

    # ...but not a proxy-route registration, which is the operator's configured
    # answer to exactly this failure.
    m._proposed_fix_action = PROXY_FIX
    assert not m._fix_vetoed()

    # With no veto, a restart is fine.
    m._llm_action = "restart_container"
    m._proposed_fix_action = {"action": "restart_container", "container": "web"}
    assert not m._fix_vetoed()


def check_fix_phrasing():
    m = ServiceMonitor()
    m._container = "api.careadyhealth.com"
    m._proposed_fix_action = PROXY_FIX
    # Don't record "Restarted" for something that was never restarted — this text
    # is read back to the model as history.
    assert m._fix_done_phrase() == "Re-registered the proxy route for api.careadyhealth.com"
    m._proposed_fix_action = {"action": "restart_container", "container": "web"}
    assert m._fix_done_phrase() == "Restarted api.careadyhealth.com"


def check_pending_routes_to_its_host():
    """A URL fix has no container in the beat's svc_map, so it has to be delivered
    on the host_id it was queued with — not by looking its target up."""
    m = ServiceMonitor()

    class FakeHost:
        def __init__(self, hid):
            self.id = hid
            self.name = hid

    m._pending_agent_restarts = {"svc-url": {**PROXY_FIX, "host_id": "host-1"}}

    async def deliver(host_id):
        # Stub out the DB sync; only the delivery filter is under test.
        async def fake_sync(host, containers):
            return {}, {}, []

        m._sync_agent_services = lambda host, containers: ({}, {}, [])
        m._process_sources = lambda snapshots, source_name: asyncio.sleep(0)
        return await m.handle_agent_beat(FakeHost(host_id), [])

    # Wrong host: nothing handed over, fix stays queued.
    restarts, _ = asyncio.run(deliver("host-2"))
    assert restarts == [], restarts
    assert "svc-url" in m._pending_agent_restarts

    # Right host: delivered once and cleared.
    restarts, _ = asyncio.run(deliver("host-1"))
    assert len(restarts) == 1 and restarts[0]["action"] == "register_proxy_route"
    assert m._pending_agent_restarts == {}


def check_can_approve():
    m = ServiceMonitor()
    m._view = "asking"
    m._method = "url"

    # An endpoint with nothing to run must not offer a button.
    m._proposed_fix_action = None
    assert not m._build_state().can_approve

    # One with a configured fix does.
    m._proposed_fix_action = PROXY_FIX
    assert m._build_state().can_approve

    # A vetoed restart doesn't, whatever the method.
    m._method = "agent"
    m._proposed_fix_action = {"action": "restart_container", "container": "web"}
    m._llm_action = "none"
    assert not m._build_state().can_approve

    # Not at the ask step, no button.
    m._view = "fixing"
    m._llm_action = None
    assert not m._build_state().can_approve


def check_service_identity_untouched():
    # Guard the existing Kamal identity behaviour these changes route around.
    assert _service_identity("caready-backend-web-latest") == "caready-backend-web"
    assert _service_identity("db") == "db"


def main():
    check_url_fix_ready()
    check_veto_scope()
    check_fix_phrasing()
    check_pending_routes_to_its_host()
    check_can_approve()
    check_service_identity_untouched()
    print("monitor self-check ok")


if __name__ == "__main__":
    main()
