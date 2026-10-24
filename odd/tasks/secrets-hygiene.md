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

## Findings (evidence)

| # | Severity | Where | What |
| --- | --- | --- | --- |
| F1 | **Critical** | `encrypt_key.py:16-17` | Binance **API key and secret in plaintext** |
| F2 | **Critical** | `src/config/crypto_accounts.json:6` | Binance **API key in plaintext** (secret encrypted) |
| F3 | High | `src/config/mt5_accounts.json` | Three broker logins (`REDACTED`, `REDACTED`, `REDACTED`), broker server, account names, encrypted passwords |
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
| T7 | S3 | Report the history decision to the owner (rewrite vs clean publish) — **no destructive action without explicit consent** | report | — |

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
- History rewriting was **not** performed: it is destructive and needs the owner's explicit
  authorization (see T7).
