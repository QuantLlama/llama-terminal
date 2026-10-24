# Machine learning pipeline

This document describes what the repository actually trains, how it scores it, where the
artefacts go and how the live engine consumes them. It also lists what the pipeline does
**not** do yet, because an overstated model is worse than an honest baseline.

---

## 1. Data

| Source | Used by | Path |
| --- | --- | --- |
| Yahoo Finance (`yfinance`) | Training and research | `src/data/loader.py` |
| MetaTrader 5 (bridge or native) | Live and historical bars/ticks | `src/live/mt5_api_connector.py` |
| CCXT exchanges | Crypto perpetuals | `src/live/crypto_connector.py` |
| Uploaded CSV | Backtesting UI | `src/platform/api/backtesting_api.py` |

`load_data(ticker, period, interval)` downloads OHLCV and adjusts the period to what the
interval allows. Offline work uses the same loader with an explicit interval.

### Feature set

`FEATURE_COLS` in `src/models/artifacts.py` (re-exported by `src/data/loader.py`) defines
the single shared model input order:

```text
Log_Ret_Close · Log_Ret_High · Log_Ret_Low · Log_Vol · RSI · ADX · ATR · EMA
```

Built by `preprocess_data`:

1. technical indicators (`RSI`, `ADX`, `ATR`, `EMA`) — TA-Lib when available, pandas
   fallback otherwise,
2. log returns for close, high, low and log volume,
3. infinite/NaN removal, then missing columns filled with `0`,
4. scaling to `[-1, 1]` with a `MinMaxScaler` that is persisted with the model.

Two additional representations are computed for analysis and for optional inclusion:

- **Fourier components** — `apply_fourier_transform` keeps the lowest 3, 6 and 9 harmonics
  of the close series (`src/features/fourier.py`).
- **Autoencoder latents** — a small dense autoencoder compresses the normalized feature
  matrix into 16 latent columns, appended as `Latent_0..15` (`src/features/autoencoder.py`,
  driven from `train.py`).

### Dataset

`FuturesDataset` yields sliding windows: input `seq[t : t+L]`, target `seq[t+1 : t+L+1]`.
The model therefore learns a **one-step-ahead sequence prediction**, not a binary
up/down label. `SEQ_LENGTH` defaults to 60.

---

## 2. Model

`src/models/generator.py` — an LSTM:

```text
input_dim → LSTM(hidden_dim=128, num_layers=2, dropout=0.2) → Linear(hidden_dim, output_dim) → Tanh
```

`output_dim == input_dim == len(FEATURE_COLS)`, so the network reconstructs the next
window of the same feature space. The `Tanh` head matches the `[-1, 1]` scaling.

Selecting a device is centralized in `src/utils/device_utils.py` (`get_best_device`), which
prefers CUDA, then Apple MPS, then CPU.

### Training loop (supervised)

`train.py::train_model`:

| Element | Value |
| --- | --- |
| Loss | `MSELoss` between predicted and next window |
| Optimizer | Adam, `lr = 5e-4`, `eps = 1e-8` |
| Scheduler | `ReduceLROnPlateau(factor=0.5, patience=10)` |
| Early stopping | Patience 15 epochs on average loss |
| Gradient clipping | `max_norm = 1.0` |
| Numerical guard | NaN/Inf loss re-initializes weights and drops the learning rate by 10× |
| Epochs | 50 by default, configurable from the Trainer CLI |

A random-forest regressor ranks feature importance before training
(`analyze_feature_importance`), and ARIMA (`statsmodels`) plus a Gaussian-process
regressor (`scikit-learn`) are fitted on a short tail of the series **for diagnostic plots
only** — they are not part of the trading signal.

---

## 3. Artefacts and the naming contract

`train.py` writes to `outputs/models/`:

| File | Content |
| --- | --- |
| `<TICKER>_<timeframe>_generator.pth` | LSTM state dict |
| `<TICKER>_<timeframe>_scaler.pkl` | Fitted `MinMaxScaler` (joblib) |
| `<TICKER>_<timeframe>_config.json` | Architecture, timeframes, ordered `feature_cols`, `input_dim` |
| `<TICKER>_<timeframe>_training_history.json` | Epoch losses |
| `outputs/plots/*.png` | Training and diagnostics plots |
| `outputs/dashboard.html` | Generated HTML report served by the Trainer CLI |

