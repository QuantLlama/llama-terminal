# Release-readiness backlog closure

Resolve the remaining release-readiness work without changing established interfaces or simulation outcomes.
Integration branch: `feature/release-readiness`, based on the unmerged security remediation PR #28 (`e570835`).

## Specs

- **S1 — Scope.** User: "bueno dale resolve todo lo pendiente". The accepted preceding status names the 13 open issues #1–#12 and #14, security review/merge/deployment of PR #28, GitHub cache/PR-reference removal, and rebuilding a clean desktop installer. Resolve against observed code and checks, not the issue's proposed mechanism alone. Report external blockers accurately.
- **S2 — Compatibility.** User selected "Conservar compatibilidad — recomendado". Preserve existing CLI entry points, endpoint paths, response contracts, required trading capabilities and the existing distinct trainer/platform accounting semantics. Consolidate genuinely equivalent logic; retain adapters where different models or consumers require them. No silent change to fees, sizing, metric units or backtest results.
- **S3 — Version identity.** User selected "La versión del producto — recomendado". `/api/platform/version` must use the product version from `package.json`. Preserve response field names and `/api/v2` URLs. Do not enable mandatory updates or change license policy.
- **S4 — Delivery shape.** User selected "Cadena con rama integradora — recomendado". Use a draft/no-merge tracker and small feature-branch-chain PRs. Child #1 targets the integration branch; later children target the immediate preceding child branch. Keep behavior, tests and documentation in the same work unit. Do not mix strategies.
- **S5 — Service and data preservation.** Earlier user: "y que nada deje fucionar". Do not use real brokers/orders/customer credentials as test fixtures. Preserve the owner's dirty runtime configuration and local artifacts. Do not rewrite saved model files or remove environments/build artifacts without validating the exact target and explicit destructive intent. Test with isolated temporary data.
- **S6 — Privacy and authorization.** Earlier user: "no lo revoco usas los mismo en la semana lo roto"; "Preparar todo y dejarlo privado". Do not rotate credentials or make the repo public. Do not re-publish old Git history, private account data or ignored tooling. Coolify runtime variables are configured; auto-deploy is paused and production is running. No deployment until the unavailable PR #28 security proof is resolved.
- **S7 — Honest closure.** Earlier user: "que siemrpe se hagan issus, pr, accition". Close issues only with named passing checks or an explicitly documented correction of a disproved premise. A test gate is not independent security approval. The failed independent verifier for PR #28 must not be retried or replaced with the approved review of a different local worktree target.

## Tasks

