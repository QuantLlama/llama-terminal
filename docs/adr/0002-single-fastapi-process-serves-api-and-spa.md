# ADR 0002 — One FastAPI process serves the API, the streams and the SPA

- **Status:** Accepted
- **Date:** 2026-10-24
- **Deciders:** Pablo Ez. Moscardo

## Context

The product has three clients with almost identical needs: the Electron desktop shell, a
plain browser tab, and (for automation) anything that speaks HTTP. The frontend is a set
of JSX components under `src/platform/web`.

Alternatives considered:

1. **Static file server for the SPA, separate API host.** Rejected: two origins means CORS
   configuration, two ports to probe from the Electron supervisor, and two deployment
   targets in the container.
2. **Bundle the SPA with a build step and ship `dist/`.** Rejected for now: it adds a
   toolchain to a project that already has three, and it slows the write-in-browser loop
   during UI work.
3. **Serve everything from one FastAPI process.** Chosen.

## Decision

`src/platform/api/main.py` mounts the REST routers, the WebSocket routes and the SPA in a
single application. The desktop shell probes a port in `8050-8059`, starts the backend if
nothing answers, and then loads the same URL a browser would. Static mounts expose
`images/`, `src/live/`, `outputs/` and `logs/`.

The JSX is compiled in the browser by Babel (`src/platform/web/index.html`), so there is no
frontend build step.

## Consequences

Positive:

- one process, one port, one deployment unit — the container image is the same application
  the desktop runs;
- no CORS policy, and no cross-origin credential handling;
- a charting bug reproduces identically in the shell and in the browser;
- the Electron supervisor only has one thing to start and one thing to kill.

Negative, accepted deliberately:

- **Route registration order is a contract.** The SPA catch-all must remain the last route;
  a router registered after it is never reached.
- **The frontend pays Babel's parse cost on every load.** Acceptable for a local trading
  application; a bundling step is a roadmap item if the SPA grows.
- **`main.py` accumulates responsibilities** (routing, startup, licensing, telemetry, static
  serving) and is currently ~4,600 lines. Splitting it is a roadmap item.
- **No fetch of `index.html` distinguishes "API missing" from "API healthy"**, because the
  fallback answers `200` with HTML. This is why the readiness probe must target a real
  endpoint — tracked as the readiness-probe issue.
