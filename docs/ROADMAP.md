# Roadmap

The roadmap is tracked as GitHub issues: everything below has a corresponding issue with
the `roadmap` label, and the issues are the source of truth for status. This page explains
the intent behind the order.

Two rules apply to everything here:

1. **Nothing is promised by being on this list.** A roadmap item is a direction, not a
   commitment, and priorities change with what the platform actually needs.
2. **A theme closes when its verification lands**, not when the code merges. For the
   hardening theme that means tests, not refactors alone.

---

## Theme 1 — Execution correctness (highest priority)

The platform can place real orders. Everything else waits behind making that path
provably safe.

| Item | Why it matters |
| --- | --- |
| Cover the order gateway with tests | No test proves every order passes the queue, the validator and the venue dispatch |
| Cover the live risk validator with tests | Daily limits, position tracking and rejection reasons are untested |
| Delete the duplicate execution path (`src/live/live_trade.py`) | Two live loops mean a guard fixed in one stays broken in the other |
| Unify the two risk implementations | `risk_validator.py` (JSON) and `engine/core/risk_manager.py` (YAML) can disagree on a limit |
| Unify the two backtesting engines | Trainer results and platform results must be comparable |
| Fix the readiness probe | The supervisor polls `/api/health`, which does not exist; the SPA fallback answers `200`, so a dead backend looks alive |
| Align inference feature width with training | `algo_engine.load_model` assumes 7 features; training produces 8 |

## Theme 2 — Structural cleanup

Cheap, low-risk work that makes the next change easier.

| Item | Why it matters |
| --- | --- |
| Split `src/platform/api/main.py` into router modules | ~4,600 lines mix routing, startup, licensing, telemetry and static serving |
| Remove unused dependencies (`transformers`, `xgboost`) | Smaller installs, honest stack, faster CI |
| Remove dead modules (`src/models/gan.py`, `src/platform/web/App.jsx`) or wire them | Readers assume everything in the tree ships |
| Report the real version from the API | The endpoint answers `2.4.0` while the product is `1.8.1` |
| Reconcile `EvolutionaryGAN.md` with the implemented pipeline | The document describes a model the trainer does not build |
| Make `setup_env.sh` portable and non-destructive | It hardcodes one developer's home path and deletes the virtual environment on every run |
| Replace the competing build entry points (`build_dist.py` vs `scripts/build_backend.py`) | Two toolchains, one of them not wired into `npm run dist` |

## Theme 3 — Delivery and operations

What turns a working repository into a releasable product.

| Item | Why it matters |
| --- | --- |
| Tag releases and publish release notes from `CHANGELOG.md` | There is one historical tag and no automated release |
| Coverage reporting in CI | The suite is small; the trend is the signal |
| Secret scanning in CI | Credentials are the highest-severity failure mode here |
| Chained pull requests for large changes | Protect review quality as the platform grows |
| Evaluate publishing this repository | Owner decision; the code, docs and governance must be finished first |

## Theme 4 — Product direction (exploratory)

Not committed. Listed because the codebase already contains the raw material and a reader
should know where it is heading.

- Multi-account execution with per-account risk budgets (the account layer exists, the
  budgets do not).
- A documented, versioned HTTP API contract (OpenAPI is generated; a compatibility policy
  is not).
- Workspace and layout sharing (workspaces already persist in SQLite).
- A reproducible research notebook per strategy, with the artefact contract enforced by a
  test.

---

## Out of scope

- Hosting a public market-data service.
- Any feature that requires storing a customer's broker credentials on infrastructure the
  user does not control.
- Copy trading or signal distribution.
