# ADR 0004 — Every venue is a connector behind one order gateway

- **Status:** Accepted
- **Date:** 2026-10-24
- **Deciders:** Pablo Ez. Moscardo

## Context

The platform trades through venues with incompatible semantics: MetaTrader 5 (request /
reply over a bridge), CCXT crypto exchanges (signed REST plus websockets), NinjaTrader 8
(file-based command replication), Tradovate (REST). Algorithms, the UI and the risk layer
must not learn four dialects.

Alternatives considered:

1. **Per-venue code paths in the API.** Rejected: the risk layer would need to know which
   venue it is guarding, and every new venue would touch the API and the UI.
2. **A single venue-neutral order model with adapters.** Chosen.
3. **An external order-management system.** Rejected: it removes the platform's control over
   its own risk decisions and adds a dependency the product cannot operate for the user.

## Decision

`src/services/order_gateway/` owns:

- an `OrderRequest` model (`side`, `type`, `size`, price fields, `source`),
- a bounded queue (1000 slots) with a four-worker executor,
- a connector registry keyed by venue,
- a `RiskValidator` that every request passes before dispatch,
- fill mirroring (for example into NinjaTrader through `replication_service.py`).

Algorithms (`algo_engine`), the API and the SPA all submit through the gateway. No client
calls a venue connector directly.

## Consequences

Positive:

- one place to add a guard, a log line, a metric or an audit record;
- the risk decision is venue-independent and therefore testable;
- a new venue is an adapter plus a manager, not a change to the API or the UI.

Negative, accepted deliberately:

- **The abstraction leaks.** NinjaTrader has no synchronous acknowledgement, MT5 answers
  request/reply, and CCXT differs per exchange in error codes. The gateway must expose the
  lowest common denominator and let each adapter report its own status; pretending they are
  identical would be worse.
- **Two risk implementations coexist today** (`order_gateway/risk_validator.py` and
  `engine/core/risk_manager.py`), so the "single funnel" claim holds for the platform path
  but not yet for the engine path. Unifying them is a roadmap item.
- **A defect in the gateway is a defect on every venue.** That is why coverage of the
  gateway and the validator is the first roadmap item.