| ID | Specs | Outcome / issue cluster | Route | State / commit evidence |
| --- | --- | --- | --- | --- |
| T0 | S1, S2, S7 | Reconcile all 13 issues against current consumers and tests | read-only explorer | DONE: task mvmmhopb-4-hhx6; root map in L3 |
| T1 | S1, S2, S5 | Model artifact feature-order/width contract across training and both inference consumers; reproduce #2, fix model-load device lookup if confirmed | worker: parallel independent unit | IN PROGRESS |
| T2 | S1, S2, S5 | Deterministic public-interface order-gateway/risk characterization and regression coverage for #3; no policy redesign | worker: parallel independent unit | READY |
| T3 | S1, S5 | Idempotent, portable, non-destructive environment setup with explicit recreation only, help/docs and isolated shell probes (#11) | worker: parallel independent unit | READY |
| T4 | S1, S2, S3 | Real JSON readiness and version identity from product metadata; preserve existing routes and update behavior (#1, #8) | parent inline: bounded contract fix | READY |
| T5 | S1, S2 | Extract API responsibilities into reviewable router slices without changing paths, schemas, registration order or lifecycle (#6) | worker after T4; context/composition unit | READY |
| T6 | S1, S2, S5 | Consolidate equivalent execution/risk/calculation primitives while preserving active legacy adapters and distinct simulation models (#4, #5) | bounded design + worker after T1/T2 | READY |
| T7 | S1, S2 | Remove only verified unused dependencies/modules/build declarations; align dashboard model documentation with shipped trainer (#7, #9) | parent inline after T1/T6 | READY |
| T8 | S1, S5, S6 | One documented safe desktop build path; no `.env` or runtime credentials in staging/installers; isolate compiled output and prove supported targets (#12, #14) | worker: distribution unit | READY |
| T9 | S1, S7 | Coverage artifact/trend and source secret-scan CI evidence; preserve check names and require no external paid service (#10) | parent inline after feature tests land | READY |
| T10 | S5, S6, S7 | Resolve actual independent security proof for PR #28 before merge/deploy; local runtime review is not a substitute | human/external | BLOCKED: earlier verifier failed without verdict |
| T11 | S6, S7 | Submit/resolve GitHub Support handling for 15 cached PR references; no automatic removal guarantee | provider/owner | BLOCKED: private support draft prepared, no submission channel established |
| T12 | S1–S7 | Integrate checked slices, reconcile issue evidence, build a clean installer, and deploy/verify login and MT5 only when T10 is satisfied | parent delivery + actual build/runtime checks | READY, ordered after implementation and proof |

## Log

### L1 — current request (verbatim)

> bueno dale resolve todo lo pendiente

### L2 — explicit decisions (verbatim)

- Consolidation policy: "Conservar compatibilidad — recomendado".
- `/api/platform/version`: "La versión del producto — recomendado".
- Delivery: "Cadena con rama integradora — recomendado".

### L3 — read-only baseline and corrected premises

Explorer `mvmmhopb-4-hhx6` read current sources, did not execute tests/builds and returned these root clusters:

- **Readiness/API composition (#1, #6):** clients probe `/api/health` while the API defines `/health`; catch-all may return HTML. Preserve public route and registration-order contracts during extraction.
- **Model/live truth (#2, #4, #7, #9):** trainer defines eight features, service loader assumes seven; artifact config lacks ordered feature metadata. `get_best_device()` appears unbound in service loader and must be reproduced before fixing. Legacy live execution is actively consumed by UI, CLI and frozen launcher; it cannot simply be deleted.
- **Execution/simulation (#3, #5):** gateway validation needs tests. Trainer prediction/cost backtesting and platform tick/contract PnL have materially different semantics and return contracts; they are not interchangeable duplicates.
- **Distribution/environment (#7, #11, #12, #14):** personal setup path is fixed but unconditional environment deletion remains. PyInstaller is wired into npm; Nuitka is separate. Current compilation stages output under build space, so stale local shadowing must not be misdiagnosed as current source-output behavior. Build configuration still copies `.env` into staging/resources; BrowserMode has Windows-only assumptions despite Linux targets.
- **Identity/assurance (#8, #10):** product is 1.9.0 and API constants are 2.4.0. Secret scanning is already partly implemented; coverage reporting is absent.

XGBoost still has packaging/bootstrap consumers: remove those consistently if runtime analysis confirms it is no longer needed. Do not describe it as unused everywhere without checking the build.

Baseline supplied by earlier completed work: 85 local tests pass; PR #28 CI is green, but its independent verifier failed without a verdict. The native approval for local target e2ab3435 covers only unrelated dirty runtime configuration/EOL changes, not PR #28.

### L4 — work routing and isolation

T1, T2 and T3 are genuinely independent behaviors, each requiring multi-step implementation and tests. Their edit surfaces are disjoint. Workers do not commit, push, deploy or run a full suite concurrently; each runs its focused RED/GREEN checks. Parent runs the seam suite once after the batch and commits/assesses each work unit separately. Shared documentation ownership: model → `docs/ML-PIPELINE.md`; gateway → `docs/TESTING.md`; setup → `docs/DEVELOPMENT.md`.

Dirty owner files excluded from every writer: `src/config/live_config.json`, `src/config/symbols_mt5.json`, `src/services/mt5_manager.py`. The last file currently has EOL-only noise; preserve it rather than staging normalization accidentally. Existing virtual environments, ignored `.so` files, local stashes and `.security-purge/` are not disposable test inputs.

### L5 — delivery forecast

Initial forecast exceeds 400 authored changed lines (roughly 1,500–3,000 excluding mechanical router moves; exact scope depends on compatibility characterization). Strategy: feature-branch-chain, chosen by owner. Use work-unit PRs with dependency diagrams; no single oversized omnibus merge. Route high-risk units through their own committed review slices, and keep tests/docs beside behavior. File/line counts do not establish completion or testing applicability.

No task or issue is complete merely because this plan exists. External blockers remain explicit, and source/build/runtime evidence will be appended task by task.
