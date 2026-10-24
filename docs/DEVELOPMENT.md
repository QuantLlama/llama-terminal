# Development guide

Everything a contributor needs to run the platform from source: prerequisites, the two
virtual environments, the optional bridge, the running modes, packaging and the failure
modes that cost time.

Related: [`ARCHITECTURE.md`](ARCHITECTURE.md) for how the pieces fit,
[`TESTING.md`](TESTING.md) for the test strategy, [`../deploy/MT5_BRIDGE.md`](../deploy/MT5_BRIDGE.md)
for the MetaTrader 5 bridge.

---

## 1. Prerequisites

| Requirement | Version | Why |
| --- | --- | --- |
| Python | 3.11+ | Backend, engine, ML. The container image pins 3.11 |
| Node.js | 18+ | Electron shell, Babel, packaging |
| npm | 9+ | Dependency installation |
| Git | any recent | Version control |
| C/C++ toolchain | — | Building TA-Lib and native Python wheels |
| TA-Lib C library | 0.4.x | `ta-lib` Python bindings |
| MetaTrader 5 terminal | Windows or Wine | Only if you use the MT5 venue |
| NVIDIA driver + CUDA | optional | GPU training; the platform falls back to CPU |

Per-platform notes:

- **Windows** — install the Visual Studio Build Tools ("Desktop development with C++") and a
  TA-Lib wheel.
- **Ubuntu/Debian** — `sudo apt install build-essential python3-dev libta-lib0-dev`.
- **Arch** — `sudo pacman -S base-devel ta-lib`.

---

## 2. First setup

```bash
git clone https://github.com/QuantLlama/llama-terminal.git
cd llama-terminal
```

### Environment variables

Create a `.env` file in the repository root with the variables you need. Nothing in
`.env` is committed, and the file is ignored by Git.

| Variable | Required | Purpose |
| --- | --- | --- |
| `MT5_BRIDGE_URL` | only for a remote bridge | Bridge endpoint, default `http://127.0.0.1:8081` |
| `MT5_BRIDGE_TOKEN` | yes when the bridge is not loopback | Shared secret for every bridge request |
| `MT5_BRIDGE_BIND` | remote bridge only | Interface the bridge listens on |
| `MT5_AUTO_LAUNCH` | no | `true` lets the client start the local bridge |
| `USE_MT5_API` | no | `auto` (default), `true` (HTTP bridge), `false` (native package) |
| `CRYPTO_HTTP_PROXY` | only when a venue is geo-blocked | Proxy for CCXT traffic |
| `QUANTUM_LLAMA_KEY_DIR` | containers | Writable directory for key material |
| `SUPABASE_URL`, `SUPABASE_ANON_KEY` | for authentication | Session validation. There are no compiled defaults: without both, auth-dependent routes answer `500 Supabase not configured` |
| `APP_PORT` | no | Container listen port, default `8050` |

### Browser authentication configuration

Set `SUPABASE_URL` and `SUPABASE_ANON_KEY` in the runtime environment (Coolify for
containers); do not embed project values in frontend files. The browser synchronously
loads `/api/public-auth-config.js` before the Babel app starts. This script exposes
only these two public fields and is served with `Cache-Control: no-store`.

The anon key is visible in the browser **by design**, not an administrative secret.
Use the legacy Supabase JWT with `role=anon` and `alg=HS256`; unknown formats,
missing/malformed values and administrative/service-role keys are rejected with
HTTP 503 and a nonsecret configuration error. Decoding classifies the role only;
Supabase still verifies signatures and sessions. Never set `SUPABASE_ANON_KEY` to
an administrative key. Keep Row Level Security policies enabled: hiding an anon key
is not access control. Popout windows retain their existing non-persistent,
non-refreshing session behavior.

### Python environment

```bash
./setup_env.sh          # Linux/macOS
setup_env.bat           # Windows
```

Run the Linux/macOS script from the project root. It creates or reuses `venv_linux`,
installs `requirements.txt` through that environment's Python, and records the selected
path in `.venv_linux_path`. Default reruns preserve valid environments and user files;
they still upgrade pip and install requirements. Windows uses `setup_env.bat` and `venv`;
the options below apply only to `setup_env.sh`.

If local creation fails (for example on NTFS/exFAT), setup uses
`${XDG_DATA_HOME:-$HOME/.local/share}/quantumllama/venv_linux`. The recorded fallback
is reused on subsequent runs, including paths containing spaces. XDG paths must be
absolute. A changed HOME/XDG location can invalidate an old recorded path: inspect the
pointer and environments before moving or updating them manually.

```bash
./setup_env.sh --help       # No filesystem changes or installs
./setup_env.sh --recreate   # Explicitly discard the selected valid environment
```

`--recreate` removes only the exact local or recorded fallback target after checking
ownership, venv metadata, activation file and that Python reports that environment's
prefix. Back up any user files inside it first. Unknown arguments exit with code 2
without mutations. Unsafe targets, symlinked targets or parent directories, malformed
path records and unrecognizable/broken environments are refused, even with
`--recreate`; inspect these manually rather than asking setup to delete them. Standard
venv interpreter symlinks are allowed; activation scripts are never sourced.

Creation and pip failures exit nonzero and never print `Setup complete.`. Failed
creation can leave a partial directory for manual inspection; it is not automatically
removed. Run only one setup process per project/shared XDG environment at a time, in
trusted directories (the checks are not protection against concurrent filesystem
replacement). The fallback retains the existing per-user shared environment layout.

