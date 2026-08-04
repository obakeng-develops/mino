# Let Mino fix a URL check

A URL check is alert-only by default: Mino tells you the endpoint is down and hands it to you. That
is the right default, because Mino has no idea what sits behind a hostname.

Sometimes it does know. The failure this exists for: a container is healthy and has been for days,
but its public hostname is dead because the reverse proxy holds no route for it. With no route the
proxy has no certificate to serve, so it aborts the TLS handshake and browsers report
`ERR_SSL_PROTOCOL_ERROR`. Nothing is crashed. A restart fixes nothing. The route has to be
registered again — and that is a single command Mino can run.

Give a URL check a **host** and a **fix**, and it stops being a dead end.

## Before you start

- The host that runs the proxy is [connected and running the agent](install-the-agent.md), on agent
  version `2026-07-26` or newer.
- The proxy is `kamal-proxy`, running as a container on that host.
- You know the hostname, the app container's name, and the port it listens on.

## Steps

1. Get the host's id. `GET /api/v1/hosts` lists them; take the `id` of the one running the proxy.
2. Attach the host and the fix to the check. On an existing one:

```bash
curl -X PATCH https://mino.example.com/api/v1/services/<service-id> \
  -H 'Content-Type: application/json' \
  -H "Authorization: Bearer $TOKEN" \
  -d '{
        "host_id": "<host-id>",
        "allowed_fix_action": {
          "action": "register_proxy_route",
          "proxy": "kamal-proxy",
          "service": "caready-backend-web",
          "container": "caready-backend-web-latest",
          "host": "api.careadyhealth.com",
          "port": 8000,
          "tls": true,
          "health_check_path": "/"
        }
      }'
```

`POST /api/v1/services` takes the same two fields when you create the check.

3. That is all. Next time the check fails, Mino diagnoses it, then either asks you to approve the
   fix or runs it, depending on the fleet's autonomy — the same path a container failure takes.

## The fix fields

| Field | Meaning |
|---|---|
| `action` | `register_proxy_route` |
| `proxy` | the proxy container to run the command in (`kamal-proxy`) |
| `service` | the service name to register the route under, as the proxy knows it |
| `container` | the app container the route should point at |
| `host` | the public hostname |
| `port` | the port the app container listens on |
| `tls` | `true` to have the proxy manage a certificate for the hostname |
| `health_check_path` | optional; the path the proxy probes before accepting the target |

**Set `health_check_path` unless your app serves `/up`.** kamal-proxy probes the target before it
accepts a new route and defaults that probe to `/up`, which is a Rails convention. An app that
serves `/` or `/health` instead never reports healthy, and the registration fails after 30 seconds
with `target failed to become healthy within configured timeout`. Nothing breaks when this happens —
the proxy keeps the route it already had — but the fix doesn't land either.

The agent resolves the container's current IP itself, at fix time. Don't try to pin one: a
container's IP changes when it is recreated, and an IP decided minutes earlier is how a route ends
up pointing at nothing.

## What Mino will and won't do

- The fix must pass the action whitelist (`backend/app/actions.py`). A malformed one is rejected
  when you configure it, not silently mid-incident.
- Set only one of `host_id` and `allowed_fix_action` and the check stays alert-only. Both or
  neither.
- The model is never asked to invent this. It diagnoses the outage; the fix is the one you
  configured. Its "a restart won't help" verdict doesn't veto a proxy-route fix, because that
  verdict is about bouncing a container.
- Mino only re-registers a route. It won't edit your proxy config, issue certificates by hand, or
  touch DNS.

## Check it works

Break the route on purpose, on a host you don't mind disturbing:

```bash
# see the routes the proxy holds
docker exec kamal-proxy kamal-proxy list

# drop one
docker exec kamal-proxy kamal-proxy remove <service>
```

The check fails within its poll interval (30s), Mino opens an incident naming the handshake
failure, and — once approved, or straight away under auto-fix — the route comes back. `kamal-proxy
list` shows it again.
