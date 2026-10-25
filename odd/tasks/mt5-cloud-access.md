# MT5 access in the cloud: one door, never a bare import

Production cannot trade and its tapes are mute. Both failures come from the same
defect: backend code imports the `MetaTrader5` package directly, but that package
is Windows-only and does not exist inside the Linux container. The bridge in front
of it (`mt5_server.py`, on the operator machine) already exposes every call the
backend needs.

## Specs

- **S1** — User: *"hay un problema en produccion, las cintas con mt5 no esta trayendo los datos en
  local si las trai"*. In production, MT5 tapes must receive data, exactly as they do locally.
- **S2** — User: *"y tampoco deja enviar ordenes no puedo comprar ni vender nada"*. In production it
  must be possible to open and close orders.
- **S3** — User: *"error modulo nome metratrader4"* / *"metarder5"*. The `ModuleNotFoundError: No
  module named 'MetaTrader5'` seen in production logs must not be able to happen again: no backend
  module outside the single access module may import `MetaTrader5`.
- **S4** — Local runs, where MT5 really is installed, keep working unchanged.
- **S5** — The connection state the UI reads must reflect the real connection after a restart, not a
  stale `disconnected` left in memory.

## Decisions

| Question | Answer |
| --- | --- |
| Where does cloud MT5 access go? | The HTTP bridge, through `MT5Connector` (`src/live/mt5_api_connector.py`) |
| Does the bridge need new routes? | No. `/api/symbol_info`, `/api/symbol_details`, `/api/current_price`, `/api/positions?ticket=` and the ticks/rates routes already exist in `mt5_server.py` |
| What shape does the access layer return? | Plain dicts with normalised keys, never an MT5 object, so both runtimes look identical to callers |
| How is recurrence prevented? | A test that fails if any module under `src/platform/api/` imports `MetaTrader5` outside the access layer |
| Scope chosen by the user | Complete: all 11 sites in `main.py` plus `footprint_api.py` |

## Tasks

| ID | Spec | Task | Route |
| --- | --- | --- | --- |
| T1 | S3, S4 | `src/live/mt5_access.py`: `symbol_info`, `symbol_tick`, `positions`, `order_size_rules`, `mt5_version`, `local_module`, `bridge_enabled`. Bridge first when `MT5_BRIDGE_URL` is set, local module only when it imports, `None` when neither works. TDD with mocked HTTP | writer + TDD |
| T2 | S3 | Recurrence guard test: no `import MetaTrader5` under `src/platform/api/` except through the access layer | writer + TDD |
| T3 | S1, S2 | Order path: `main.py` 3035 (`symbol_info_tick`), 3053 (`symbol_info`), 3130 (`positions_get`/`orders_get` by ticket) | writer |
| T4 | S1 | Data path: `main.py` 2829 (`/api/realtime`) and 777 (`order_size_rules`) | writer |
| T5 | S3 | Footprint: `footprint_api.py` 18, 27, 283, 501 | writer |
| T6 | S3 | `/debug/mt5` (2324) degrades to `bridge_enabled` + nulls instead of raising | writer |
| T7 | S5 | Startup must publish the real connection state into `_connection_state` after `startup_services` succeeds | writer |
| T8 | S1, S2 | Verify in production: batch returns ticks, an order opens and closes, tapes move | parent |

## Log

- **L1** — User: *"hay un problema en produccion, las cintas con mt5 no esta trayendo los datos en
  local si las trai"*.
- **L2** — User: *"y tampoco deja enviar ordenes no puedo comprar ni vender nada"*.
- **L3** — User: *"error modulo nome metratrader4"*, then *"metarder5"*.
- **L4** — Evidence, production logs: `POST /api/order` → 500 with
  `ModuleNotFoundError: No module named 'MetaTrader5'` and `[ORDER-CRITICAL] Internal Order Error`.
- **L5** — Evidence: `connector.connect()` posts `/api/connect` and the bridge answers `success`;
  `/api/vix/live` returns fresh data (`age 2.6s`). The bridge and the market engine are alive, so
  this is not an outage of the bridge.
- **L6** — Evidence: `_connection_state` is only written by `/api/connection/connect` and
  `/disconnect`. `startup_services` connects the engine successfully but never updates it, so after
  every container restart the UI reads `disconnected`. `index.html` only sets `connected = true`
  when that state says `connected`, and never clears it.
- **L7** — Scope decision by the user: fix all 11 sites plus `footprint_api.py`, not just orders.
