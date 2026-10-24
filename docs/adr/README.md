# Architecture decision records

Short, dated records of the decisions that shaped this platform. Each record states the
context, the decision and the consequences — including the costs we accepted.

| ADR | Decision | Status |
| --- | --- | --- |
| [0001](0001-mt5-behind-an-http-bridge.md) | MetaTrader 5 lives behind an HTTP bridge, not in the application process | Accepted |
| [0002](0002-single-fastapi-process-serves-api-and-spa.md) | One FastAPI process serves the API, the WebSocket streams and the SPA | Accepted |
| [0003](0003-minimal-ci-dependency-set.md) | CI installs a minimal dependency set, not the full stack | Accepted |
| [0004](0004-multi-venue-connector-abstraction.md) | Every venue is a connector behind one order gateway | Accepted |

New records: copy the shape of an existing one, number it, and add it to this table in the
same pull request.
