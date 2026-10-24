# MT5 bridge: local terminal, cloud UI

`MetaTrader5` is a Windows-only Python package, so the terminal stays on your
machine and the cloud app talks to it over HTTP. This document is the exact
procedure for both sides.

```
MetaTrader 5 terminal ──> mt5_server.py (bridge :8081) ──> Tailscale tailnet ──> Coolify container
```

## 1. Local machine (where MT5 runs)

### Configuration

| Variable | Local value | Meaning |
| --- | --- | --- |
| `MT5_BRIDGE_BIND` | `0.0.0.0` when using Tailscale, otherwise `127.0.0.1` | Interface the bridge listens on |
| `MT5_BRIDGE_PORT` | `8081` (default) | Bridge port |
| `MT5_BRIDGE_TOKEN` | long random value | Shared token required on every request |

`127.0.0.1` + no token is the desktop default and stays unchanged. As soon as
the bridge is reachable from another machine, set a token: the API can place
orders.

Generate a token once:

```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

### Start the bridge

Windows (inside the MT5 environment):

```bat
set MT5_BRIDGE_BIND=0.0.0.0
set MT5_BRIDGE_TOKEN=<your token>
start_mt5_server.bat
```

Linux with Wine (MT5 running under Wine, Python inside the same prefix):

```bash
export MT5_BRIDGE_BIND=0.0.0.0
export MT5_BRIDGE_TOKEN=<your token>
wine python -m uvicorn mt5_server:app --host "$MT5_BRIDGE_BIND" --port 8081
```

Verify locally:

```bash
curl -s -H "X-Bridge-Token: <your token>" http://127.0.0.1:8081/api/balance
```

Without the token the bridge answers `401 {"detail": "invalid bridge token"}`.
The terminal must be logged in to the broker account before trading works.

## 2. Private network (Tailscale)

The bridge must never be published on the public internet.

1. Install Tailscale on the local machine and log in:
   `curl -fsSL https://tailscale.com/install.sh | sh && sudo tailscale up`
2. Install Tailscale on the Coolify VPS (already done during the deployment).
3. Confirm both nodes see each other:
   `tailscale status`
4. Note the local machine's tailnet address (`100.x.y.z`) and that the bridge
   answers on it:

```bash
curl -s -H "X-Bridge-Token: <your token>" http://<local-tailnet-ip>:8081/api/balance
```

Tailnet traffic is WireGuard-encrypted and authenticated by device identity;
only devices in your tailnet can reach the bridge.

### Firewall rule (recommended)

Allow 8081 only on the tailnet interface so the LAN cannot reach it:

```bash
# nftables example
nft add rule inet filter input iifname "tailscale0" tcp dport 8081 accept
```

## 3. Cloud side (Coolify application)

Set these on the `quantum-llama-web` application and redeploy:

| Variable | Value |
| --- | --- |
| `MT5_BRIDGE_URL` | `http://<local-tailnet-ip>:8081` |
| `MT5_BRIDGE_TOKEN` | the same token used locally |
| `MT5_AUTO_LAUNCH` | `false` (already set) |

The container reaches the tailnet address through the host, so no extra
routing is required when Tailscale runs on the VPS.

## 4. Verify end to end

```bash
curl -s https://llama.nbmsystemas.com/api/account      # balance from MT5
curl -s https://llama.nbmsystemas.com/api/positions    # open positions
curl -s https://llama.nbmsystemas.com/api/symbols      # symbols resolved from MT5
```

`/api/connection/status` should report `connected` and the platform MT5.

## Troubleshooting

| Symptom | Cause |
| --- | --- |
| `401 invalid bridge token` | `MT5_BRIDGE_TOKEN` differs between bridge and application |
| `503 Could not connect to MT5` in the cloud | Bridge down, MT5 terminal not logged in, or `MT5_BRIDGE_URL` unreachable from the container |
| Bridge reachable locally but not over Tailscale | Bridge bound to `127.0.0.1`; set `MT5_BRIDGE_BIND=0.0.0.0` |
| Orders rejected (`Invalid volume`/`Invalid stops`) | Broker symbol rules; check the sizing values shown in the order panel |

## Security notes

- The token travels inside the encrypted tailnet; do not use the bridge over
  plain internet.
- Rotate the token by changing it on both sides and redeploying the
  application.
- The bridge has no per-user accounts: anyone with the URL and token has full
  trading access to the logged-in terminal.
