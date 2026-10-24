# Secrets hygiene and pre-publish audit

Remove every credential, account identifier and personal path from the tracked tree, add a
gate that fails CI when a new one appears, and decide (with the owner) what happens to the
history that already contains them.

## Specs

- **S1** — Owner: *"te aseguraste que en repo no tengamos secrectos ni nada que me esponga algun
  dato privado complicado"*. The tracked tree must contain no credential, no broker account
  number, no exchange API key, no authentication secret and no personal absolute path.
- **S2** — A new secret must be caught by CI before it lands, not by a human reading a diff.
- **S3** — Nothing already in Git history is considered "removed" by a new commit; the owner must
  be told what remains and what the options are.
- **S4** — Owner selected *"Sí, autorizo la purga del historial"* after being told that affected branches and tag `v1.9.0` would be rewritten and hashes would change. Preserve working data and production availability; do not rotate credentials.
- **S5** — Owner: *"y que nada deje fucionar"*. Removing browser-embedded Supabase configuration must preserve login: obtain the public anon configuration from runtime environment, never expose an administrative/service-role key. Keep production unchanged until missing security proof is resolved.

## Findings (evidence)

| # | Severity | Where | What |
| --- | --- | --- | --- |
| F1 | **Critical** | `encrypt_key.py:16-17` | Binance **API key and secret in plaintext** |
| F2 | **Critical** | `src/config/crypto_accounts.json:6` | Binance **API key in plaintext** (secret encrypted) |
| F3 | High | `src/config/mt5_accounts.json` | Broker logins (redacted), broker server, account names, encrypted passwords |
| F4 | Medium | `src/services/auth.py:8-9` | Supabase project URL + **anon JWT** (`role: anon`, expires 2035) hardcoded as built-in defaults |
| F5 | Low | `setup_env.sh:16`, `scratch/`, `.atl/skill-registry.md` | Personal absolute paths (`/home/<user>/...`) and internal tooling state |
| F6 | Low | `.agents/`, `.claude/`, `.junie/`, `.openclaw/` (222 tracked files) | Agent/tooling skill trees: not secrets, but internal noise and duplicated config in a product repo |

Mitigating fact verified: no `*.key`, `.env`, `*.pem` or database file was **ever** tracked
(`git rev-list --objects --all`), so the encrypted blobs in F3 are not decryptable from the
repository alone.

## Tasks

| ID | Spec | Task | Route | Commit |
| --- | --- | --- | --- | --- |
| T1 | S1 | Delete `encrypt_key.py`; empty the account stores; `default_account.json` loses the reference | inline | `fix(security): remove credentials from the tracked tree` |
| T2 | S1 | `src/services/auth.py` reads Supabase credentials from the environment only, with an explicit disabled state | inline | same commit |
| T3 | S1 | Untrack the agent/tooling trees, `scratch/` and `.venv_linux_path`; ignore them; `.dockerignore` stops shipping runtime account files | inline | same commit |
| T4 | S1 | `setup_env.sh` no longer contains a username path | inline | same commit |
| T5 | S2 | `scripts/check_secrets.py` + CI gate + a test that the guard catches each pattern class | inline | `ci(security): fail the build on committed secrets` |
| T6 | S2, S3 | Documentation: SECURITY.md, CONTRIBUTING.md, CHANGELOG.md, `docs/DEVELOPMENT.md` | inline | folded into T5 |
| T7 | S3 | Report the history decision to the owner | report | completed: explicit authorization received |
| T8 | S4 | Inventory remote refs and sensitive historical blobs without exposing values | inline | evidence in log |
| T9 | S4 | Filter all affected branch/tag history in an isolated mirror | inline | rewritten refs |
| T10 | S3, S4 | Push only authorized refs with exact leases; sanitize repository metadata and record inaccessible PR/cache remnants | inline | rewritten refs |
| T11 | S3, S4 | Report production health, retained local copies and missing independent security proof | inline | evidence in log |
| T12 | S1, S5 | Replace embedded browser configuration with runtime anon-only configuration | worker | completed; 27 focused tests, PR #28 |
| T13 | S1, S2 | Remove first-party file-size blind spot and use synthetic account fixtures | inline | completed; RED/GREEN, 5 guard tests |

## Log

### L1 — request (verbatim)

> te aseguraste que en repo no tengamos secrectos ni nada que me esponga algun dato privado complicado

### L2 — honest status before the audit

The answer was **no**: only `.gitignore`/`.dockerignore` patterns had been reviewed, which is not
an audit. The audit ran afterwards and found F1–F6.

### L3 — decisions taken without asking (reversible, in-scope)

- Sanitizing a tracked credential is not a product decision, so it was done immediately.
- Deleting `encrypt_key.py` was chosen over sanitizing it: it is a one-off personal migration
  script, not product code, and the keys it contained are already in history.
- History rewriting was initially withheld pending explicit authorization (see L4).

### L4 — explicit history authorization

The owner selected *"Sí, autorizo la purga del historial"* in response to the scoped question covering affected branches, tag `v1.9.0`, forced remote updates, changed commit hashes and clone resynchronization. The prompt stated that external copies and GitHub caches are not automatically erased.

Current owner instruction (verbatim):
> no lo revoco usas los mismo en la semana lo roto pero estos aun funcionan y no fueron hackeados pero asegurte que no quede nada expuesto en el repo,. y ya tenes el token de coolify para que hagas todo lo de las variables, y que nada deje fucionar asi qu ehace todo lo qu etengas que hacer dale

No credential rotation is authorized now. Coolify runtime variables were configured before deployment. The independent verifier failed without a verdict; this remains missing proof, not approval. Production deployment is held.


### L5 — authorized history purge and its limits

- Rewrote 17 branches and 2 tags with exact-lease atomic pushes. Preserved two public integration defaults after identifying over-redaction: a public broker server label and a generic NinjaTrader exchange directory are not credentials.
- A final fresh download checked 922 reachable blob/commit/tag objects: zero occurrences of the identified sensitive values. This is a known-value check of ordinary branches/tags, not an unrestricted security certification.
- Two editable GitHub text bodies were sanitized. Metadata readback found no identified values in issue, comment or release text.
- Fifteen affected GitHub PR references remain provider-controlled. Server-side cache/PR cleanup requires GitHub Support; no request was submitted.
- Coolify production and preview runtime Supabase settings are configured without rotation. Actual auto-deploy on main was enabled; it was paused before forced updates. Production was not restarted.
- Browser runtime configuration has 27 isolated public-interface tests; the guard has 5. Full local suite: 85 passed with one dependency warning. Before the history rewrite, the runtime/guard correction CI passed on Python 3.11 and 3.12.
- The independent verifier failed without a verdict. No native review approval or deployment approval is claimed. PR #28 stays unmerged while this proof is missing.
- Local branches/tracking refs and tags were resynchronized without a hard reset. Four pre-existing working-file hashes were preserved. Existing local stashes, unreachable old objects and other clones were not erased; do not push them back.
- Delivery slices: credential removal; mechanical untracking of tooling; source guard; browser runtime migration; large-file regression; this remediation record. The many deleted tooling lines are not a new product implementation.

### L6 — explicit installer deletion authorization

The owner selected *"Sí, eliminá el instalador antiguo"* after being told that deleting the 913 MB release download is irreversible and does not alter installed applications or cloud production. The exact named asset was deleted; API readback confirmed zero remaining assets on that legacy release. Notes were retained. No claim is made about copies already downloaded.
