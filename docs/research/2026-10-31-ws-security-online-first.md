# WebSocket authentication and transport security for online-first

Date: 2026-10-31. Question: how to secure `/ws` and the transport when the system becomes internet-reachable
(Starlink in the field, hosted develop on Kubernetes) with no CA-signed certificate available.

Examined: our code (`backend/routers/ws.py`, `backend/ws.py`, `backend/auth.py`, `backend/routers/auth.py`,
`backend/main.py`, `backend/routers/users.py`, `frontend/src/composables/useWebSocket.js`,
`deploy/docker/nginx.conf`, `deploy/k8s/app/*`), ADR 12/15, risk R-22.

External sources fetched: Let's Encrypt challenge types, the Let's Encrypt 2026-01-15 IP/6-day GA post, uvicorn
settings, Tailscale HTTPS docs, WebKit and Chromium discussion on `wss://` with an accepted exception. The facts about
Starlette, OWASP, Caddy, mkcert and cert-manager are from the researcher's own knowledge and were not fetched.
**Re-check them before an ADR cites them.**

## Verdict

Authenticate `/ws` with option (b), extended. The browser sends `{"type":"auth","token":<access JWT>}` as the first
message. The server drops the socket after 5 s without a valid token. The client re-sends a fresh token after every
refresh. Add a strict `Origin` check. This reuses the existing JWT and refresh flow, puts no secret in a URL, and needs
no new endpoint.

For transport:
- **Field laptop:** keep `http://localhost`, which is a secure context and needs no certificate (ADR 12). If other
  devices must reach it, use Caddy `tls internal` with its root installed once per device.
- **Hosted develop:** cert-manager with Let's Encrypt, which needs a real domain.

| Surface | (1) /ws auth | (2) Transport |
|---|---|---|
| Field laptop, offline-capable (TP-01) | First-message JWT plus Origin check, always on. The map UI already needs an admin login, so there is no offline cost. | Same-machine browser: `ws://localhost`, no TLS. LAN or Starlink clients: Caddy `tls internal`, hostname plus IP SAN, root CA installed once. |
| Hosted develop (K8s) | Same code path. | Ingress TLS via cert-manager and Let's Encrypt (HTTP-01, public ingress, domain required). With no domain: a cert-manager CA issuer, root installed on testers' machines. |

The owner must decide:
1. **Buy a domain or not (about 10 EUR a year).** Without one, no public-CA certificate is possible for a DNS name.
   Let's Encrypt now issues IP-address certificates (GA 2026-01-15, 160 h lifetime), but only through HTTP-01 or
   TLS-ALPN-01. The IP therefore has to be publicly reachable. That fits the cluster's load-balancer IP and does not fit
   a CGNAT Starlink laptop.
2. **Is the field laptop ever reached from outside its own machine?** If not, it needs no TLS.
3. **Accept a private root CA on operator laptops, or pay for the domain.**

BP-02: authentication must not delay alarms to an authenticated client, and a lapsed token must not silently stop live
updates. The design below covers both.

## Borrow

### 1. In-band JWT auth with deadline, re-auth and Origin check (effort M)

Files: `backend/routers/ws.py`, `backend/ws.py`, `backend/auth.py` (factor out `verify_access_token(token, conn)` from
`get_current_user`), `frontend/src/composables/useWebSocket.js`, the auth store.

| Option | Fit with JWT and refresh | Expiry mid-connection (60 min) | Exposure | CSRF / Origin | Starlette support |
|---|---|---|---|---|---|
| (a) Query-string JWT | Easy | Cannot change on an open socket; needs a reconnect | Worst: uvicorn access log, ingress and proxy logs, history, Referer | Origin check still needed | `websocket.query_params` |
| (b) First message | Easy, same token as REST | In-band `{type:auth}` re-send, no reconnect | None in URL or headers | Origin check needed; browsers apply neither SOP nor CORS to WS | Yes: `accept()` then `receive_json()` under `asyncio.wait_for` |
| (c) One-time ticket | New REST endpoint plus server state (in-memory is fine, we are single process) | Checked only at connect | Short-lived and single use, so a leaked URL is harmless | Origin check needed | Manual |
| (d) HttpOnly cookie | Conflicts with Bearer-in-localStorage. Needs `Secure`, `SameSite` and CSRF handling, and the Vite proxy and CORS wildcard must change | Cookie refresh is separate | No JS access | Cookies go cross-site on the handshake (CSWSH), so the Origin check is mandatory | `websocket.cookies` |
| (e) `Sec-WebSocket-Protocol` | `new WebSocket(url, ['bearer', jwt])`; the server must echo a subprotocol | Same limit as (a): reconnect on every refresh | Not in the URL; some proxies log headers | Origin check needed | `scope['subprotocols']`, `accept(subprotocol=...)` |

