# MT5 terminal on demand

Make the MT5 terminal start only while a browser session is open or when the
operator opens it manually. It is never started by background polling, never
started at login, and never closed by the platform.

## Specs

- **S1 — Request.** The operator reported: "tengo un problema que cuando no utilizao la plataforma me sigue abriendo mt5 a cada momento y eso no puede pasar solo cuando yo utilzce la plataforma o quiera abrir yo mismo el mt5 pero no que se inicie solo".
- **S2 — What counts as use.** Operator selected: "Solo la web abierta". The trade terminal may be booted only while a browser/desktop session of the platform is connected (the platform's WebSocket connections). Background market-data polling, a running live algorithm, container restarts and login-time service start must never boot it.
- **S3 — No automatic close.** Operator selected: "No cerrar, solo no abrir". The platform must never terminate the terminal process. Once the terminal runs, it stays until the operator closes it.
- **S4 — Preserve existing contracts.** A terminal the operator opened by hand keeps being served exactly as today ("quiera abrir yo mismo el mt5"). Existing bridge routes, their payloads and their status codes are unchanged; the bridge token still guards every route; order and market-data paths are untouched. Additive routes only.

## Tasks

| ID | Specs | Outcome | Route | State / commit evidence |
| --- | --- | --- | --- | --- |
| T1 | S1, S2, S4 | Bridge: demand lease, gate that withholds the terminal boot (never blocks a route), `/api/terminal/demand` and `/api/terminal/status`; tests | inline (contract author) | DONE: `d75ac4e`; 20 tests pass |
| T2 | S1, S2, S4 | Platform: renew the lease only while browser sessions are connected; no renewal from polling or services startup; tests | inline | DONE: `29ee7b5`; 12 tests pass |
| T3 | S1, S2, S3 | Delivery: terminal unit loses `Restart=always`, bridge unit no longer pulls it in, installer stops enabling it; docs | inline | DONE: this commit; 5 unit-contract tests pass |
| T4 | S1-S4 | Verification: focused suites, full suite, then machine activation (needs operator authorization: systemd units live outside the repository) | inline | PARTIAL: full suite 784 passed / 1 skipped; docs links resolve; secret scan clean; machine activation pending operator authorization |

## Log

### L1 — operator request (verbatim)

> tengo un problema que cuando no utilizao la plataforma me sigue abriendo mt5 a cada momento y eso no puede pasar solo cuando yo utilzce la plataforma o quiera abrir yo mismo el mt5 pero no que se inicie solo

### L2 — operator decisions (verbatim labels)

- What counts as use: "Solo la web abierta" — "Web abierta → MT5 disponible; Web cerrada → MT5 no se abre (bot live queda sin feed); Polling de fondo → no abre nada".
- Idle behaviour: "No cerrar, solo no abrir" — "Se abre por demanda; Queda abierto hasta que lo cierres; Sin kill automático".

### L3 — observed evidence for the diagnosis

Three independent sources boot the terminal today:

1. `qllama-mt5-terminal.service` is `enabled` with `Restart=always`. Journal of 2026-10-26 shows the loop: `10:32:21` → `10:32:34` → `10:32:46`, a new MT5 every ~12 s whenever it was closed, plus a start at login.
2. `mt5_server.py` calls `mt5.initialize()` from `ensure_mt5_session` on every request, and the MT5 Python API boots `terminal64.exe` when no terminal answers. Journal: `MT5_CONN: session flagged connected but the terminal is gone; reinitializing` repeatedly between 13:38 and 13:41.
3. The VPS `coolify-qllama` (100.103.37.109) polls the bridge about once per second: `lifespan → startup_services` starts `MarketDataEngine` at container boot and it polls `MESZ26` forever, independent of any open UI.

`deploy/local/qllama-mt5-bridge.service` also declares `Wants=qllama-mt5-terminal.service`, so starting the bridge at login pulled the terminal unit in.

### L4 — design decisions

- The gate is a **lease**, not a request classifier: `POST /api/terminal/demand` extends it, `MT5_TERMINAL_DEMAND_TTL` (default 120 s) expires it. Polling cannot renew it because only connected browser sessions do.
- The gate **withholds the reconnect attempt**, it does not answer 503: `mt5.initialize()` is the only boot trigger, so skipping it is enough, and every existing route keeps its current payload and status code (S4).
- The probe that decides whether a terminal is already running reads the process table (`terminal64.exe` / `metatrader`) and fails open: an unreadable process table allows the reconnect, so a platform that cannot probe never silently loses a terminal the operator opened.
- No code path kills the terminal (S3). The platform's own auto-shutdown behaviour is out of scope and untouched.

### L5 — delivery slices

Feature branch `fix/mt5-terminal-on-demand`, work units committed separately so a
review can take each one alone:

| Slice | Scope | Evidence |
| --- | --- | --- |
| S1 | Bridge demand lease, boot gate, terminal routes, bridge tests | `d75ac4e` — 483 authored changed lines, `tests/test_mt5_terminal_demand.py` 20 pass |
| S2 | Platform renewal while a session is open, connector demand call, renewal tests | `29ee7b5` — 305 authored changed lines, `tests/test_terminal_demand_renewal.py` 12 pass |
| S3 | Delivered units, installer, operator docs, unit contract tests | this commit — `tests/test_mt5_terminal_units.py` 5 pass |

The first slice exceeds the ~400-line guidance (483) because the lease, the gate
and the tests that pin both are one behaviour; splitting them would land a gate
whose tests live in a later commit. S2 and S3 are independent of each other and
stay under the guidance.

The pre-existing `test_bridge_client_pool` setup errors (13, reproduced on `main`
at `7030999` for the `bridge_symbols + login_and_guide + bridge_client_pool`
combination) came from `src.services.auth` loading `.env` at import: the leaked
`MT5_BRIDGE_TOKEN` broke "no token header when unset". The fix in
`tests/test_mt5_api_connector_config.py` clears the variable, and the full suite
is green afterwards (784 passed, 1 skipped).

### L6 — verification evidence

- `tests/test_mt5_terminal_demand.py` — 20 pass (20 failed before the module and the gate existed).
- `tests/test_terminal_demand_renewal.py` — 12 pass (12 failed before the renewal loop existed).
- `tests/test_mt5_terminal_units.py` — 5 pass (4 failed before the units and the installer changed).
- Full suite: `784 passed, 1 skipped, 271 warnings in 22.43s` (the skip is a pre-existing display-discovery case that cannot fail on a machine with an X socket).
- `scripts/check_docs_links.py`: 164 relative links in 92 markdown files resolve.
- `scripts/check_secrets.py`: no secrets found (536 files scanned).
- `bash -n scripts/install_bridge_runtime.sh` and `systemd-analyze --user verify` on both units: clean.

Machine activation is NOT done by these commits: the units and the installed
runtime copy live outside the repository (`~/.config/systemd/user`,
`~/.local/share/qllama/runtime`), so it needs explicit operator authorization.