To create the environment by hand:

```bash
python3 -m venv venv_linux
source venv_linux/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

For the container/web surface only, `requirements.deploy.txt` installs a much smaller set
(no torch, no training stack). For the test suite only, use `requirements.ci.txt`.

### Node environment

```bash
npm install
```

`npm install` is enough for `npm start`. Packaging needs the extra resources described in
section 6.

---

## 3. Running the platform

```bash
source venv_linux/bin/activate
python run.py
```

`run.py` presents the mode menu:

| Option | Mode | What it does |
| --- | --- | --- |
| 1 | Terminal app | Packaged desktop experience (expects built resources) |
| 2 | Browser mode | Starts the API and opens the default browser |
| 3 | Trainer CLI | Training, dashboards, symbol mapping, live trading, cleanup |

During development, the fastest loop is the API server plus the SPA:

```bash
python start_api.py            # uvicorn on 127.0.0.1:8050
npm start                      # Electron shell pointing at the same port
# or simply open http://127.0.0.1:8050 in a browser
```

Health check: `curl -fsS http://127.0.0.1:8050/health`.

### Ports

| Port | Service |
| --- | --- |
| `8050` (up to `8059`) | Application server |
| `8081` | MetaTrader 5 bridge |
| `8000`+ | Trainer dashboard (only in the Trainer CLI) |

---

## 4. MetaTrader 5 bridge

MetaTrader 5 cannot run inside a Linux container, so the platform talks to it over HTTP.

```bash
# On the machine that runs the MT5 terminal:
export MT5_BRIDGE_TOKEN="$(python -c 'import secrets; print(secrets.token_urlsafe(32))')"
python mt5_server.py            # listens on 127.0.0.1:8081 by default
```

- Loopback + no token is the desktop default.
- As soon as the bridge is reachable from another host, set `MT5_BRIDGE_TOKEN`; the
  bridge rejects unauthenticated calls and the API can place orders.
- Never expose the bridge to the internet. Use a private network (Tailscale is the
  documented option) as described in [`../deploy/MT5_BRIDGE.md`](../deploy/MT5_BRIDGE.md).

---

### Before you push

```bash
python scripts/check_secrets.py    # the same guard CI runs
python -m pytest -q
```

## 5. Tests

```bash
python -m pytest -q
python -m pytest tests/test_mt5_bridge_auth.py -q
```

The suite is designed to run without a broker, without network access and without
`torch`. Do not add a test that needs any of the three. See
[`TESTING.md`](TESTING.md).

---

## 6. Packaging

```bash
npm run dist       # PyArmor + PyInstaller backend, bytenode JS, electron-builder
npm run pack       # same, unpacked directory only
```

Pipeline order matters: the Electron installer picks up
`build/pyinstaller_dist/{backend,Trainer,BrowserMode}` as `extraResources`, so a JS-only
build ships a stale backend. `npm run dist` handles the order for you.

Outputs land in `dist/`: NSIS installer for Windows, AppImage and `.deb` for Linux.

---

## 7. Container (web/API only)

```bash
docker build -t llama-terminal .
docker run --rm -p 8050:8050 --env-file .env llama-terminal
```

Optional CPU inference build: `docker build --build-arg WITH_TORCH=true -t llama-terminal .`.
The container does not include the desktop shell or the MT5 terminal; see
[`../deploy/COOLIFY.md`](../deploy/COOLIFY.md) for the full topology.

---

## 8. Debugging

| Symptom | Cause | Fix |
| --- | --- | --- |
| Chart never loads, API responds | The desktop probes `/api/health`, which does not exist; the SPA fallback answers `200` | Check `/health` directly and read the backend log |
| `TA-Lib` build failure | C library missing | Install the platform package, then `pip install ta-lib` |
| `MetaTrader5` import error on Linux | Windows-only package | Use the HTTP bridge (`USE_MT5_API=true`) |
| Charts empty for MT5 symbols from a crypto session | Global platform mismatch | Switch platform, or use the per-symbol mapping |
| `PermissionError` on the key directory | Read-only container tree | Set `QUANTUM_LLAMA_KEY_DIR` to a writable path |
| Exchange returns HTTP 451 | Regional block | Configure `CRYPTO_HTTP_PROXY` |
| GPU not used | Wrong torch build or no driver | Check `torch.cuda.is_available()`; the platform falls back to CPU |
| Tests fail only on Python 3.11 with a missing attribute or stale behavior | A PyArmor/Cython `.so` from a local build sits next to the source and shadows the `.py` file (for example `src/services/security.cpython-311-x86_64-linux-gnu.so`) | Delete the `*.so` files under `src/` and the repository root — they are build artifacts, ignored by Git and excluded by `.dockerignore` |
| `pytest` skips tests you expect it to run | Collection is restricted to `tests/` | The `test_*.py` scripts at the repository root are manual probes, not suite members |

Logs are written under `logs/`; the API and the bridge both log to stdout, which is what
the container supervisor collects.

---

## 9. Repository conventions

- Branch from `main` with a type prefix (`feat/`, `fix/`, `docs/`, `ci/`, …).
- Conventional Commits; the pull request title becomes the squash-merge subject.
- One behavior per pull request, around 400 changed lines.
- Tests with the behavior, documentation with the interface change.
- English in code, comments, documentation, issues and pull requests.

Full workflow: [`../CONTRIBUTING.md`](../CONTRIBUTING.md).
