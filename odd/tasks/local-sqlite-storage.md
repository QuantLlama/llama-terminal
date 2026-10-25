# Local SQLite storage, cloud PostgreSQL unchanged

The operator runs the platform locally and wants local data to stay local: reading
the cloud PostgreSQL through an SSH tunnel costs ~200 ms per query, which makes
the local app feel broken. Branch: `feat/local-sqlite-storage`.

## Specs

- **S1** — User: *"cuando yo ejecuto mi plataforma en local no desde la nube quiero que todo sea
  local menos el login… pero el resto lo de la base de datos que utilice la sqlite como antes en
  local"*. Local runs use SQLite for every per-user table; authentication still goes to Supabase.
- **S2** — User: *"pero que en modo cloud siga como ahora"*. The cloud deployment keeps using
  PostgreSQL through `DATABASE_URL`, unchanged and by default.
- **S3** — User: *"noto que es mas lento utiliznado desde local para leer la del vps"*. Measured:
  tunnel connect 1158 ms, 202 ms per trivial query, ~2 s for a ten-query screen. Local SQLite must
  remove that round trip.
- **S4** — User: *"no se hace una copia del remoto y pasalo a local"*. The existing cloud rows
  (settings, workspaces, broker accounts with their encrypted blobs) are copied into the local
  SQLite so the operator does not start from an empty app.

## Tasks

| ID | Spec | Task | Route | Commit |
| --- | --- | --- | --- | --- |
| T1 | S1, S2 | `SqliteUserRepository` implementing the full 25-method contract, plus backend selection in `get_repository()` behind `QLLAMA_STORAGE` | inline + TDD | `feat(storage): sqlite repository for local runs` |
| T2 | S4 | `scripts/migrate_cloud_to_sqlite.py`: copy the cloud rows into the local SQLite, idempotent, blobs verbatim | inline + TDD | same unit |
| T3 | S1, S3 | Verification: local app answers from SQLite in milliseconds and shows the migrated accounts | inline | evidence only |
| T4 | S1, S2 | Document the switch and its risk in `docs/DATA.md` | inline | `docs(data): local sqlite mode` |

## Log

- **L1** — *"ahora no me gusta algo lo de cuando yo ejecuto mi plataforma en local no desde la nube
  quiero que todo sea local menos el login vcclar oque se nesecita para logearse pero el resto lo de
  la base de datos que utilice la sqlite como antes en local pero que en modo clud siga com oahora
  porque te digo porque noto que es mas lento utiliznado desde local para leer la del vps.- anets en
  m,odo local era mucho mas rapida todo n ose hace una copia del remoto y pasalo a local"*
- **E1** — Measured on 2026-10-25 through the tunnel: connect 1158 ms, 202 ms per trivial query,
  179 ms for a real count, ~2 s for a ten-query screen.
- **E2** — `d0663e5 fix(security): isolate per-user state in Postgres behind the token` removed the
  SQLite path on purpose. This feature reintroduces it behind an explicit switch, so the cloud keeps
  one source of truth and only the local operator opts in.
- **E3** — Decision recorded: the cheaper option A (a cloned local PostgreSQL, same speed, zero new
  code) was offered and declined by the operator, who chose real SQLite.