(b) is the only option where expiry is handled without a reconnect and no endpoint or state is added. Until
authenticated, the socket is not added to `manager._clients`, so it receives nothing. (c) is the fallback if the owner
dislikes an unauthenticated 5 s window.

Server sketch:
```python
AUTH_DEADLINE_S, REAUTH_GRACE_S = 5, 120

@router.websocket('/ws')
async def websocket_endpoint(websocket: WebSocket):
    if not origin_allowed(websocket.headers.get('origin'), websocket.headers.get('host')):
        await websocket.close(code=1008)      # closed before accept: browser sees HTTP 403
        return
    await websocket.accept()
    try:
        exp = await _authenticate(websocket, timeout=AUTH_DEADLINE_S)   # receive_json + verify_access_token
    except (asyncio.TimeoutError, AuthError):
        await websocket.close(code=4401); return
    manager.add(websocket)
    try:
        while True:
            left = exp + REAUTH_GRACE_S - time.time()
            msg = await asyncio.wait_for(websocket.receive_json(), timeout=max(left, 0.1))
            if msg.get('type') == 'auth':     # client re-sends after each refresh
                exp = await _verify(msg.get('token'))
    except (WebSocketDisconnect, asyncio.TimeoutError, AuthError, ValueError):
        pass
    finally:
        manager.disconnect(websocket)         # close(4401) if the cause was expiry or bad auth
```
Client: send `{type:'auth', token}` on `open`. Send the new token from the axios refresh-success path and from a timer
at 50 min. On close code 4401, refresh once and reconnect at once (not after 3 s). If the refresh returns 401, log out.

- The existing 45 s REST resync already triggers the refresh interceptor, so the token stays fresh for free.
- The 120 s grace past `exp` absorbs a slow Starlink refresh.
- `verify_access_token` re-reads the user row, so a deactivated user loses the socket at the next re-auth.
- Origin allowlist: `settings.allowed_origins`. If empty, accept only when the Origin host equals the `Host` header.
  Browsers always send `Origin` on a WS handshake. Allow a missing Origin when a valid token follows, for tools such as
  `demo.py`.
- Do not close sockets for "no inbound traffic", because the client sends none by design. Dead peers are handled by
  uvicorn ping/pong (defaults 20 s and 20 s).

### 2. Transport per environment (S for Caddy on the field machine, M for cert-manager)

| Option | Offline in the field | Effort | Renewal | `wss://` without clicks |
|---|---|---|---|---|
| (a) openssl self-signed leaf | Yes | High: install in each OS store, redo on expiry | Manual redistribution | Only after install or a warning click |
| (b) Caddy internal CA or mkcert | Yes | Low: root installed once per device | Caddy renews leaves automatically; root lasts about 10 years | Yes once the root is trusted. Firefox needs `security.enterprise_roots.enabled` or its own import. |
| (c) Let's Encrypt DNS-01 | Needs internet at issue and renewal; serves a cached cert offline | Domain plus DNS API token | Automatic | Yes, nothing to set up on clients |
| (d) Tunnel | No, needs internet | Low | Provider | Yes |
| (e) cert-manager | Hosted cluster only | Low once set up | Automatic | Yes with LE (domain) or CA issuer plus installed root |

