# Security policy

## Supported versions

| Version | Supported |
| ------- | --------- |
| 1.8.x   | ✅        |
| < 1.8   | ❌        |

Security fixes land on `main` and in the latest release line.

## Reporting a vulnerability

**Do not open a public issue.** Report privately, through one of these channels:

1. **Preferred** — GitHub private vulnerability report:
   <https://github.com/QuantLlama/llama-terminal/security/advisories/new>
2. Email: **contacto@quantumllama.com** (PGP not required; encrypt attachments if you can)

Include:

- affected version or commit,
- the surface involved (API, WebSocket, MT5 bridge, desktop shell, credential storage),
- a minimal reproduction,
- the impact you can demonstrate, not the impact you suspect.

### What to expect

| Stage | Target |
| ----- | ------ |
| Acknowledgement | 72 hours |
| Initial assessment | 7 days |
| Fix or mitigation plan | 30 days for high severity |

You will be credited in the advisory unless you ask otherwise. Please give us a
reasonable window to ship a fix before publishing details.

## Scope

In scope — defects that affect confidentiality, integrity or availability of the
platform or its users' trading accounts:

- **Authentication and authorization bypass** — the MT5 bridge token, the API, session
  handling, Supabase auth integration.
- **Credential and secret handling** — `src/services/security.py`, `.crypto_key`,
  `.mt5_key`, encrypted account storage, secrets written to logs.
- **Order execution integrity** — a path that places, modifies or cancels an order
  without the intended authorization, validation or risk guard.
- **Injection and traversal** — command injection in the process launchers, path
  traversal in the HTTP layer, unsafe deserialization.
- **Data exposure** — account numbers, balances, positions or PII reachable by an
  unauthenticated caller, or leaked to a third party (including an egress proxy).
- **Remote code execution** in the desktop shell, the packaging pipeline or the update
  path.

Out of scope:

- Trading losses, strategy performance, or a broker's own behavior.
- Vulnerabilities in third-party dependencies without a demonstrated impact here.
- Missing hardening headers or best-practice findings with no exploitable path.
- Self-XSS, social engineering, or physical access to an unlocked machine.

## Hardening already in place

- The MT5 bridge refuses requests without `MT5_BRIDGE_TOKEN` whenever it is bound to a
  non-loopback interface (see [deploy/MT5_BRIDGE.md](deploy/MT5_BRIDGE.md)).
- Broker credentials are encrypted at rest with Fernet; the key is stored outside the
  repository.
- Crypto exchange traffic can be forced through an optional egress proxy
  (`src/services/crypto_proxy.py`).
- The cloud image runs as a non-root user with a health check (`Dockerfile`).

## Credentials in the repository

Nothing that authenticates anything may be committed: exchange API keys, broker logins,
Fernet keys, session tokens, the bridge token, or the Supabase anon key. Three mechanisms
enforce it:

1. **`.gitignore`** keeps `.env`, `*.key`, `.crypto_key`, `.mt5_key`, `*.db` and the runtime
   account stores out of the index.
2. **`scripts/check_secrets.py`** runs in CI on every push and pull request and fails on a
   credential-shaped literal, a broker account field or a personal absolute path. Run it
   locally before pushing.
3. **Environment-only configuration.** `SUPABASE_URL` / `SUPABASE_ANON_KEY`,
   `MT5_BRIDGE_TOKEN` and `CRYPTO_HTTP_PROXY` are read from the environment; the application
   has no built-in credential defaults. Without them, that feature reports itself disabled
   instead of falling back to a committed value.

### If a credential reaches a commit

Deleting it in a later commit is not a fix: it stays in the history and in every clone.

1. **Rotate the credential first.** Treat it as compromised the moment it was pushed.
2. Remove it from the working tree and load it from the environment.
3. Decide the history: rewrite it before publishing, or publish a clean history. The
   repository owner makes that call; it is destructive and never automatic.

## Safe harbour

We will not pursue legal action against researchers who act in good faith, stay within
this policy and avoid privacy violations, data destruction and service disruption.
