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

The suite runs on a minimal dependency set, on purpose:

```bash
pip install -r requirements.ci.txt
python -m pytest -q
```

`requirements.ci.txt` contains FastAPI, httpx, cryptography, NumPy, Pandas and pytest —
nothing else. Three rules follow from that:

1. A test must not require `torch`, `transformers`, TA-Lib, a broker terminal or network
   access.
2. Code that needs a heavy dependency at import time must degrade instead of raising; the
   test `test_algo_engine_torch_optional.py` enforces that for `torch`.
3. If a test needs a venue, it uses a fake: `monkeypatch`, `types.ModuleType` or a
   `TestClient` over a router built inside the test.

---

## 2. What is covered today

85 tests across eleven modules.

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

The common thread: the connector boundary and the credential boundary. Both are places
where a regression is invisible in the UI and expensive in production.

---

## 3. What is not covered (known gaps)

State this honestly in a pull request that touches these areas — the absence of tests is
a reason for extra care, not a reason to skip verification.

| Area | Path | Risk |
| --- | --- | --- |
| Order gateway | `src/services/order_gateway/` | No test proves that every order passes the queue and the venue dispatch |
| Live risk validator | `src/services/order_gateway/risk_validator.py` | Daily limits and position tracking are untested |
| Market data engine | `src/services/market_data_engine/` | Buffer eviction and fan-out are untested |
| Strategies | `src/algorithms/` | No strategy has a deterministic fixture |
| Backtesters | `src/analysis/backtester.py`, `src/engine/backtesting/` | Metrics, costs and equity curves are unverified |
| HTTP routes | `src/platform/api/` | No `TestClient` test over the real routers |
| Auth and license | `src/services/auth.py`, `license_service.py` | Session and license gates are untested |
| Persistence | `src/services/database.py` | Schema and workspace queries are untested |

Closing these gaps is the first theme of the roadmap; see [`ROADMAP.md`](ROADMAP.md).

---

## 4. Writing a test

A test is accepted when it fails on the old code and passes on the new one. Practical
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

Every push to `main` and every pull request runs `.github/workflows/ci.yml`:

| Job | Gate |
| --- | --- |
| `pytest (3.11, 3.12)` | Full suite on a minimal dependency set |
| `static` | `compileall` over entry points, no merge-conflict markers, secret-pattern guard, every relative documentation link resolves |
| `commit-hygiene` (PRs) | The pull request title follows Conventional Commits |

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
