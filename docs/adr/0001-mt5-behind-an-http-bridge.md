# ADR 0001 — MetaTrader 5 lives behind an HTTP bridge

- **Status:** Accepted
- **Date:** 2026-10-24
- **Deciders:** Pablo Ez. Moscardo

## Context

The `MetaTrader5` Python package is a Windows-only CPython extension that attaches to a
running MT5 terminal through the Windows API. The platform must run on Linux (Arch,
Ubuntu), inside a Linux container, and on Windows from the same codebase. Importing the
package on a non-Windows host raises at import time, which would make the entire
application unimportable there.

Alternatives considered:

1. **Vendor the package and stub it on Linux.** Rejected: the stub degrades silently, and a
   silent no-op on a trading path is the worst possible failure mode.
2. **Run the whole platform under Wine.** Rejected: it drags the Electron shell, the GPU
   stack and the ML dependencies into a compatibility layer.
3. **Serve the venue over HTTP from a small process next to the terminal.** Chosen.

## Decision

`mt5_server.py` is a separate FastAPI process that imports the real package, binds to
`127.0.0.1:8081` by default, and exposes the venue operations the platform needs. The
application reaches it through `src/live/mt5_api_connector.py`, chosen at import time by the
factory in `src/live/connector.py` (`USE_MT5_API=auto|true|false`).

Security is part of the decision, not an afterthought:

- every request carries `X-Bridge-Token`, validated by middleware;
- the bridge refuses to start without a token when bound to a non-loopback interface;
- the documented remote deployment puts the bridge on a private network (Tailscale), never
  on the public internet — see [`deploy/MT5_BRIDGE.md`](../../deploy/MT5_BRIDGE.md);
- responses are gzipped and the symbol catalogue is filtered server-side, because the
  full catalogue is large and the link may be a consumer connection.

## Consequences

Positive:

- the platform imports and runs on Linux and in containers;
- the venue boundary is an HTTP contract, so it can be tested — three test modules cover
  authentication, session reuse and the symbol catalogue;
- the terminal (and its licence) stays on the machine that owns it.

Negative:

- an extra process to supervise (systemd unit in `deploy/local/`);
- added latency and a network hop on every venue call;
- the token becomes a credential that must be rotated and never committed;
- the bridge's API surface must be kept in step with the connector, and a version skew
  between them produces confusing errors.

## Verification

`tests/test_mt5_bridge_auth.py`, `tests/test_mt5_bridge_session.py`,
`tests/test_mt5_bridge_symbols.py` and `tests/test_mt5_api_connector_config.py`.
