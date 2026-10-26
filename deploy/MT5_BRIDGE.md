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

Linux with Wine (MT5 running under Wine, Python inside the same prefix). The two
units from `deploy/local/` are the supported path: the bridge must be running,
and the terminal is **booted on demand** — see [When does MT5 open?](#when-does-mt5-open).

```bash
./scripts/install_bridge_runtime.sh   # copies the runtime files and the units
systemctl --user enable --now qllama-mt5-bridge.service
```

The installer disables `qllama-mt5-terminal.service`, so MT5 does not open at
login. To open the terminal yourself, either launch MetaTrader 5 normally or:

```bash
systemctl --user start qllama-mt5-terminal.service
```

### When does MT5 open?

`mt5.initialize()` is what launches `terminal64.exe` when nothing answers, so the
bridge is the only component that can open a terminal by itself. That boot is
authorised by a short **demand lease**, never by polling:

| Signal | Effect |
| --- | --- |
| A browser or desktop session of the platform is connected | renews the lease every `MT5_TERMINAL_DEMAND_RENEW` seconds (default `30`) |
| Market-data polling, a running algorithm, a container restart, login | never renews it |
| The last session closes | the platform releases the lease immediately (`DELETE /api/terminal/demand`), so no background poll boots a terminal in the gap |
| No session for `MT5_TERMINAL_DEMAND_TTL` seconds (default `120`) | the lease also lapses on its own if the release cannot be delivered |
| A terminal you opened by hand | served exactly as before, with or without a lease |

The gate answers "is a terminal already running?" from the process table via
`psutil`. When that answer is unavailable it withholds the boot instead of failing
open, because failing open is the polling loop this removes.

The platform never closes the terminal: once it runs it stays until you close it.
Inspect the state without booting anything:

```bash
curl -s -H "X-Bridge-Token: <your token>" http://127.0.0.1:8081/api/terminal/status
# {"terminal_running": false, "session_alive": false, "demand_active": false, "demand_remaining_seconds": 0.0}
```

To run it by hand instead:

```bash
export MT5_BRIDGE_BIND=0.0.0.0
export MT5_BRIDGE_TOKEN=<your token>
./scripts/start_mt5_terminal.sh    # resolves the X display, starts terminal64.exe
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

Because Tailscale drops traffic that reaches a tailnet address from a
non-tailnet interface, the container cannot dial `100.x.y.z` directly. The VPS
runs a small relay from the Docker bridge gateway to the tailnet peer:

```
container -> 10.0.0.1:8081 -> socat -> <local-tailnet-ip>:8081
```

Install or update it on the VPS (auto-discovers the single online peer):

```bash
sudo ./deploy/vps/setup-mt5-relay.sh
# or explicitly
sudo ./deploy/vps/setup-mt5-relay.sh 100.101.102.103
```

The script installs `socat`, writes `/etc/default/qllama-mt5-relay`, enables
`qllama-mt5-relay.service` and opens `10.0.0.1:8081` to the Docker subnet only
(`ufw allow from 10.0.0.0/24`). Re-run it whenever the peer address changes.

Set these on the `quantum-llama-web` application and redeploy:

| Variable | Value |
| --- | --- |
| `MT5_BRIDGE_URL` | `http://10.0.0.1:8081` |
| `MT5_BRIDGE_TOKEN` | the same token used locally |
| `MT5_AUTO_LAUNCH` | `false` (already set) |

Do not point `MT5_BRIDGE_URL` at a tailnet address: the container has no route
to it and the request times out.

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
| Container gets `HTTP 000` / timeout against `10.0.0.1:8081` | Relay stopped, peer offline, or ufw rule missing: re-run `deploy/vps/setup-mt5-relay.sh` |
| Orders rejected (`Invalid volume`/`Invalid stops`) | Broker symbol rules; check the sizing values shown in the order panel |

## Security notes

- The token travels inside the encrypted tailnet; do not use the bridge over
  plain internet.
- Rotate the token by changing it on both sides and redeploying the
  application.
- The bridge has no per-user accounts: anyone with the URL and token has full
  trading access to the logged-in terminal.

## Running the local pieces as services

The MT5 bridge and the crypto egress proxy run on the operator machine. They
must not depend on the repository path: the repository usually lives on an
encrypted removable volume, and a unit whose working directory is there fails
with `status=200/CHDIR` until that volume is unlocked (`systemd` reports
`Changing to the requested working directory failed: No such file or directory`).

Install the runtime files on the system disk first, then the units:

```bash
./scripts/install_bridge_runtime.sh            # copies to ~/.local/share/qllama/runtime
./scripts/install_bridge_runtime.sh --check    # exits 1 when the copy is stale
mkdir -p ~/.config/systemd/user
# scripts/install_bridge_runtime.sh also copies the units:
# cp deploy/local/*.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now qllama-mt5-bridge.service qllama-crypto-proxy.service
sudo loginctl enable-linger "$USER"   # keep them running without an active login
```

`qllama-mt5-terminal.service` is installed but deliberately **not enabled**: the
bridge boots the terminal on demand while a platform session is open, and a
terminal that comes back at login or after being closed is what made MT5 look
like it started by itself. Start it by hand with
`systemctl --user start qllama-mt5-terminal.service`.

Re-run `install_bridge_runtime.sh` after changing `mt5_server.py`, the
`src/live/mt5_bridge_*` modules (including `mt5_terminal_demand.py`) or
`scripts/local_crypto_proxy.py`; the units keep running the installed copy, not
the repository. The bridge retries forever (`StartLimitIntervalSec=0`) because it
is the cloud deployment's only route to MT5 and the exchange.

Check them with `systemctl --user status qllama-mt5-bridge qllama-crypto-proxy`
and follow logs with `journalctl --user -u qllama-mt5-bridge -f`.

## Crypto egress when the venue blocks the server region

Binance answers `HTTP 451 (restricted location)` to this deployment's AWS
region while the operator connection is allowed. The crypto traffic is routed
through a CONNECT proxy on the operator machine instead of moving the server:

```
container (CRYPTO_HTTP_PROXY=http://10.0.0.1:3128)
   -> socat relay on the VPS
   -> <operator-tailnet-ip>:3128 CONNECT proxy
   -> venue
```

Install the relay on the VPS with `sudo ./deploy/vps/setup-crypto-proxy-relay.sh`
and set `CRYPTO_HTTP_PROXY` on the application. Only crypto traffic uses it, so
MT5, Supabase auth and market data keep their normal path.
