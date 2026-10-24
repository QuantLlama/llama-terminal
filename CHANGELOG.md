# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and this
project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

Release notes with full detail live in [`docs/RELEASES/`](docs/RELEASES/).

## [Unreleased]

Nothing yet.

## [1.9.0] - 2026-10-24

**Cloud mode.** Full notes: [`docs/RELEASES/v1.9.0.md`](docs/RELEASES/v1.9.0.md).

### Added

- **Repository foundation** — English README, architecture / development / testing / ML
  documentation, issue and pull request templates, `CODEOWNERS`, contributing guide,
  code of conduct, security policy and a CI workflow running the test suite.
- **Remote MT5 bridge** — the Windows-only MetaTrader 5 package stays on a local
  machine and the platform talks to it over an authenticated HTTP bridge, relayed into
  the container network.
- **MT5 symbol catalogue over the bridge** — the catalogue is served by the bridge,
  cached locally, gzipped and filtered server-side instead of being re-downloaded.
- **Crypto egress proxy** — exchange traffic can be routed through an optional proxy
  (`CRYPTO_HTTP_PROXY`), documented in `deploy/`.
- **Container image and Coolify deployment** — a `python:3.11-slim` runtime image with a
  non-root user, health check and volumes for configuration, models and logs.
- **Liquidity heatmap** — crypto liquidity visualization with an optimized overlay
  renderer.
- **SQLite workspace persistence** — named workspaces with cross-timeframe drawing
  state.
- **Order flow overlays** — large-trade overlays that realign on timeframe change and
  resize.
- **Repository foundation** — English documentation (`README`, architecture, development,
  testing, ML pipeline, cloud mode, roadmap, ADRs), contribution governance (issue forms, PR
  template, `CODEOWNERS`, contributing, code of conduct, security policy) and CI (test suite on
  3.11/3.12, byte-compile, conflict markers, documentation links, Conventional Commits).

### Changed

- MT5 data is served through the connector abstraction instead of direct package calls
  in the API layer.
- The bridge reconnects lazily and no longer tears down the shared session when a
  single request ends.

### Fixed

- Bridge requests carry the token on every call and reject error payloads instead of
  returning them as data.
- Bridge symbols whose `trade_mode` is unknown are listed instead of being dropped.
- CFD session detection and MT5 tick restoration after a weekend gap.
- Real-time MT5 ECN candle rendering and timezone synchronization.
- `sqlite3.Row` attribute error on the workspaces query; workspaces refresh on platform
  change.
- Drawings no longer swallow clicks on the price and time axes, restoring zoom.
- SPA route no longer serves itself as the favicon.
- The container runtime user can write the key directory and the full application tree.

## [1.8.1] - 2026-05-02

### Fixed

- AlgoLab technical documentation and dashboard generator no longer crash with
  `NameError: name 'sys' is not defined`.
- Broker detection now prioritizes symbol patterns (MNQ, ES, NQ), fixing the endless
  loading state in detached (*popout*) charts when MT5 symbols are opened from a crypto
  session.
- Quick-save persists MT5 and crypto settings into their own session instead of
  overwriting each other.
- The workspace selector in the header shows the active workspace name, defaulting to
  `WORKSPACE 1`.
- `select` / `option` elements keep a dark, readable theme across browsers.

### Changed

- Removed third-party branding, watermarks and links (including the VIX correlation
  panel) from the charting surface.
- Selectors use custom arrow icons, accent borders and `JetBrains Mono`.
- Session tokens and state survive detaching a chart into its own window.
- Legacy symbol formats are purged from the local cache on startup.

See [`docs/RELEASES/v1.8.1.md`](docs/RELEASES/v1.8.1.md) for the full release notes.

## Earlier releases

Releases before 1.8.1 predate this changelog. The repository history and
[`docs/RELEASES/`](docs/RELEASES/) are the source of truth for them.

[Unreleased]: https://github.com/QuantLlama/llama-terminal/compare/v1.9.0...HEAD
[1.9.0]: https://github.com/QuantLlama/llama-terminal/releases/tag/v1.9.0
[1.8.1]: https://github.com/QuantLlama/llama-terminal/releases/tag/v1.8.1
