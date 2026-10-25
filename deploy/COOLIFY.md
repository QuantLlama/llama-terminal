# Cloud deployment (Coolify)

This document describes how the Quantum Llama Terminal web/API runs on the
Coolify VPS and how to operate it. The desktop/Electron build is not part of
this deployment.

For the architecture, request paths, security model and the integration problems
behind this setup, read [`../docs/CLOUD.md`](../docs/CLOUD.md).

## Topology

```
Browser ──HTTPS──> Traefik (Coolify proxy) ──> quantum-llama-web container ──> FastAPI (uvicorn :8050)
                                                    │
                                                    ├─ SPA assets from src/platform/web
                                                    ├─ SQLite  /app/config/quantum_llama.db   (volume qllama-config)
                                                    ├─ Models  /app/outputs                   (volume qllama-outputs)
                                                    └─ Logs    /app/logs                      (volume qllama-logs)
```

Crypto market data (CCXT) and Supabase auth run inside the container.
MetaTrader 5 cannot run inside a Linux container; see "MT5 bridge" below.

## Current Coolify resources

| Resource | Value |
| --- | --- |
| Project | `Quantum Llama` (`90bx3rrvtwhlby6khhijshou`) |
| Application | `quantum-llama-web` (`zzkdpzudy7gp42gfxcffday4`) |
| Server | `localhost` (`nkirbxo6kjkkoiywkqdsesr9`) |
| Domain | `https://llama.nbmsystemas.com` |
| Branch | `main` |
| Build pack | Dockerfile (`/Dockerfile`) |
| Exposed port | `8050` |
| Health check | `GET /health` on port `8050` |
| Private key | `GitHub QuantLlama (read-only deploy key)` (`roqekywcxrd48tbwhipilerl`) |

The deploy key is registered in the GitHub repository as a **read-only** key,
so Coolify can clone but never push.

## Environment variables

| Variable | Value | Why |
| --- | --- | --- |
| `APP_PORT` | `8050` | Port uvicorn binds and Traefik forwards to |
| `MT5_AUTO_LAUNCH` | `false` | There is no Wine/MT5 inside the container; never try to boot it |
| `MT5_BRIDGE_URL` | `http://10.0.0.1:8081` | The VPS relay, never the tailnet address: the container has no route to the tailnet |
| `MT5_BRIDGE_TOKEN` | deployment secret | Same value as `~/.config/qllama/mt5_bridge_token` on the operator machine |
| `CRYPTO_HTTP_PROXY` | `http://10.0.0.1:3128` | Same relay pattern for crypto: the venue answers HTTP 451 to this region |
| `TZ` | `America/Argentina/Buenos_Aires` | Market session / chart time handling |
| `SUPABASE_URL` | from the Supabase project | Required for authentication; no code default |
| `SUPABASE_ANON_KEY` | from the Supabase project | Required for authentication; no code default |
| `QUANTUM_LLAMA_KEY_DIR` | `/app/config/keys` | Writable location for the credential encryption keys (the container user cannot write the project root) |
| `PYTHONUNBUFFERED` | `1` | Live container logs |

`SUPABASE_URL` and `SUPABASE_ANON_KEY` are **required** when authentication is used: the
application has no compiled defaults, and without both variables the Supabase client stays
disabled (auth-dependent routes answer `500 Supabase not configured`). Set them in the
application's environment before deploying a build that includes this change. They live in
the deployment secret store, never in the repository.

## Persistent volumes

Docker named volumes are mounted over paths that the app writes to:

| Volume name | Mount path | Contents |
| --- | --- | --- |
| `<app-uuid>-qllama-config` | `/app/config` | SQLite database, live/account/symbol configuration |
| `<app-uuid>-qllama-outputs` | `/app/outputs` | Trained models and generated artifacts |
| `<app-uuid>-qllama-logs` | `/app/logs` | Runtime logs |

On first start Docker copies the image contents of those directories into the
volume, so the shipped default configuration files are preserved.

## Deploying a new version

1. Push the reviewed commit to the tracked branch (`main`).
2. Redeploy from Coolify:
   - UI: *Application → quantum-llama-web → Deploy*.
   - API: `POST /api/v1/deploy` with body `{"uuid":"zzkdpzudy7gp42gfxcffday4"}`.
3. Watch the deployment until `status: finished` and confirm
   `https://llama.nbmsystemas.com/health` returns `200`.

Automatic deployment was confirmed enabled on `main`, then paused during the authorized history purge. Keep `is_auto_deploy_enabled=false` until the runtime authentication migration in PR #28 has completed its required security review. The running container was not restarted. See [`../docs/SECURITY-REMEDIATION.md`](../docs/SECURITY-REMEDIATION.md) before any manual redeployment.

## Verifying a deployment

