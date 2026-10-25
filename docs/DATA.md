# Data storage and tenant boundaries

This page describes where the platform keeps state, which identifier owns each
row, and what happens when the database is not configured. It is written for the
operator who deploys the API and for the next engineer who touches storage.

## One system of record: PostgreSQL

All per-user state lives in PostgreSQL. The connection string comes from the
`DATABASE_URL` environment variable and is read at request time.

| Variable | Meaning |
| --- | --- |
| `DATABASE_URL` | PostgreSQL DSN for per-user storage. Required for `/api/config`, `/api/workspace/*`, AlgoLab state, AlgoLab chat history and `/api/accounts/*`. |
| `QL_LEGACY_IMPORT_USER_ID` | Account that receives the one-time legacy imports (SQLite rows and `*_accounts.json` files). |
| `QL_CREDENTIAL_MASTER_KEY` | Installation master secret the per-user broker-credential keys are derived from. |
| `QUANTUM_LLAMA_KEY_DIR` | Writable directory holding the Fernet key material when `QL_CREDENTIAL_MASTER_KEY` is unset. |
| `QL_DISABLE_LEGACY_SQLITE_IMPORT` | Set to `1`/`true`/`yes`/`on` to skip the one-time SQLite import described below. |

`psycopg2-binary` is the driver (`requirements.txt`, `requirements.ci.txt`). It is
imported lazily, so a process that never touches storage does not need it loaded.

### When `DATABASE_URL` is missing

The cloud deployment has one source of truth: PostgreSQL. Without `DATABASE_URL`
the app does not silently fall back to a file. `db_get_settings`, workspace reads
and writes, AlgoLab state and chat history raise `DatabaseNotConfigured`, and the
API answers **503** with the reason instead of returning or storing shared data.
Every `/api/accounts/*` route answers the same way: broker accounts are PostgreSQL
rows, so there is no JSON file to fall back to. Startup keeps running (the lifespan
logs the error), so the failure is visible per request rather than as a silently
degraded deployment with two sources of truth.

### Local mode: an explicit SQLite switch

A workstation can run entirely from a local SQLite file, which removes the network
round trip that dominates every query when the database is remote:

| Variable | Effect |
| --- | --- |
| `QLLAMA_STORAGE` | `sqlite` serves every per-user table from a file; `postgres` forces PostgreSQL; **unset keeps today's behaviour exactly** |
| `QLLAMA_SQLITE_PATH` | SQLite file for local mode (default `config/quantum_llama.db`) |

The switch is explicit on purpose. A deployment that says nothing keeps one source
of truth in PostgreSQL, so the cloud can never fall back to a file by accident.
Authentication is not part of this: the login still goes to Supabase in both modes.

Measured on a workstation reading the cloud through an SSH tunnel: 202 ms per
trivial query and ~2 s for a ten-query screen, against **0.56 ms** from the local
SQLite file for the same call.

`scripts/migrate_cloud_to_sqlite.py` copies the cloud rows into the local file,
idempotently and with `credential_blob` verbatim (it is encrypted per user with the
installation master key, so the same `QL_CREDENTIAL_MASTER_KEY` still decrypts it).
Run it through the tunnel when you want a fresh snapshot:

```bash
python scripts/migrate_cloud_to_sqlite.py --sqlite-path config/quantum_llama.db
```

**The copy is a snapshot, not a sync.** Once local mode is on, a settings or
workspace change made locally does not appear in the cloud, and the reverse is
true. Re-running the migration brings the cloud rows over; it never pushes local
rows back.

## Schema

The schema is created idempotently on startup by `init_db()` →
`PostgresUserRepository.ensure_schema()`, which only issues
`CREATE TABLE IF NOT EXISTS`, `CREATE INDEX IF NOT EXISTS` and
`ALTER TABLE ... ADD COLUMN IF NOT EXISTS`.