The ticker is sanitized (`=` and `-` removed) before being used as a filename prefix.

**This naming contract is the interface between training and live inference.** The algo
engine resolves the three files by symbol and timeframe, falls back to a generic
`generator.pth` + `scaler.pkl` pair, and refuses to start when neither exists.

---

## 4. Inference in the live engine

`src/services/algo_engine/engine.py::load_model`:

1. resolves the three artefacts for `(ticker, timeframe)`,
2. fails explicitly when `torch` is absent (`HAS_TORCH` — a tested property),
3. validates ordered features against scaler width/names and checkpoint input/output widths,
4. rebuilds `Generator` with persisted architecture and validated width, then runs `model.eval()`.

The legacy `src/live/live_trade.py::load_model_and_scaler` uses the same validator and
retains its five-item return contract. New training validates metadata before writing the
unchanged artifact filenames. Both consumers select the validated feature order; model
EMA uses span 20, independently of the service strategy filter's EMA(50).

The historical producer fitted `MinMaxScaler` on NumPy arrays in the canonical eight-feature
order above and saved architecture/timeframe config without `feature_cols` or `input_dim`.
Both loaders preserve that legacy convention when ordered metadata and scaler feature names
are absent, provided scaler width and checkpoint input/output widths all equal eight.
This is compatibility with the documented producer, not proof of arbitrary external feature
order: custom unnamed eight-feature bundles with another order cannot be distinguished.

Explicit `feature_cols`, `input_dim` and scaler feature names remain authoritative and must
agree with the canonical order and widths. Seven-feature models, conflicting metadata,
corrupt configs and width mismatches are rejected rather than assigned another schema.
Retrain unsupported bundles; loaders never rewrite them or manufacture persisted metadata.
Service rejection returns `False` with a logged reason; the legacy loader raises an error.
Only load trusted local checkpoints/scalers: joblib artifacts are executable pickle data,
not a safe interchange format.

`start()` refuses to run without a market data engine, an order gateway and a loaded
model, and the generated orders are submitted through the order gateway like any other
order — the model never talks to a venue directly.

---

## 5. What is not in this pipeline

Recorded because a reviewer will ask, and because these are roadmap items rather than
secrets:

| Claim to avoid | Reality |
| --- | --- |
| "Transformer models" | `transformers` is pinned in `requirements.txt` but no module imports it |
| "XGBoost signals" | `xgboost` is pinned but unused; random forest replaced it |
| "Generative adversarial training" | `src/models/gan.py` and `src/models/discriminator.py` exist but nothing trains them; `train.py` is supervised LSTM only |
| "Evolutionary GAN" | `src/doctecnicaalgos/EvolutionaryGAN.md` describes a design that is not implemented end to end; the evolutionary loop that does exist is the live population in `src/services/big_llama/` |
| "Walk-forward validation" | The backtester walks bars, but the training split is a single chronological holdout |
| "Deterministic training" | No global seed is set |
| "Experiment tracking" | Artefacts are files on disk; there is no run registry |

### Artifact regression checks

Run the CPU-only synthetic contract tests without broker access or existing outputs:

```sh
venv_linux/bin/python -m pytest -q tests/test_model_artifact_contract.py tests/test_algo_engine_torch_optional.py
```

They cover both public loaders, generic fallback, historical NumPy-scaler bundles, incompatible
orders/widths, read-only rejection, service inference and optional-Torch imports.

---

## 6. Evaluation guidance

When you evaluate a model, report all four of these or the number means nothing:

1. **Out-of-sample window** — the last N bars held out chronologically, never shuffled.
2. **Costs** — spread plus commission plus slippage; a signal that dies after costs is not
   a signal.
3. **Baseline** — comparison against "always long", "previous bar direction" and a random
   entry with the same risk sizing.
4. **Stability** — the metric across several symbols and regimes, not the best symbol.

Common traps in this codebase's history worth guarding against: look-ahead bias from
indicator windows that include the target bar, leakage from scaling fitted on the full
series before splitting, and interpreting an in-sample loss curve as predictive skill.
