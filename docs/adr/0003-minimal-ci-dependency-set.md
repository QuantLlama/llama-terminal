# ADR 0003 — CI installs a minimal dependency set

- **Status:** Accepted
- **Date:** 2026-10-24
- **Deciders:** Pablo Ez. Moscardo

## Context

`requirements.txt` is the desktop and research environment: PyTorch 2.2.2, torchvision,
TA-Lib 0.4.28 (needs the C library), VectorBT, gym, PyArmor, PyInstaller, MetaTrader5 on
Windows. A runner that installs all of it spends several minutes on wheels, needs a
compiler and a TA-Lib build, and fails for reasons unrelated to the change under test.

The existing suite is unit-level: it exercises the bridge, the connector configuration, the
credential store, the crypto proxy and the favicon route. None of those need the heavy
stack.

Alternatives considered:

1. **Install the full `requirements.txt` in CI.** Maximum fidelity, unacceptable runtime and
   flakiness for a suite that does not need it.
2. **Install `requirements.deploy.txt`.** Closer to production, but it still builds TA-Lib
   and pulls the whole analytics stack for tests that never touch it.
3. **Pin a dedicated minimal set.** Chosen: `requirements.ci.txt`.

## Decision

`requirements.ci.txt` contains FastAPI, httpx, cryptography, NumPy, Pandas and pytest — and
nothing else. `.github/workflows/ci.yml` installs it on Python 3.11 and 3.12 and runs
`python -m pytest -q`.

The constraint is enforced socially and by example:

- a test must not need a broker, network access, `torch`, TA-Lib or a GPU;
- code that requires a heavy dependency at import time must degrade instead of raising, and
  `tests/test_algo_engine_torch_optional.py` holds that line for `torch`;
- a venue is replaced by a fake (`monkeypatch`, `types.ModuleType`, an in-test `TestClient`).

## Consequences

Positive:

- CI feedback in a couple of minutes instead of ten;
- the suite documents which parts of the system genuinely have no heavy dependency;
- a contributor on a laptop can reproduce CI with one `pip install`.

Negative:

- **CI does not prove the packaging or deployment path.** The container build, PyArmor and
  PyInstaller are not exercised by the test job; that gap is deliberate and tracked in the
  roadmap rather than hidden.
- **A regression that only appears with a heavy dependency installed will pass CI.** The
  mitigation is explicit: tests that touch those paths must assert the degraded behavior or
  skip with a reason, never silently pass.
- Adding a dependency to the suite now requires a conscious decision to widen
  `requirements.ci.txt`, which is exactly the friction we want.