| Table | Tenant key | Uniqueness |
| --- | --- | --- |
| `user_settings` | `user_id TEXT NOT NULL` | `UNIQUE (user_id)` |
| `workspaces` | `user_id TEXT NOT NULL` | `UNIQUE (user_id, session_name)` |
| `ai_chat_history` | `user_id TEXT NOT NULL` | append-only log; one row per message, indexed on `user_id` |
| `algolab_state` | `user_id TEXT NOT NULL` | `UNIQUE (user_id)` |
| `broker_accounts` | `user_id TEXT NOT NULL` | `UNIQUE (user_id, platform, account_id)` |
| `migration_state` | n/a | `name` is the primary key; records completed one-time steps |

Every table has an index on `user_id`. `ai_chat_history` is deliberately *not*
unique on `user_id`: it stores many messages per user, so a per-user unique key
would keep exactly one message. Its tenant boundary is the mandatory `user_id`
column plus a `WHERE user_id = ...` filter on every read, write and delete.

### Query rules

* Every statement is parameterized. Values, including `user_id`, are always bound
  parameters; only static column lists are interpolated into SQL text.
* No query in the repository mentions `default_user`. That value exists solely as
  the compatibility target of the one-time import.
* The facade in `src/services/database.py` takes `user_id` as a required
  keyword-only argument, so a caller that forgets it fails with `TypeError`
  instead of writing to a shared tenant.

## Who owns `user_id`

`user_id` is derived only from a validated Supabase bearer token, through
`src/services/auth.py::get_authenticated_user_id` (which reuses
`get_current_user` and `extract_user_id`). A `user_id` in a request body, query
string or header is ignored. Requests without a valid token receive **401**; when
authentication is not configured at all they receive **503**.

## Calling per-user endpoints from the browser

Every endpoint listed above (`/api/config`, `/api/workspace/*`, `/api/workspaces`,
`/api/algolab/state`, `/api/algolab/chat`, `/api/algolab/chat/history` and the whole
`/api/accounts/*` family, including `/api/accounts/brokers` and
`/api/accounts/server-search`) requires the Supabase bearer token. The browser must
send `Authorization: Bearer <access_token>` on each call, or the API answers
**401**.

`src/platform/web/lib/authFetch.js` is the only sanctioned way to call those
routes. It reads the current session from the Supabase client the page already
created (`window.supabase.auth.getSession()`), adds the header when a session
exists, and forwards every other `fetch` option untouched. With no session — or
when the session lookup fails — the request is still sent, without the header, so
the API answers 401 and logged-out flows degrade predictably instead of throwing.
The helper never logs, persists or URL-encodes the token.

```js
// correct: per-user route
const res = await window.authFetch("/api/config");

// correct: public route, token is not needed and must not be added
const res = await fetch("/api/platform/version");
```

Adding a new per-user endpoint therefore means adding its call site to the helper
path: call it with `window.authFetch(...)` and extend
`tests/test_web_auth_fetch.py`. A new public endpoint (readiness, version,
robots, sitemap) keeps plain `fetch`.

### Broker accounts

Broker accounts left the JSON files. `MT5AccountManager`, `CryptoAccountManager`,
`NinjaTraderAccountManager` and `TradovateAccountManager` read and write
`broker_accounts` through `src/services/database.py`, and every storage method
takes `user_id` as a required keyword-only argument, so one user's account list is
unreachable from another's request. Each row is `(user_id, platform, account_id)`
plus a `metadata JSONB` column for the public fields and a `credential_blob` column
for the encrypted secrets. Nothing is read from or written to `src/config` any
more, and the installation-wide `.tradovate_key` leg is gone with the file it
protected.

The blob is encrypted with a **per-user key**, derived with HMAC-SHA256 from one
installation master secret (`QL_CREDENTIAL_MASTER_KEY`, or the key file under
`QUANTUM_LLAMA_KEY_DIR` when the variable is unset) and the `user_id`. Ciphertext
written for one user therefore cannot be decrypted for another, and there is no
installation-wide account key left to leak a whole deployment at once. Losing the
master secret means every stored broker credential must be re-entered, so keep it
in the deployment secret store rather than in the image.

`GET /api/accounts`, `POST /api/accounts`, `PATCH /api/accounts/{id}`,
`DELETE /api/accounts/{id}`, `POST /api/accounts/{id}/{test,master,connect,leverage}`,
`GET /api/accounts/brokers` and `GET /api/accounts/server-search` all require the
bearer token: an anonymous call is a 401 and changes nothing, and a `user_id` in a
body or query string is ignored in favour of the token.

