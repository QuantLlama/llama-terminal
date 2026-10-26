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
| T4 | S1-S4 | Verification: focused suites, full suite, then machine activation (needs operator authorization: systemd units live outside the repository) | inline | PARTIAL: full suite 786 passed / 1 skipped; independent verifier all-MET; machine activated; native review blocked at the targeted-validator slot (unburned authority) |

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

### L7 — native review and correction

Lineage `review-5ec1c719957cc28a` (tier high, 4 lenses: risk, resilience, readability,
reliability; 15 paths, 1060 original lines, correction budget 200). The four lens
reviewers admitted their findings, and the refuter corroborated three
candidate-caused CRITICAL findings, all in the delivery slice:

| Finding | Claim | Correction |
| --- | --- | --- |
| R3-001, R4-001 | An on-demand terminal is a child of the bridge cgroup; with the terminal unit no longer pulled in, the routine bridge restart killed MT5, so the platform closed a terminal the operator did not close (violates S3) | `KillMode=process` on `qllama-mt5-bridge.service`; test asserts it |
| R4-002 | The installer printed "autostart disabled" unconditionally after a silent `disable || true`, hiding a failed disable | installer reads `is-enabled`, disables only when needed, and reports a still-enabled failure |

Correction committed as `2230745` (37 diff lines, inside the 200 budget). RED first:
2 new assertions failed, then 7/7 in `tests/test_mt5_terminal_units.py`; full suite
786 passed / 1 skipped. `corrected_candidate_unavailable` was resolved by committing
the correction, as the review is `committed-only`.

### L8 — review blocker and activation deviations

- The targeted-validator slot (`provider_targeted_validator`, revision
  `sha256:7ef10812…`, request `sha256:7cf1a927…`) was offered again by a fresh bound
  STATUS after the correction, and its capture was rejected twice:
  `capture-binding-rejected: collectBinding is missing or stale for current STATUS`
  (once without `validationRequest`, once with the complete binding; the forecast for
  the same binding was accepted and authorised one relayed run). No verdict was
  invented and nothing further was submitted. Authority stays at `correction_required`
  and is not burned, so this candidate has **no native approval**; delivery remains the
  operator's decision.
- Activation deviation, reported honestly: the earlier plan was
  `systemctl --user disable --now qllama-mt5-terminal`. Between the question and the
  execution the unit had become the owner of a live `terminal64.exe`, so `--now` would
  have closed MT5 (against S3). Only `disable` was run. `install_bridge_runtime.sh`
  installed the units and the runtime copy, and the bridge was restarted to load the
  gate; that restart closed the terminal the bridge owned at the time, which is exactly
  the defect R3-001/R4-001 describe and `2230745` fixes.
- Live state after activation: `qllama-mt5-terminal` disabled and inactive,
  `qllama-mt5-bridge` active, MT5 not running, and
  `GET /api/terminal/status` returns `{"terminal_running": false, "session_alive":
  false, "demand_active": false}` with no operator session open. That is S2 satisfied:
  nothing boots the terminal until a platform session is connected.

### L9 — second review lineage, second correction

Lineage `review-4b9906f1a80227b7` (target `sha256:4e49ce6…`, tier high, same four
lenses, 15 paths, 1134 original lines). The four lenses and the refuter ran; the
refuter corroborated four candidate-caused CRITICAL findings, two of them defects
in the previous correction:

| Finding | Claim | Correction |
| --- | --- | --- |
| R3-001, R4-001 | `systemctl --user is-enabled` exits non-zero both for a disabled unit and for an unreachable user bus, so the installer read a broken probe as "already disabled" and could report success with the unit still enabled | the unit state is decided from the command's text; only an explicit disabled-family answer counts, unreadable is reported as unknown |
| R4-002 | The lease outlived the last session by its full TTL, so one background poll inside that window booted a terminal for nobody | the last disconnect now sends `DELETE /api/terminal/demand`; the bridge revokes the lease immediately and terminates nothing |
| R4-003 | `allow_terminal_boot` treated an unreadable process probe as authorisation, recreating the polling boot loop on a runtime without `psutil` | an unknown probe withholds the boot and logs it; `psutil` is a declared deploy dependency |

Correction committed as `5afcbcc` (195 diff lines, inside the 200 budget), RED
first (6 new or changed assertions failed), full suite afterwards: **791 passed,
1 skipped**.

Ordering note: the correction plan must be declared before the fixing commit,
because a commit moves the candidate target and the plan slot then points at a
target that no longer exists. The first attempt committed first and the slot was
rejected. `git reset --soft HEAD~1` restored the served target, the plan was
accepted at 195 lines, and the same content was committed again.

### L10 — blocked: the targeted-validator slot cannot be captured

`provider_targeted_validator` (request `sha256:4b09b6b7…`, correction target
`sha256:94c416e0…`, expected revision `sha256:58fd287a…`) was offered by a fresh
bound STATUS, its **forecast was accepted** (one relayed `review-validator` run
authorised), and the acknowledged submission was then rejected with
`capture-binding-rejected: collectBinding is missing or stale for current STATUS`.

The same shape blocked lineage `review-5ec1c719957cc28a` earlier in this session,
where the slot was re-offered by a fresh STATUS and rejected twice (once without
`validationRequest`, once with the complete object). Two independent lineages, the
same slot, the same rejection, a forecast accepted each time: this is a defect in
the validator slot, not a binding this session can repair by retrying or by
hand-writing provider tokens.

Consequence, stated plainly: **neither lineage reached approval.** Both stopped at
`correction_required` with their authority unburned, so this candidate carries no
native review approval. A maintainer has to inspect the review authority, or the
provider has to be fixed, before a review of this range can complete. Delivery
(commit, push, PR, merge) remains the operator's decision and is not authorised by
anything in this document.