```bash
curl -s https://llama.nbmsystemas.com/health
curl -s -o /dev/null -w '%{http_code} %{content_type}\n' https://llama.nbmsystemas.com/
curl -s -o /dev/null -w '%{http_code} %{content_type}\n' https://llama.nbmsystemas.com/lib/babel.min.js
curl -s -o /dev/null -w '%{http_code} %{content_type}\n' https://llama.nbmsystemas.com/images/QuantumLLama.png
curl -s -o /dev/null -w '%{http_code} %{content_type}\n' https://llama.nbmsystemas.com/components/ChartPane.js
```

Expected: `200 application/json` for `/health`, `200 text/html` for `/`,
`200 application/javascript` for the vendored scripts and components,
`200 image/png` for the images.

## MT5 bridge (local broker, cloud UI)

`MetaTrader5` is a Windows-only Python package, so the terminal keeps running
where the broker terminal lives and the cloud app talks to it over HTTP. The
container never reaches the tailnet directly: it calls a socat relay on the VPS
that forwards to the operator machine.

```
container (MT5_BRIDGE_URL=http://10.0.0.1:8081)
   -> socat relay on the VPS
   -> <operator-tailnet-ip>:8081 bridge (mt5_server.py)
   -> MetaTrader 5 terminal
```

1. On the machine that runs MT5, start the bridge (`mt5_server.py`, default
   `127.0.0.1:8081`; `MT5_BRIDGE_BIND=0.0.0.0` to accept tailnet traffic) and
   run it as the user service described below.
2. Install the relay on the VPS with `sudo ./deploy/vps/setup-mt5-relay.sh`;
   it writes `/etc/default/qllama-mt5-relay` and enables
   `qllama-mt5-relay.service`.
3. Set `MT5_BRIDGE_URL=http://10.0.0.1:8081` and `MT5_BRIDGE_TOKEN` on the
   Coolify application.
4. Redeploy so the container picks up the variables.

`deploy/MT5_BRIDGE.md` holds the full procedure, including the same relay
pattern for crypto egress (`CRYPTO_HTTP_PROXY`).

Security requirements for the bridge: `mt5_server.py` requires an
`X-Bridge-Token` header on every request and refuses to serve a non-loopback
bind without a configured token, so set `MT5_BRIDGE_TOKEN` to the same value on
both sides. The bridge still has a single shared secret and no per-user
authorization: keep it off the public internet and reach it only through a
private network (tailnet, VPN) or an authenticated tunnel.

The full topology, security model and the problems solved during the rollout are
documented in [`../docs/CLOUD.md`](../docs/CLOUD.md).

`MT5_AUTO_LAUNCH=false` always stays set in the container: the terminal is never
started there. If the relay or the operator machine is down, the MT5 connector
reports a connection error and the platform keeps serving crypto, analysis and
backtesting until the bridge returns. The crypto feed needs the operator machine
too, because every exchange request leaves through the tailnet proxy.

## Operational notes

### Deploys answer "Server is not functional"

Coolify stops deploying when it decides the server is unhealthy, and the failure is
self-locking: the sentinel heartbeat is refused with `401 {"message":"Server is not
functional"}` every minute, so the server can never prove it recovered.

Symptoms:

- The manual GitHub webhook answers
  `[{"application":"quantum-llama-web","status":"failed","message":"Server is not functional."}]`
  and no row appears in `application_deployment_queues`.
- `docker logs coolify-sentinel` repeats `push operation failed ... returned 401`.

Check and repair (both mutations are health state only, nothing is deleted):

```bash
sudo docker exec coolify-db psql -U coolify -d coolify -c \
  "select unreachable_count, sentinel_updated_at from servers;"
sudo docker exec coolify-db psql -U coolify -d coolify -c \
  "select is_reachable, is_usable from server_settings;"

# reset the counter and both settings together, or the deadlock returns
sudo docker exec coolify-db psql -U coolify -d coolify -c \
  "update servers set unreachable_count = 0;"
sudo docker exec coolify-db psql -U coolify -d coolify -c \
  "update server_settings set is_reachable = true, is_usable = true;"
```

Wait for one sentinel push without an error (up to a minute;
`sentinel_updated_at` must be current) and redeploy. A healthy server logs only
`pushing url=...` and the deploy row appears with `status = in_progress`.

- The VPS has 2 vCPU and 3.7 GB of RAM. The image excludes `torch`; set the
  build arg `WITH_TORCH=true` only if live AI-model inference is required
  (adds roughly 2 GB to the image and a CPU-only torch build).
- Back up the `qllama-config` volume before changing account or workspace
  configuration; it holds the SQLite database.
- `src/config/*.json` is tracked in git. Editing configuration from the UI
  writes into the mounted volume, so UI changes are not overwritten by a
  redeploy, but they are also not in git.
