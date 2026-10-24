# Testing

The suite exists to protect the parts of this platform where a defect costs money, leaks
a credential or silently changes a trading decision. It is deliberately small and it is
allowed to be: every test here must fail when the behavior it describes is broken.

```bash
python -m pytest -q                                  # full suite
python -m pytest tests/test_mt5_bridge_auth.py -q    # one module
python -m pytest -q -k bridge                        # by keyword
```

`pytest.ini` restricts collection to `tests/`. The `test_*.py` scripts in the repository
root are ad-hoc manual probes from earlier development and are not part of the suite.

---

## 1. Setup

Use an isolated environment, not an existing desktop or owner environment. The minimal
API/source lane deliberately excludes two modules that run in the separate CPU lane:

```bash
python -m pip install -r requirements.ci.txt
python -m pytest -q --ignore=tests/test_model_artifact_contract.py --ignore=tests/test_simulation_compatibility.py
```

`requirements.ci.txt` supplies the API test dependencies, NumPy/Pandas, requests for
readiness probes, pytest and coverage. It does not install torch or scikit-learn.

For the **Python 3.11 CPU model/simulation lane**, use another isolated environment:

```bash
python -m pip install -r requirements.ci.txt scikit-learn==1.4.2 yfinance==0.2.40
python -m pip install torch==2.2.2 --index-url https://download.pytorch.org/whl/cpu
python -c "import numpy, pandas, sklearn, torch; assert not torch.cuda.is_available(); assert torch.version.cuda is None"
python -m pytest -q tests/test_model_artifact_contract.py tests/test_simulation_compatibility.py
```

This separate lane is necessary because the artifact tests import real torch and
scikit-learn at collection time; the data loader also imports yfinance, but these tests
do not download data. Silently skipping those tests in the minimal environment would
hide the feature-order/model-loading seam. Existing application pins are retained;
transformers, TA-Lib, native terminals and the full training stack are not installed.

1. Tests use synthetic data, never real venues or network access.
2. Optional cloud imports must still degrade gracefully: the minimal lane retains
   `test_algo_engine_torch_optional.py`, which explicitly blocks torch imports.
3. Venue boundaries use fakes: `monkeypatch`, `types.ModuleType` or a `TestClient` over
   a router built inside the test.

---

## 2. What is covered today

The table below records the earlier 85-test baseline, not a current suite total.
Release-readiness additions include model artifact ordering/loading, synthetic simulation
accounting, readiness/version, API router composition and packaging-source contracts.
Use the actual pytest summary for the current count; do not infer live-platform coverage.

| Module | Tests | What it pins |
| --- | --- | --- |
| `test_bridge_types.py` | 14 | Dict → attribute normalization and positions payload mapping |
| `test_mt5_api_connector_config.py` | 10 | Bridge URL and token resolution, `MT5_AUTO_LAUNCH`, shared-session shutdown, symbol cache |
| `test_mt5_bridge_symbols.py` | 8 | Symbol catalogue route, server-side filtering, token enforcement |
| `test_mt5_bridge_auth.py` | 6 | Default bind, token requirement once non-loopback |
| `test_mt5_bridge_session.py` | 5 | Lazy reconnect semantics of the bridge session |
| `test_crypto_proxy.py` | 4 | `CRYPTO_HTTP_PROXY` parsing and application to exchanges |
| `test_credential_manager_key_dir.py` | 3 | `QUANTUM_LLAMA_KEY_DIR` override and key creation |
| `test_web_favicon.py` | 2 | The SPA does not serve itself as the favicon |
| `test_algo_engine_torch_optional.py` | 1 | The algo engine imports with `torch` blocked |
| `test_secrets_guard.py` | 5 | Pattern detection, masked reports, binary exclusion and large first-party files |
| `test_public_auth_config.py` | 27 | Runtime anon-only settings, privileged/missing/malformed rejection, escaping, caching and frontend startup |

### Order gateway and live risk boundary

```bash
venv_linux/bin/python -m pytest -q tests/test_order_gateway.py tests/test_live_risk_validator.py
```

These deterministic tests use real request/response models and risk validation with a
fake connector. Synchronous submission creates no worker threads; fixtures isolate the
singleton, disable file logging and replication, and shut down the executor in teardown.
No broker, runtime configuration, credentials, network or live market data is used.

- Successful submissions dispatch exactly once with the normalized size; failed broker
  responses do not consume daily risk allowance.
- A daily limit of N permits N successful orders and rejects the next with
  `MAX_ORDERS_EXCEEDED`. Total and ALGO-specific caps remain distinct (defaults 50/20).
- Daily PnL at or below -500 rejects with `MAX_DAILY_LOSS_EXCEEDED`; -499 permits trading.
- Nonpositive crypto sizes must remain invalid, not be raised to the exchange minimum.
  Positive fractional sizing still uses the existing contract conversion and rounding.
- Manual/ALGO position caps remain 10/5. `RiskValidator.update_position()` supplies the
  snapshot; validation and `record_order()` do not automatically rewrite positions.
- Rejections leave risk counters, PnL, positions and execution metrics unchanged.
  Gateway received/rejected telemetry intentionally increments; it is not risk allowance.

Position accumulation through live fills, concurrent submissions, asynchronous queue
processing and worker lifecycle behavior are not established by these synchronous tests.

The common thread: the connector boundary and the credential boundary. Both are places
where a regression is invisible in the UI and expensive in production.

---

## 3. What is not covered (known gaps)

State this honestly in a pull request that touches these areas — the absence of tests is
a reason for extra care, not a reason to skip verification.

