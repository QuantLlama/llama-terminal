# Crypto tape and DOM live in the cloud deployment

Make the crypto tape (recent trades) and the DOM (order book) deliver data in the
cloud deployment, keep the market-data feed self-healing after the operator
machine goes away, and stop the two local bridges from depending on the encrypted
external volume. Branch: `fix/crypto-tape-dom-live`.

## Specs

- **S1** — User: *"nesecito que veamos porque la plataforma no recibe datos,-.en crypto y mt5?, y
  te pregunto tengo que inicar algo yo manual cada dia que apaga mi pc y entro a la plataforma web
  o se hace solo, todo?"*. Explain the real cause of the missing data on both platforms and state
  whether a manual daily start is required.
- **S2** — User: *"CRYPTO ME LEE LOS SIMBOLO ABRE GRAFICOS TODO PERO LA CINTAS y dom no reciben
  datos en el remoto del vps"*. In the cloud deployment, crypto symbols resolve, charts open, but
  the tape and the DOM stay empty. Both must receive data.
- **S3** — User: *"si esos system estan en el disco secundario es porque esta encriptado y nesecita
  password para lebanta tenes que pasarlo al local.- asi no me hace mas eso"*. The two local
  systemd bridges must not depend on the encrypted external volume to start.
- **S4** — User: *"NO EL REPO ENTERO NO ... LA IDEA NO ES USARLO EN LOCAL POR AHORA A LA PLATAFORMA
  QUIERO USARLA DE LA NUBE"*. The repository stays on the external volume; only the bridge runtime
  moves to the local disk. The platform keeps running in the cloud.
- **S5** — User: *"deja todo funcioando como un reloj suizo sin problemas.- y retrasos grande de
  lataency porfavor"*. Leave the deployment working end to end, with no large latency spikes in
  the market-data path.

## Tasks

| ID | Spec | Task | Route | Commit |
| --- | --- | --- | --- | --- |
| T1 | S2, S5 | Public market-data connector (`src/live/crypto_public_connector.py`) so the crypto tape and DOM do not depend on an active trading tenant, plus the MDE fallback that uses it | inline + TDD | `feat(crypto): serve tape and dom without a trading tenant` (96fa302) |
| T2 | S2, S5 | Crypto feed resilience in `engine.py`: drop a failing connector, count failures, adaptive poll cadence instead of a fixed 80 ms | inline + TDD | `fix(feed): reconnect crypto feed and bound its poll cadence` (f84b279) |
| T3 | S3, S4 | Move the bridge runtime to `~/.local/share/qllama/runtime` with an idempotent installer and systemd units that never reference the encrypted volume | inline | `fix(ops): run the local bridges from the system disk` (cdf61c7) |
| T4 | S2, S5 | Deploy to the VPS and verify end to end: `/api/v2/feed/status` messages > 0, DOM and trades non-empty for a crypto symbol, chart latency measured | inline (`ssh`) | PR #64 merged (`d6fe06c`), deploy via Coolify |
| T5 | S1, S5 | Documentation: correct the stale `deploy/COOLIFY.md` environment table and document the bridge runtime install | inline | `docs(ops): record the real cloud env and the local bridge runtime` (3e1e663) |
| T6 | S5 | Unblock the deploy pipeline: Coolify had the server marked not functional (`unreachable_count` 66, `server_settings.is_reachable`/`is_usable` false), so every deploy answered "Server is not functional" and the sentinel deadlocked on 401 | inline (`ssh`) | `docs(ops): document the Coolify not-functional deadlock` |

## Log

- **L1** — *"nesecito que veamos porque la plataforma no recibe datos,-.en crypto y mt5?, y te
  pregunto tengo que inicar algo yo manual cada dia que apaga mi pc y entro a la plataforma web o
  se hace solo, todo?"*
- **L2** — *"si arranca cpm todo, y si esos system estan en el disco secundario es porque esta
  encriptado y nesecita password para lebanta tenes que pasarlo al local.- asi no me hace mas
  eso.- y la del vps si lo tenes la llave del ssh esta en la carpeta Descargas nombre aws fijate
  porque ya te conectaste antes.- asi que dalec con todo y deja todo funcioando como un reloj
  suizo sin problemas.- y retrasos grande de lataency porfavor"*
