# Data storage and tenant boundaries

This page describes where the platform keeps state, which identifier owns each
row, and what happens when the database is not configured. It is written for the
operator who deploys the API and for the next engineer who touches storage.

## One system of record: PostgreSQL

All per-user state lives in PostgreSQL. The connection string comes from the
`DATABASE_URL` environment variable and is read at request time.

| Variable | Meaning |
| --- | --- |
| `DATABASE_URL` | PostgreSQL DSN for per-user storage. Required for `/api/config`, `/api/workspace/*`, AlgoLab state and AlgoLab chat history. |
| `QL_DISABLE_LEGACY_SQLITE_IMPORT` | Set to `1`/`true`/`yes`/`on` to skip the one-time SQLite import described below. |

`psycopg2-binary` is the driver (`requirements.txt`, `requirements.ci.txt`). It is
imported lazily, so a process that never touches storage does not need it loaded.

### When `DATABASE_URL` is missing

The app no longer falls back to SQLite. `db_get_settings`, workspace reads and
writes, AlgoLab state and chat history raise `DatabaseNotConfigured`, and the API
answers **503** with the reason instead of returning or storing shared data.
Startup keeps running (the lifespan logs the error), so the failure is visible per
request rather than as a silently degraded deployment with two sources of truth.

SQLite at `config/quantum_llama.db` is therefore no longer a system of record. It
is only read once by the compatibility import.

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
`/api/algolab/state`, `/api/algolab/chat` and `/api/algolab/chat/history`) requires
the Supabase bearer token. The browser must send
`Authorization: Bearer <access_token>` on each call, or the API answers **401**.

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

## Tests

`tests/test_database_postgres.py` drives the real repository against a fake
DB-API connection (`FakePostgres`) that records SQL text and bound parameters, so
schema, parameterization and tenant filters are asserted without a real database.
`tests/test_tenant_isolation.py` composes the real route handlers with a stubbed
Supabase client and the same fake store to assert 401s, cross-tenant isolation and
client-supplied `user_id` rejection on HTTP responses. No test opens a socket or a
real database connection.