| Area | Path | Risk |
| --- | --- | --- |
| Order gateway | `src/services/order_gateway/` | Async queue/concurrent dispatch and lifecycle remain untested |
| Live risk validator | `src/services/order_gateway/risk_validator.py` | Live fill-to-position synchronization and daily rollover remain untested |
| Market data engine | `src/services/market_data_engine/` | Buffer eviction and fan-out are untested |
| Strategies | `src/algorithms/` | No strategy has a deterministic fixture |
| Backtesters | `src/analysis/backtester.py`, `src/engine/backtesting/` | Synthetic accounting/metric contracts exist; live data realism and full strategy outcomes remain unverified |
| HTTP routes | `src/platform/api/` | Readiness/version and operational-router contracts exist; not all domain routes or production services are exercised |
| Auth and license | `src/services/auth.py`, `license_service.py` | Session and license gates are untested |
| Persistence | `src/services/database.py` | Schema and workspace queries are untested |

Closing these gaps is the first theme of the roadmap; see [`ROADMAP.md`](ROADMAP.md).

---

## 4. Writing a test

Behavior fixes require an observed failure on the old code and a pass on the fix.
Characterization of already-correct behavior needs no fabricated RED. Practical
patterns used in this repository:

**Fake a module** — replace a dependency with a stub injected into `sys.modules`:

```python
import sys, types

def test_bridge_without_token(monkeypatch):
    fake = types.ModuleType("MetaTrader5")
    fake.initialize = lambda **kwargs: True
    monkeypatch.setitem(sys.modules, "MetaTrader5", fake)
    ...
```

**Prove import isolation** — run the import in a subprocess with a meta-path finder that
blocks the dependency, so the assertion is about the import, not about the local
environment:

```python
subprocess.run([sys.executable, "-c", script], check=True, cwd=REPO_ROOT)
```

**Assert the observable contract** — HTTP status and body, the exact error message, the
value written to the store, the arguments passed to the connector. Never assert on private
attributes unless the attribute *is* the contract.

**Cover the case the rule names** — the boundary (`127.0.0.1` versus `0.0.0.0`), the empty
catalogue, the rejected payload. A test of the happy path alone does not describe a rule.

---

## 5. CI gates

`.github/workflows/ci.yml` keeps pushes restricted to `main` and retains manual
`workflow_dispatch`. Pull requests run CI for every target branch, including
`feature/release-readiness` and predecessor `fix/`, `refactor/` or `build/` branches
in the approved feature-branch chain. Existing job IDs and check names are unchanged:

| Job ID / check name | Gate |
| --- | --- |
| `tests` / `pytest (Python 3.11)`, `pytest (Python 3.12)` | Minimal API/source suite, excluding only the two explicit CPU selectors above |
| `model-simulation` / `CPU model and simulation seams (Python 3.11)` | Real CPU model artifacts and synthetic trainer/platform accounting; dependency imports must succeed |
| `static` / `Syntax, conflict markers and documentation links` | Python compilation, conflict markers, full source secret guard, relative doc links; Electron main/health syntax when Node exists |
| `commit-hygiene` / `Conventional Commits` (PRs) | Conventional PR title |

The new lane is additive; this workflow does not change repository branch-protection
settings or declare it a required check. Read-only repository permissions and the existing
`python scripts/check_secrets.py` source scan remain intact. No paid reporting service,
external coverage upload, new token, deployment or credential fixture is introduced.

### Coverage reports and comparison

Each Python lane runs `python -m coverage run -m pytest -q` with its selectors, then
creates XML and a human-readable missing-line report, even after test failure:

```bash
# After running coverage with the lane selectors, using a fresh external scratch directory:
python -m coverage xml -o "$RUNNER_TEMP/coverage.xml"
python -m coverage report -m > "$RUNNER_TEMP/coverage.txt"
```

CI sets `COVERAGE_FILE` to `${{ runner.temp }}/.coverage`; local reproduction should set
it to a fresh system-temp location, not a shared worktree database. GitHub artifacts
`coverage-python-3.11`, `coverage-python-3.12` and
`coverage-model-simulation-python-3.11` retain only XML/text reports for 14 days in the
private repository. The text report also appears in job logs. Reports contain source
paths and line counts, not credentials, raw model artifacts or customer data. Private
Actions access rules still apply; do not publish reports elsewhere without authorization.

`.coveragerc` measures `src` with no module omissions and no invented percentage floor.
Unexercised native/broker/training code remains visible as missing coverage, not silently
excluded. Compare the **same lane and Python version** across runs for a manual trend;
these are separate reports, not a merged total or an automated trend service. Subprocess
execution is not measured by this configuration. Successful collection alone does not
prove training, CUDA/MPS, TA-Lib/native execution, installed Electron/MT5, real brokers,
orders, installer safety or production deployment. Some dependencies are stubbed and
some source-only tests inspect files without executing application code.

The CPU lane has a 20-minute timeout. Expect several minutes on a cold cache for CPU
torch and scientific wheels (hundreds of MB); this is an estimate, not a measured hosted
runtime. Pip caching reduces repeat downloads without caching private test data.

Offline structural validation: `venv_linux/bin/python -m pytest -q tests/test_ci_contract.py`.
This validates selected workflow contracts, not the full Actions YAML schema. Hosted
Actions execution and coverage baselines remain **pending** until returned checks and
artifacts are observed. A local test pass is not hosted success or independent security
approval. Parent integration runs the combined suite after parallel changes finish.

A red gate is a stop, not a warning. If a check is flaky, fix the check; do not retry it
into green.

---

## 6. Manual verification

Some behavior cannot be tested without a venue. When you verify it by hand, record what
you ran and what you saw in the pull request:

- placing and cancelling an order against a demo account,
- the bridge refusing a request without `MT5_BRIDGE_TOKEN`,
- a footprint chart rendered from live ticks,
- an optimization job that completes and produces a PDF.

"I tested it" is not evidence. A command, a screenshot or a log excerpt is.
