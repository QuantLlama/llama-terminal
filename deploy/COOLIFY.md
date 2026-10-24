# Cloud deployment (Coolify)

This document describes how the Quantum Llama Terminal web/API runs on the
Coolify VPS and how to operate it. The desktop/Electron build is not part of
this deployment.

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
| Branch | `feature/coolify-deploy` |
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
| `MT5_BRIDGE_URL` | *(unset)* | Set it to the tunnel URL when the local MT5 bridge is exposed |
| `TZ` | `America/Argentina/Buenos_Aires` | Market session / chart time handling |
| `QUANTUM_LLAMA_KEY_DIR` | `/app/config/keys` | Writable location for the credential encryption keys (the container user cannot write the project root) |
| `PYTHONUNBUFFERED` | `1` | Live container logs |

`SUPABASE_URL` and `SUPABASE_ANON_KEY` fall back to the values compiled into
`src/services/auth.py`; override them only if the Supabase project changes.

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

1. Push the commit to the tracked branch (`feature/coolify-deploy`).
2. Redeploy from Coolify:
   - UI: *Application → quantum-llama-web → Deploy*.
   - API: `POST /api/v1/deploy` with body `{"uuid":"zzkdpzudy7gp42gfxcffday4"}`.
3. Watch the deployment until `status: finished` and confirm
   `https://llama.nbmsystemas.com/health` returns `200`.

Automatic deployment on push is intentionally disabled; enable
`is_auto_deploy_enabled` and add the GitHub webhook when the branch becomes
`main`.

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
where the broker terminal lives and the cloud app talks to it over HTTP:

1. On the machine that runs MT5, start the bridge (`mt5_server.py`, default
   `127.0.0.1:8081`).
2. Expose it with a private tunnel (WireGuard/Tailscale is the safest option;
   Cloudflare Tunnel works too) and terminate TLS in front of it.
3. Set `MT5_BRIDGE_URL` on the Coolify application to that tunnel URL, e.g.
   `https://mt5.internal.example.com`.
4. Redeploy so the container picks up the variable.

Security requirements for the bridge: keep it off the public internet without
authentication. The current `mt5_server.py` has no auth layer, so the tunnel
must be the only path to it and must require credentials, a VPN, or an IP
allowlist.

Until `MT5_BRIDGE_URL` is configured, the container runs with
`MT5_AUTO_LAUNCH=false`, the MT5 connector reports a connection error, and the
platform continues serving crypto, analysis and backtesting features.

## Operational notes

- The VPS has 2 vCPU and 3.7 GB of RAM. The image excludes `torch`; set the
  build arg `WITH_TORCH=true` only if live AI-model inference is required
  (adds roughly 2 GB to the image and a CPU-only torch build).
- Back up the `qllama-config` volume before changing account or workspace
  configuration; it holds the SQLite database.
- `src/config/*.json` is tracked in git. Editing configuration from the UI
  writes into the mounted volume, so UI changes are not overwritten by a
  redeploy, but they are also not in git.