**(a) Self-signed.** The command (OpenSSL 1.1.1 or newer):
```
openssl req -x509 -newkey ec -pkeyopt ec_paramgen_curve:prime256v1 -nodes -days 365 \
  -keyout bee.key -out bee.crt -subj "/CN=bee.local" \
  -addext "subjectAltName=DNS:bee.local,DNS:localhost,IP:192.168.1.10" \
  -addext "basicConstraints=critical,CA:FALSE" \
  -addext "keyUsage=critical,digitalSignature" -addext "extendedKeyUsage=serverAuth"
```
- The SAN is mandatory because browsers ignore CN.
- Windows trust store (admin): `certutil -addstore -f Root bee.crt`, or
  `Import-Certificate -FilePath bee.crt -CertStoreLocation Cert:\LocalMachine\Root`. Chrome and Edge read the Windows
  store. Firefox has its own store unless `security.enterprise_roots.enabled=true`.
- Click-through exception: an exception made for `https://host:port` covers the same host and port, and Chromium treats
  it as valid for `wss://` too. WebKit and Safari historically refused. The usual failure is a different port or host
  for the socket (`ERR_CERT_AUTHORITY_INVALID`). Our `/ws` is same-origin (`location.host`), so a click-through should
  work in Chrome, Edge and Firefox. It is still a warning on every first visit, and Chromium restricts some powerful
  features on pages loaded after a bypassed certificate error. Current Firefox and Edge behaviour was not confirmed
  against primary docs: test before relying on it.

**(b) Private CA.** Renewing a leaf does not touch the clients, which is the advantage over (a).
- Caddy: put `tls internal` in the site block. The root is at `<caddy data>/pki/authorities/local/root.crt`.
  `caddy trust` installs it locally; copy it to other laptops.
- mkcert: `mkcert -install; mkcert bee.local 192.168.1.10 localhost`. The `rootCA-key.pem` must never leave the machine.
- Risk: whoever holds the root key can mint a certificate for any site on every laptop with the root installed. A
  hand-made CA with a `nameConstraints` extension (permitted DNS `bee.local` and an IP range) limits this. Neither Caddy
  nor mkcert adds name constraints by default.

**(c) Let's Encrypt without a public port.**
- Confirmed from the Let's Encrypt docs: HTTP-01 "can only be done on port 80", TLS-ALPN-01 uses port 443, and DNS-01
  "cannot be used to validate IP Addresses".
- Standard Starlink is CGNAT with no inbound connections. HTTP-01 and TLS-ALPN-01 are therefore impossible for a field
  laptop, and IP certificates are impossible too, because they need those two challenges. Starlink's IPv6 inbound
  behaviour was not verified.
- DNS-01 with a domain (or a dynamic-DNS provider with a TXT API) is the only public-CA route. Caddy and `lego` have DNS
  plugins. It needs internet only at issue and renewal.

**(d) Tunnels.**
- Cloudflare Tunnel needs a Cloudflare-managed domain and sends traffic through a third party.
- Tailscale `tailscale cert` gives `*.ts.net` names via Let's Encrypt DNS-01. The private key stays local, names go
  into public CT logs, and you renew the file yourself unless you use the Caddy integration.
- WireGuard encrypts the link, but Tailscale needs its coordination server for login and node-key renewal, which
  conflicts with a pure offline start (TP-01). Use it as an optional remote-access layer, not as the base.

**(e) cert-manager.** Use a `ClusterIssuer` with ACME HTTP-01 through the ingress for a real hostname. Without a
domain, use a `CA` or `selfSigned` issuer. `deploy/k8s/app/kustomization.yaml` says ingress is managed outside the
repo, so the TLS the owner has today is not visible.

**Ingress and WebSocket.**
- The ingress must forward the Upgrade headers, and its read timeout must exceed the 20 s ping interval. With
  ingress-nginx, uvicorn's pings keep the default 60 s `proxy-read-timeout` from firing.
- `deploy/docker/nginx.conf` has no `/ws` or `/api` proxy, so that routing must live in the ingress. Check it.

### 3. Online-first hardening bundle (effort M)

Files: `backend/ws.py`, `backend/main.py`, `backend/routers/users.py`, `backend/routers/auth.py`, `backend/config.py`.

