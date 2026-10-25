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
| T1 | S2, S5 | Public market-data connector (`src/live/crypto_public_connector.py`) so the crypto tape and DOM do not depend on an active trading tenant, plus the MDE fallback that uses it | inline + TDD | `feat(crypto): serve tape and dom without a trading tenant` |
| T2 | S2, S5 | Crypto feed resilience in `engine.py`: drop a failing connector, count failures, adaptive poll cadence instead of a fixed 80 ms | inline + TDD | `fix(feed): reconnect crypto feed and bound its poll cadence` |
| T3 | S3, S4 | Move the bridge runtime to `~/.local/share/qllama/runtime` with an idempotent installer and systemd units that never reference the encrypted volume | inline | `fix(ops): run the local bridges from the system disk` |
| T4 | S2, S5 | Deploy to the VPS and verify end to end: `/api/v2/feed/status` messages > 0, DOM and trades non-empty for a crypto symbol, chart latency measured | inline (`ssh`) | deploy only |
| T5 | S1, S5 | Documentation: correct the stale `deploy/COOLIFY.md` environment table and document the bridge runtime install | inline | `docs(ops): record the real cloud env and the local bridge runtime` |

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