- **L3** — *"NO EL REPO ENTERO NO PORQUE? PORQUE QUERES MOVER EL REPO ENTERO A MI DSCO LOCAL? SI LA
  IDEA NO ES USARLO EN LOCAL POR AHORA A LA PLATAFORMA QUIERO USARLA DE LA NUBRE?"*
- **L4** — *"CRYPTO ME LEE LOS SIMBOLO ABRE GRAFICOS TODO PERO LA CINTAS y dom no reciben datos en
  el remoto del vps"*
- **E1** — Diagnosis (2026-10-25): `GET /api/v2/feed/status` on the cloud returns `status ONLINE`,
  `messages_received: 0`, `buffer.size: 0`, `symbols_subscribed ["BTC/USDT:USDT","BTC/USDC:USDC"]`.
  Charts work because `/api/history` and `/api/realtime` build a connector from the request token;
  the tape (`/api/v2/feed/trades/*`) and the DOM (`/api/v2/feed/dom/*`, `/api/v2/ws/feed`) only read
  the MarketDataEngine, whose crypto poll returns early when `get_active_user_id()` is empty
  (`src/services/active_tenant.py`), which is the state after every container restart.
- **E2** — The cloud env is *not* what `deploy/COOLIFY.md` says: the container has
  `MT5_BRIDGE_URL=http://10.0.0.1:8081`, a matching `MT5_BRIDGE_TOKEN` and
  `CRYPTO_HTTP_PROXY=http://10.0.0.1:3128`; both relays on the VPS are active and the MT5 relay
  answers `200` from inside the VPS.
- **E3** — Latency measured 2026-10-25: VPS→bridge `~0.53 s` per request, local direct `~0.015 s`,
  tailnet RTT `~176 ms`. The fixed 80 ms crypto poll can never complete a round trip through that
  relay, so polls overlap and starve the socket.
- **E4** — The two bridge units use `WorkingDirectory=/run/media/pabloezm/Respalados/...`
  (`/dev/sda1`, LUKS, mounted by udisks after login). On 2026-10-25 the mount appeared ~18 minutes
  after boot; the crypto proxy reached restart counter 106 and the MT5 bridge logged ~339 start
  attempts, all `status=200/CHDIR`.
- **E5** — Fixed (T3): the bridges now run from `~/.local/share/qllama/runtime`, installed by
  `scripts/install_bridge_runtime.sh` (`--check` reports drift) with `StartLimitIntervalSec=0`.
  Verified live: both processes report that `cwd`, no runtime file references `run/media`, and the
  bridge answered `200` 18 s after the restart.
- **E6** — The deploy pipeline was dead before any code reached it: `servers.unreachable_count` was
  66 and `server_settings.is_reachable`/`is_usable` were `false`. The manual GitHub webhook answered
  `{"status":"failed","message":"Server is not functional"}` and the sentinel got `401` on every
  push, which is also why the counter could never recover. Reset the counter and both settings in
  one go; a partial reset re-enters the deadlock.
- **E7** — `TCP_NODELAY` on both VPS relays did not move the measured bridge latency
  (0.534-0.544 s before, 0.539-0.558 s after). The floor is the ~176 ms tailnet RTT plus the MT5
  call under Wine, so MT5 chart latency has to come from the engine buffer, not from the relay.
- **E8** — Verified in production after deployment 40 (`finished`):
  `GET /api/v2/feed/status` reports `status ONLINE`, `messages_received` growing (27 → 47 over
  16 s), `buffer.size` 295 → 483, `errors_count 0`; `GET /api/v2/feed/dom/BTCUSDT` returns 5 bids
  and 5 asks with live prices; `GET /api/v2/feed/trades/BTCUSDT` returns 50 trades, stable in 8
  consecutive samples, with the `size`/`side`/`trade_id` shape `useTradeStream.js` consumes.
  The earlier 50/0 oscillation was the freshly started container, not a second worker (the image
  runs a single uvicorn process).
- **E9** — Feed latency with a reused connection is ~0.19 s per request (`/feed/status`,
  `/feed/trades`, `/feed/dom` alike), which is this operator link's ~176 ms RTT: the endpoints read
  the engine buffer and add no per-request bridge call. A cold connection pays ~0.58 s for the
  handshake, which is what a per-request `curl` measures.
