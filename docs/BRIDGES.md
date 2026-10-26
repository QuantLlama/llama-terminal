# Connect your own machine: the two bridges

The web platform runs in the cloud, but two things only exist where **you** are:
your MetaTrader 5 terminal and a network path to the crypto exchanges. This page
is the step-by-step to connect them. If you only need charts and backtesting, you
do not need either bridge.

## Quick path

1. **Decide which bridges you need** with the table below.
2. **Install the runtime** on the machine that has the terminal:
   `./scripts/install_bridge_runtime.sh`
3. **Start them** as user services and copy the two values (URL + token) into the
   deployment's environment, then redeploy.
4. **Verify** with the commands in [Verification](#verification).

## Which bridges do I need?

| You want | MT5 bridge | Crypto proxy | Why |
| --- | --- | --- | --- |
| MT5 charts, orders, account data | ✅ required | — | The MT5 terminal is Windows software; the cloud talks to it over HTTP |
| Crypto charts only | — | ⚠️ only if your region is blocked | Binance answers `HTTP 451` to the cloud provider's region |
| Crypto tape and DOM | — | ⚠️ same as above | The feed polls public endpoints from the container |
| Both | ✅ | ✅ | The usual setup |

The **MT5 bridge** is the piece that needs Windows underneath, because the
`MetaTrader5` Python package only exists for Windows. The **crypto proxy** is
plain `python3` and runs on anything.

| Your machine | MT5 bridge | Crypto proxy |
| --- | --- | --- |
| Windows | ✅ native | ✅ native |
| Linux | ✅ with Wine (MT5 terminal under Wine) | ✅ native |
| macOS | ⚠️ only with Wine or a Windows VM | ✅ native |

## 1. The MT5 bridge

It exposes `mt5_server.py` over HTTP so the platform can read the account, place
orders and pull candles from your terminal.

### Windows

```bat
REM 1. Python inside the same environment as the MetaTrader5 package
pip install MetaTrader5 fastapi uvicorn pandas pytz

REM 2. Shared token: generate it once and keep it
python -c "import secrets; print(secrets.token_urlsafe(32))"

REM 3. Start the bridge, reachable from your private network
set MT5_BRIDGE_BIND=0.0.0.0
set MT5_BRIDGE_TOKEN=<the token you just generated>
start_mt5_server.bat
```

MetaTrader 5 must be **open and logged in** to the broker account. Without a
logged-in terminal the bridge answers `503` on every data route.

### Linux (MT5 under Wine)

```bash
./scripts/install_bridge_runtime.sh   # copies the runtime files and both units
systemctl --user enable --now qllama-mt5-terminal.service qllama-mt5-bridge.service
```

`qllama-mt5-terminal.service` opens the terminal inside the graphical session,
because Wine needs an X display and otherwise dies with `nodrv_CreateWindow`;
the bridge starts after it, and both come back on their own after a reboot.

The token is generated on first run and stored in
`~/.config/qllama/mt5_bridge_token`; the script prints it once so you can copy it
into the deployment. If you skip that file, set `MT5_BRIDGE_TOKEN` yourself.

### macOS

The `MetaTrader5` package does not exist for macOS. Either run the bridge inside
a Windows VM, or run MT5 and the bridge under Wine — the same procedure as Linux.
If you only trade crypto, skip this bridge entirely.

## 2. The crypto egress proxy

Some venues block the cloud provider's region (`HTTP 451 restricted location`).
This proxy lets the container reach the exchange **from your connection** instead.
It only supports `CONNECT` tunnels, and it binds to your Tailscale address so
nothing on your LAN or the internet can use it.

```bash
# Default: binds the tailnet address on port 3128
python3 scripts/local_crypto_proxy.py

# Loopback instead, for a single-machine setup
LOCAL_PROXY_BIND=127.0.0.1 LOCAL_PROXY_PORT=3128 python3 scripts/local_crypto_proxy.py
```

It has no authentication on purpose: the tailnet (WireGuard) is the trust
boundary. Never expose this port publicly.

## 3. Run both automatically (Linux)

Do not point a systemd unit at a repository that lives on an encrypted or
removable volume: the unit fails with `status=200/CHDIR` until that volume is
mounted. Install a small dependency-free copy on the system disk instead.

```bash
./scripts/install_bridge_runtime.sh           # ~/.local/share/qllama/runtime
./scripts/install_bridge_runtime.sh --check   # exit 1 when the copy is stale
# scripts/install_bridge_runtime.sh also copies the units:
# cp deploy/local/*.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now qllama-mt5-terminal.service qllama-mt5-bridge.service qllama-crypto-proxy.service
sudo loginctl enable-linger "$USER"           # start at boot, without logging in
```

Re-run `install_bridge_runtime.sh` after changing `mt5_server.py`, the
`src/live/mt5_bridge_*` modules or `scripts/local_crypto_proxy.py`. The units run
the installed copy, not the repository.

## 4. Point the cloud deployment at your machine

Your machine is not reachable from the container directly, so a small `socat`
relay on the VPS forwards to your tailnet address:

```
container -> 10.0.0.1:8081 (VPS relay) -> <your-tailnet-ip>:8081 bridge
container -> 10.0.0.1:3128 (VPS relay) -> <your-tailnet-ip>:3128 proxy
```

On the VPS, once:

```bash
sudo ./deploy/vps/setup-mt5-relay.sh            # auto-discovers your tailnet peer
sudo ./deploy/vps/setup-crypto-proxy-relay.sh
```

On the application (Coolify → Environment Variables):

| Variable | Value |
| --- | --- |
| `MT5_BRIDGE_URL` | `http://10.0.0.1:8081` |
| `MT5_BRIDGE_TOKEN` | the token from step 1 |
| `MT5_AUTO_LAUNCH` | `false` (the container has no terminal) |
| `CRYPTO_HTTP_PROXY` | `http://10.0.0.1:3128` |

Redeploy so the container picks the values up. If your tailnet address changes,
re-run the two `setup-*-relay.sh` scripts.

## Verification

Run these on the machine that hosts the bridge:

```bash
# 1. The bridge answers and sees the terminal
TOKEN=$(cat ~/.config/qllama/mt5_bridge_token)
curl -s -H "X-Bridge-Token: $TOKEN" http://127.0.0.1:8081/api/account_info

# 2. The proxy is listening on the tailnet address
ss -tlnp | grep 3128

# 3. From the VPS, the relay reaches you
ssh <vps> 'curl -s -o /dev/null -w "%{http_code}\n" \
  -H "X-Bridge-Token: <token>" http://10.0.0.1:8081/api/account_info'
```

Expected: an account JSON with your balance, a line showing `100.x.y.z:3128`, and
`200`.

In the platform itself, `GET /api/health` reports `mt5_status: connected` when the
bridge is reachable, and `GET /api/v2/feed/status` shows `messages_received`
growing for crypto.

## Troubleshooting

| Symptom | Cause and fix |
| --- | --- |
| `401 invalid bridge token` | `MT5_BRIDGE_TOKEN` differs between the bridge and the deployment. Compare `~/.config/qllama/mt5_bridge_token` with the Coolify variable |
| `503` on every MT5 route | Terminal not running or not logged in to the broker |
| `curl` to `10.0.0.1:8081` times out | Relay stopped, peer offline, or the `ufw` rule is missing. Re-run `deploy/vps/setup-mt5-relay.sh` |
| Bridge works locally, not over the tailnet | It is bound to `127.0.0.1`. Set `MT5_BRIDGE_BIND=0.0.0.0` |
| Unit fails with `status=200/CHDIR` | The unit points at a path that does not exist yet (an encrypted volume that is not mounted). Use `install_bridge_runtime.sh` |
| Crypto charts empty, MT5 fine | `CRYPTO_HTTP_PROXY` unset, or the proxy is not running |
| `451` in the container logs | The venue still sees the cloud region: the proxy is not in the path |
| Deploys answer `Server is not functional` | Coolify marked the server unhealthy. See `deploy/COOLIFY.md` |

## Running everything locally instead

If you prefer the whole platform on your own machine (no cloud, no relay, no
token), you only need the desktop build:

```bash
npm start          # Electron shell + local backend on 127.0.0.1:8050
```

`npm start` does not write anything outside the project. The Linux launchers
(menu and Desktop entries) are opt-in: set `QLLAMA_INSTALL_SHORTCUTS=1` when you
want them, or run `scripts/setup_shortcuts.sh` directly. Earlier versions created
them on every launch, which left four entries behind for anyone who just wanted
to try the app.

In that mode the bridges are optional and local: leave `MT5_BRIDGE_URL` unset so
the platform uses the terminal directly, and the crypto proxy is unnecessary
because the requests leave from your own connection. The desktop needs a `.env`
with `SUPABASE_URL` and `SUPABASE_ANON_KEY`; without them the interface stops at
`Public authentication configuration unavailable`.

## Next step

- Full topology and the security model: [`CLOUD.md`](CLOUD.md)
- Cloud deployment operations: [`../deploy/COOLIFY.md`](../deploy/COOLIFY.md)
- The guided onboarding tour: [`ONBOARDING.md`](ONBOARDING.md)

## Using the cloud database while working locally

Running the app locally needs a PostgreSQL for the per-user data (accounts,
settings, workspaces). Without `DATABASE_URL` those routes answer `503`:

```
[DATABASE] DATABASE_URL is not set. Per-user storage requires PostgreSQL;
there is no sqlite fallback for authenticated data. See docs/DATA.md.
```

Two ways out. A **local database** is isolated: you load the accounts again. A
**tunnel to the cloud database** keeps the accounts you already have, which is
what this section describes.

The cloud Postgres is a container inside the VPS docker network with no public
port, and **its address changes whenever Coolify recreates it**. Hardcoding the
address means the tunnel dies silently and every per-user route starts answering
`500`. `scripts/qllama-pg-tunnel.sh` therefore asks the VPS for the current
address on every start, finding the database through the application's own
`DATABASE_URL` instead of guessing by container name:

```bash
./scripts/qllama-pg-tunnel.sh --print-target   # show what it would forward to
```

It looks for a usable key in `~/.ssh/qllama_vps`, `~/.ssh/id_ed25519_vps`,
`~/Descargas/awspass.pem` and `~/.ssh/id_ed25519`, keeping the first that
authenticates, so moving a key does not break it. Point it at your host with an
`~/.ssh/config` entry:

```ini
Host qllama-vps
    HostName <vps-address>
    User <user>
    IdentityFile <your-key>
```

Run it as a user service so it re-resolves the address on every boot and after
every failure:

```ini
# ~/.config/systemd/user/qllama-pg-tunnel.service
[Service]
Environment=QLLAMA_VPS_HOST=qllama-vps
Environment=QLLAMA_PG_PORT=5433
ExecStart=%h/.local/share/qllama/runtime/scripts/qllama-pg-tunnel.sh
Restart=always
RestartSec=10
```

`scripts/install_bridge_runtime.sh` copies the script to that path, so install
the runtime first (see above), then:

```bash
cp deploy/local/qllama-pg-tunnel.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now qllama-pg-tunnel.service
psql "postgresql://<user>:<pass>@127.0.0.1:5433/postgres" -c 'select 1'
```

Then in `.env` (never in the repository):

```ini
DATABASE_URL=postgresql://<user>:<pass>@127.0.0.1:5433/postgres
QL_CREDENTIAL_MASTER_KEY=<contents of /app/config/keys/.broker_accounts_master_key on the cloud>
```

`QL_CREDENTIAL_MASTER_KEY` is not optional: broker credentials are encrypted per
user with it, so a different key gives you the accounts with
`DECRYPTION_FAILED` and no usable secret. The value is the same 44-byte file the
cloud keeps under `QUANTUM_LLAMA_KEY_DIR`.

Verification that does not need a login:

```bash
curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8050/api/accounts
# 401 -> the database is reachable and the route wants a session
# 503 -> DATABASE_URL is still missing or the tunnel is down
```
