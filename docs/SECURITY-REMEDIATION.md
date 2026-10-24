# Credential exposure remediation

This is a record of what was removed, what was checked, and what still cannot be certified.
It is not a declaration that every copy of the former repository has been erased.

## Completed

- The owner explicitly authorized rewriting affected branch and tag history, without rotating credentials.
- Seventeen branch references and two tag references were updated atomically with exact old-value leases.
- A fresh download of the rewritten branch/tag history was checked across 922 reachable blob, commit and tag objects. No identified historical sensitive value remained in that scope.
- Two editable GitHub text bodies containing copied private data were sanitized. Issue, comment and release text was checked for the identified values afterward.
- Repository visibility remains private; no forks were reported during the check.
- The browser configuration was moved out of source in the security remediation PR. Its runtime endpoint exposes only an explicitly classified anon configuration, never administrative configuration. This remains subject to security review before deployment.
- The secret guard no longer skips large first-party text files. Its size-limit regression test failed before the correction and passed afterward.

## Production protection

`SUPABASE_URL` and `SUPABASE_ANON_KEY` are configured in Coolify for production and preview at runtime, not build time. They were migrated, not rotated.

Automatic deployment on `main` was enabled when the cleanup began. It was paused before rewriting remote history, without stopping the running application. Keep it paused until the browser runtime migration is reviewed and deployed deliberately.

**Do not redeploy a redacted historical snapshot expecting its former embedded defaults.** The tested runtime migration is in PR #28; a missing or privileged configuration fails closed. A health response alone does not establish that interactive login works after a new deployment.

## Remaining exposure boundaries

### GitHub-controlled references and cached views

Rewriting ordinary branches and tags does not delete GitHub's read-only PR references, cached commit views or copies in other clones. Fifteen PRs were identified as affected: #13, #15, #16, #17, #18, #19, #20, #21, #22, #23, #24, #25, #26, #27 and #28.

Follow [GitHub's sensitive-data removal procedure](https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/removing-sensitive-data-from-a-repository) and contact Support privately with:

- repository owner and name;
- the affected PR count;
- the first changed commit reported by `git-filter-repo`;
- any orphaned LFS object report, if present.

GitHub determines whether assistance is applicable, including whether credential rotation would mitigate the risk. No Support request or server-side garbage collection has been completed by this work. Do not claim those caches have been removed.

### Release downloads

The owner separately authorized deleting `QuantLlamalInstaller1.8.1.exe` (913 MB) from `QuantLlama_0.1.1.8`. The API confirmed that the legacy release now has no downloadable assets; its notes remain. The installer was removed, not certified clean. Previously downloaded copies are outside this operation.

### Existing clones and local backups

The working checkout was resynchronized while preserving human working files. Existing local stashes, old unreachable objects and other clones may retain former data. Do not push old histories back to GitHub or publish a backup. Coordinate cleanup or replacement of other clones separately.

### Unavailable proof

The independent verifier failed without a verdict. The writer's tests and CI are not a substitute for independent security approval. Keep the remediation PR unmerged and production deployment held until this is resolved by the maintainer.

## Credential policy

No credential was revoked or rotated, per the owner's instruction. A functioning credential is not evidence that no one copied it. The Supabase anon key is public browser configuration by design; that is distinct from an administrative key, signing secret, broker password or exchange API secret. Strict database access policies remain necessary.

The pattern-based secret guard and the known-value historical scan have different scopes and neither proves the absence of every possible secret. Keep the repository private until the remaining boundaries above are resolved.

## Tenant isolation for per-user storage (security item 2)

### What was broken

`src/services/database.py` stored per-user rows in SQLite at
`config/quantum_llama.db`. Its functions accepted a `user_id` and filtered by it,
but every caller in `src/platform/api/main.py` omitted the argument, so all rows
landed under the default `'default_user'`. The endpoints that used those rows —
`/api/config`, `/api/workspace/*`, AlgoLab editor state and AlgoLab chat history —
also had no authentication dependency: only `/api/auth/session` used
`Depends(get_current_user)`. Any visitor could read and overwrite every workspace
and UI setting, and every logged-in user shared one namespace.

### What changed

- Per-user storage now runs on PostgreSQL through `DATABASE_URL`
  (`src/services/user_repository.py`, documented in [DATA.md](DATA.md)). Every
  statement is parameterized and tenant-filtered; the schema enforces
  `user_id TEXT NOT NULL`, `UNIQUE (user_id)` on `user_settings` and
  `algolab_state`, `UNIQUE (user_id, session_name)` on `workspaces`, and an index
  on `user_id` for each table. SQLite is no longer a system of record.
- One dependency, `get_authenticated_user_id`, derives the tenant id only from a
  validated Supabase token. All per-user endpoints require it: `GET`/`POST
  /api/config`, `GET`/`POST /api/workspace/last-active`, `GET`/`POST
  /api/workspace/{session}`, `GET /api/workspaces`, `DELETE /api/workspace/{name}`,
  `GET`/`POST /api/algolab/state`, `GET`/`DELETE /api/algolab/chat/history` and
  `POST /api/algolab/chat`. Missing or invalid credentials return 401 and never
  reach storage.
- `user_id` supplied in a request body, query string or header is ignored; only the
  token subject is used.
- With `DATABASE_URL` unset, those endpoints fail with 503 and an explicit reason
  instead of silently writing to SQLite. The decision not to keep two sources of
  truth is recorded in [DATA.md](DATA.md).
- Pre-existing SQLite rows are copied once into PostgreSQL under `default_user`
  by an idempotent, marker-guarded import that never overwrites PostgreSQL rows and
  can be disabled with `QL_DISABLE_LEGACY_SQLITE_IMPORT=1`.

### Residual boundaries for this item

- `src/platform/api/services_api.py` exposes `GET`/`POST /api/v2/config`, which
  still calls the storage facade without a tenant. Because the facade now requires
  `user_id`, those two routes fail rather than serving shared data, but they are
  not yet authenticated and are outside the edit surface of this change.
- Browser clients must send `Authorization: Bearer <token>` on every per-user call
  listed above; unauthenticated calls now return 401 by design.
- Ground truth for isolation and migration behaviour is the offline suite
  (`tests/test_tenant_isolation.py`, `tests/test_database_postgres.py`). It is not a
  substitute for the independent security review that this remediation still
  requires.