- **Bounded broadcast (BP-02).** `broadcast` awaits `send_json` one client at a time, so one slow internet client
  stalls alarms for everyone.
  ```python
  async def _send(ws, msg):
      try: await asyncio.wait_for(ws.send_json(msg), SEND_TIMEOUT_S)   # 5
      except Exception: return ws
  dead = {r for r in await asyncio.gather(*(_send(w, message) for w in list(self._clients))) if r}
  ```
  The client resyncs over REST on reconnect, so dropping a laggard is safe.
- **Limits.** Run uvicorn with `--ws-max-size 4096` (default 16777216). Cap total sockets, for example 50. Keep ping
  interval and timeout at 20 s. Behind an ingress, add `--proxy-headers --forwarded-allow-ips <ingress CIDR>` so
  client IPs are real.
- **CORS from settings.** Replace `allow_origins=['*']` with `settings.cors_origins`. Empty means same-origin only,
  which is what an ingress deployment needs. CORS never covers WebSockets.
- **`/uploads` behind auth.** Photos are named with UUID4 (`users.py:190`), so they are unguessable, but they never
  expire and need no login (DP-01). A plain `<img src>` cannot send a Bearer header. Use either (i) short-lived
  HMAC-signed URLs, `/api/users/{id}/photo?exp=..&sig=..`, keyed from `secret_key` and minted by the list/live
  endpoints, or (ii) fetch the image as a blob through axios. (i) fits the planned thin WS payload: the WS carries IDs
  and REST returns signed photo URLs. Remove the `StaticFiles` mount at `main.py:285` afterwards.
- **Login rate limit.** A small in-memory limiter keyed by `(IP, username)`, for example 10 failures in 5 min gives
  429, is enough for a single process. `slowapi` is the packaged alternative.

## Risks in our code

| # | Severity | Where | Risk |
|---|---|---|---|
| 1 | High once online | `backend/routers/ws.py:8-16`, `backend/ws.py:34-37` | `/ws` accepts anyone and streams `full_name`, `phone`, `photo_url` and SOS to every client (R-22, DP-01, DP-02). ADR 15 holds only on loopback, so it needs superseding. No Origin check, so any web page can open the socket from a user's browser (CSWSH) once the server is reachable. |
| 2 | High once online | `backend/main.py:285` | `/uploads` serves volunteer photos with no auth and no expiry. Random UUID4 names (`users.py:190`) are the only protection, and the names are in the open WS payload. |
| 3 | Medium-High (BP-02) | `backend/ws.py:43-50` | Sequential broadcast with no send timeout. One slow or half-open client delays alarms to all. It also iterates `_clients` while a connect can mutate it. |
| 4 | Medium | `backend/routers/ws.py:12-14` | Only `WebSocketDisconnect` is caught. A binary frame or any other exception from `receive_text()` leaves the socket in `_clients` until a later broadcast fails. No connection cap, and the 16 MiB uvicorn message limit is at its default. |
| 5 | Medium | `backend/main.py:259-265` | `allow_origins=['*']` with `allow_credentials=True` ("tighten in production"). Low today because auth is Bearer, but a real hole if any cookie is ever added. |
| 6 | Medium | `backend/routers/auth.py:28-52` | Login has no rate limit or lockout. Once the host is public, the admin password is open to online guessing. `admin`/`admin` on an empty DB is the worst case for a hosted environment. The insecure-defaults check in `main.py` only warns; it should refuse in hosted mode. |
| 7 | Low | `backend/auth.py:78-95` | A deactivated user's token stays valid for up to 60 min, and a long-lived WS is never re-checked. Fixed by the re-auth in Borrow 1. |
| 8 | Low | `backend/ws.py:69-72` | The DSN is built with an f-string, so a password containing `@`, `:` or `/` breaks the listener. Use asyncpg keyword arguments. A correctness issue, not security. |
| 9 | Low | `frontend/src/composables/useWebSocket.js:55-56,91` | Fixed 3 s reconnect with no backoff and no 4401 handling. It will loop against a server that rejects the socket. |

## Skip