### Consumers of the account registry

Every caller is now either a **request path** or a **background consumer**, and the
two resolve the tenant differently on purpose:

* **Request paths** (`src/platform/api/main.py`, `accounts_api.py`,
  `footprint_api.py`) take `user_id` from `Depends(get_authenticated_user_id)` and
  pass it down to the manager and to `get_connector(account_id, *, user_id=...)`.
  There is no default and no fallback: a route that cannot name the user requires a
  token instead of guessing. An `account_id` in a request body is only a selection
  and is checked against the caller's own rows.
* **Background consumers** - the crypto account monitor, the market-data engine,
  the order gateway and the NinjaTrader replicator - have no request context. They
  read the **active trading tenant** from `src/services/active_tenant.py`
  (`get_active_user_id()`), which only an authenticated action sets: selecting a
  master account (`POST /api/accounts/{id}/master`) or connecting an account
  (`POST /api/accounts/{id}/connect`). While it is empty they skip their work and
  emit one log line per consumer, and the crypto monitor reports no account to the
  UI, so no health or status surface can claim a phantom account.

An owner who stops trading clears the holder (`clear_active_user_id()`), which
stops every background loop; the process never falls back to `default_user` or to
"the first row in the table", because either would trade somebody else's account.

Because those routes now require a token - `/api/modify`, `/api/symbols`,
`/api/symbol_info`, `/api/timeframes`, `/api/history`, `/api/deals`,
`/api/positions`, `/api/account`, `/api/realtime`, `/api/realtime_batch` and
`/api/order` - their browser call sites have to send the bearer header too.
`src/platform/web/index.html` does, through `window.authFetch`. Still on bare
`fetch` (follow-up required, outside this change's edit surface):
`components/ChartPane.js` (`/api/timeframes`, `/api/history`),
`components/PositionOverlay.js` (`/api/modify`, `/api/order`),
`components/PerformanceModal.js` and `components/HistoryPanel.js` (`/api/deals`),
`components/VixCorrelationPanel.js` (`/api/history`) and
`components/AlgoPanel.js` (`/api/accounts`). Until those move to the helper they
answer 401 for a logged-in session.

**Still not tenant scoped (follow-up required, outside this change's edit
surface):**

* `src/live/tradovate_connector.py:123` (`get_tradovate_connector`) still calls
  `get_account_full(account_id)` without a tenant, so a per-user route cannot open a
  Tradovate session yet: `test`, `connect` and `leverage` for Tradovate answer
  **503** ("connectors do not accept per-user credentials yet") instead of resolving
  credentials for the wrong user. The crypto connector (`get_connector`) does take
  `user_id`.
* `src/live/live_trade.py:135` calls `get_connector(account_id)` and
  `get_tradovate_connector(account_id)` from the local CLI runner, so that runner
  must pass a tenant (or set the active tenant) before it can trade again.

## One-time legacy import

`init_db()` calls `PostgresUserRepository.import_legacy_sqlite()` with the SQLite
path the previous release used (`config/quantum_llama.db` in development,
`%APPDATA%/Quantum Llama/data/quantum_llama.db` in a bundled build).

Behaviour:

1. The file is opened read-only; if it is absent the step is skipped, and if it
   is unreadable or not a SQLite database it is skipped with a log line — startup
   never crashes on it.
2. A marker row is inserted into `migration_state` (`legacy_sqlite_default_user_v1`)
   inside the same transaction as the copied rows. If the marker already exists
   the step returns `skipped_already_applied` and changes nothing, so the import
   runs at most once even across restarts and partial failures.
3. Legacy rows are copied under `default_user`, whatever tenant column the old
   file contained.
4. Inserts use `ON CONFLICT ... DO NOTHING`, so rows that already exist in
   PostgreSQL are never overwritten.
5. Operators who want to skip the import entirely set
   `QL_DISABLE_LEGACY_SQLITE_IMPORT=1` before starting the API.

The imported `default_user` rows are a compatibility bridge, not an account:
authenticated users have their own rows and never fall back to that namespace.

### One-time broker-account import

`init_db()` also imports the JSON account files the previous release wrote
(`src/config/mt5_accounts.json`, `src/config/crypto_accounts.json`,
`src/config/nt8_accounts.json`; inside a container that is `/app/src/config`, which
is **not** a mounted volume, which is why those files were lost on every deploy).
`src/config/tradovate_accounts.json` is deliberately **not** in that list
(`database.BROKER_PLATFORMS`), because the shared file was never per-user and its
rows cannot be attributed to an owner: Tradovate accounts created before this
change must be entered again by their owner.

The import uses the same marker discipline as the SQLite import, with its own
marker (`legacy_broker_accounts_json_v1`):

1. Every account lands under `QL_LEGACY_IMPORT_USER_ID`, the same option used for
the SQLite rows.
2. The marker row and every account row share one transaction; a second run
returns `skipped_already_applied` and changes nothing.
3. Inserts use `ON CONFLICT (user_id, platform, account_id) DO NOTHING`, so rows
that already exist in PostgreSQL are never overwritten.
4. A missing or unreadable file is skipped with a status instead of crashing, and
an import where nothing was readable leaves the marker untouched so a later
restart can still succeed.
5. Legacy secrets are re-encrypted under the owner's per-user key when the old
installation key file is still present. When it is gone the account is still
imported with an empty credential blob and the credentials must be re-entered;
nothing undecryptable is ever stored.

## Tests

`tests/test_database_postgres.py` drives the real repository against a fake
DB-API connection (`FakePostgres`) that records SQL text and bound parameters, so
schema, parameterization and tenant filters are asserted without a real database.
`tests/test_tenant_isolation.py` composes the real route handlers with a stubbed
Supabase client and the same fake store to assert 401s, cross-tenant isolation and
client-supplied `user_id` rejection on HTTP responses. `tests/test_accounts_repository.py`
covers the `broker_accounts` schema, the mandatory `user_id`, the per-user key
derivation and the JSON import; `tests/test_accounts_isolation.py` does the same
for every `/api/accounts/*` route. `tests/test_active_tenant.py` pins the
active-tenant holder and proves, for each background consumer, that it neither
raises nor touches an account while the holder is empty and that it uses exactly
the id the holder carries otherwise. `tests/test_accounts_consumers.py` drives the
trading, footprint and accounts routes through the real handlers and managers, and
then asserts structurally (AST) that no consumer passes an account call without a
resolved tenant, defaults a tenant parameter, reads the ambient tenant from a
request path, or reintroduces a `default_user` literal; it also checks that every
`/api/accounts` call site in the browser sources uses `window.authFetch`. No test
opens a socket or a real database connection.

## Migrating a desktop installation to one hosted account

The desktop app stored workspaces and settings in `config/quantum_llama.db`
(SQLite). The hosted platform imports that file once at startup, and by default
the rows land under the historical `default_user` placeholder.

An owner who wants their existing local data attached to their own web identity
sets one variable before the import runs:

```
QL_LEGACY_IMPORT_USER_ID=<their Supabase user id>
```

Validation: the value must be a single identifier of at most 128 characters with
no whitespace or path separators; an empty value keeps the default, and an
invalid one fails loudly rather than writing rows under a wrong tenant.

Procedure:

1. Copy the desktop `quantum_llama.db` into the deployed container's persistent
   data directory (`/app/config/quantum_llama.db`). It is the same path the
   desktop build used, so nothing is renamed.
2. Set `QL_LEGACY_IMPORT_USER_ID` to the account that should own the data.
3. Restart the application. The import runs once inside a transaction guarded by
   a marker row, inserts with `ON CONFLICT DO NOTHING`, and never overwrites
   existing Postgres rows.
4. Remove `QL_LEGACY_IMPORT_USER_ID` afterwards; the marker makes a second run a
   no-op, and `QL_DISABLE_LEGACY_SQLITE_IMPORT=1` disables it entirely.

The file contains broker credentials, so it must be placed by the operator and
must never be committed, uploaded to a third party or pasted into a chat.