- **Client id / client secret.** It is application-layer authentication of the calling program, not confidentiality.
  A secret compiled into a browser SPA is readable by anyone who loads the page. It proves nothing about the user and
  adds nothing over the JWT. It does not encrypt traffic; only TLS does. It is worth having for non-browser machine
  clients (a future gateway, `tools/demo.py`), using the OAuth2 client-credentials grant with revocable per-client
  secrets. That is not a reason to change `/ws`.
- Ticket flow (c): correct but heavier. Revisit if the owner will not accept the 5 s unauthenticated window.
- HttpOnly cookie (d): forces CSRF, SameSite and CORS redesign for no gain over Bearer.
- Query-string JWT (a): the token lands in access and proxy logs.
- Subprotocol token (e): works, but cannot be rotated in-band, so every refresh needs a reconnect.
- Hand-distributed self-signed leaf: no renewal story. Prefer a private CA.
- Cloudflare Tunnel: third-party path and domain requirement for a system that must start offline (TP-01).
- Tailscale as the base layer: needs its control plane; fine as an optional add-on.
- Let's Encrypt IP certificates for the field laptop: need inbound 80/443, impossible behind CGNAT.

## Addendum (2026-10-31, from the maintainer): JWT revocation, input for the `identity` module and the WS re-auth design

Source: an article on why a password change does not stop a JWT (ASP.NET Core examples; the mechanics are
framework-independent). Applied to our code (`backend/auth.py`: HS256, access 60 min, refresh 7 d, refresh tokens
**not stored**, so nothing can be revoked today):

1. **Step 1, do this first:** short access tokens (the article uses 5 min; 60 min today) plus **stored, rotating refresh
   tokens**: a `refresh_tokens` table with the token hash, `user_id`, `family_id` (one family per login), `expires_at`
   (absolute, from login), `used_at`. `/auth/refresh` marks the token used in one atomic `UPDATE … WHERE used_at IS NULL`;
   zero rows updated means **reuse** → delete the whole family and answer 401. Logout deletes one family; password change
   or deactivation deletes every family of the user. Refresh from one place in the client (two tabs refreshing at once
   look like reuse).
2. **Step 2, when minutes are too long:** a `token_version` column on `users`, copied into the token; `get_current_user`
   compares it (and `is_active`) against the row on every request. Costs one indexed query per request (negligible at our
   10 devices and one operator) and makes auth depend on the database, which it already does here. This is exactly the
   "re-read the user row on re-auth" that Borrow 1 recommends for the live channel: the WS re-auth message should
   carry a token whose `token_version` still matches.
3. **Where it lands in the programme:** `identity` module (step 5) owns `/auth/*` and the new table (migration through the
   reviewer); the WS re-auth (deferred, device-maker discussion) consumes the same `verify_access_token`. Put the family
   id in the token as `sid` so a WS connection can be dropped when its session is logged out.

## Sources

- Let's Encrypt challenge types: https://letsencrypt.org/docs/challenge-types/
- Let's Encrypt 6-day and IP certificates GA, 2026-01-15: https://letsencrypt.org/2026/01/15/6day-and-ip-general-availability
- uvicorn settings, defaults ws-max-size 16777216, ws-ping-interval 20, ws-ping-timeout 20: https://raw.githubusercontent.com/encode/uvicorn/master/docs/settings.md
- Tailscale HTTPS: https://tailscale.com/kb/1153/enabling-https
- WebKit thread on accepting a certificate warning for `wss://`: https://lists.webkit.org/pipermail/webkit-dev/2011-June/017335.html
- Not fetched, from memory (verify): OWASP WebSocket Security Cheat Sheet, RFC 6455 sections 10.2 and 7.4, Starlette WebSocket docs, Caddy `tls internal`, mkcert README, cert-manager ACME and CA issuers.
- Our code and docs: `backend/routers/ws.py`, `backend/ws.py`, `backend/auth.py`, `backend/routers/auth.py`, `backend/main.py`, `backend/routers/users.py`, `frontend/src/composables/useWebSocket.js`, `deploy/docker/nginx.conf`, `deploy/k8s/app/kustomization.yaml`, `Architecture/governance/risk-register.md` (R-22), ADR 0012 and 0015.
