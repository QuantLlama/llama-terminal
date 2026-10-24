# Shipped model: supervised LSTM

Evolutionary GAN is a historical UI and filename label, not the architecture
trained by the current standard train.py entrypoint. This report describes that
path only, not every strategy or algorithm elsewhere in the repository.
The filename EvolutionaryGAN.md is retained for dashboard and packaging compatibility.

## Architecture and objective

The Generator in src/models/generator.py is a stacked LSTM followed by a
Linear projection and Tanh activation at every time step. Default train_model
arguments are hidden_dim=128, num_layers=2 and seq_length=60; LSTM dropout is 0.2.
There is no multihead attention in this Generator and no BCE classification loss.
Inputs and outputs have shape (batch, sequence length, eight features).

* Training minimizes MSELoss against the next shifted feature window.
* Adam updates the Generator; gradients are clipped to max_norm=1.0.
* ReduceLROnPlateau halves the learning rate after 10 non-improving epochs.
* Early stopping uses average training loss, with patience 15, not validation loss.
* The best training-loss state is restored before saving.

The Tanh output is a scaled feature estimate, not a calibrated probability.
Neither a 0.6/0.4 confidence rule nor probability-based sizing is implemented
by this training/report path.

## Eight ordered inputs

src/models/artifacts.py defines the canonical order:

* 1. Log_Ret_Close
* 2. Log_Ret_High
* 3. Log_Ret_Low
* 4. Log_Vol
* 5. RSI
* 6. ADX
* 7. ATR
* 8. EMA

src/data/loader.py computes close/high/low log returns, log1p volume and
technical indicators, then fits MinMaxScaler to the selected eight columns
with range [-1, 1]. Its EMA fallback uses span 20.
FuturesDataset pairs each input window with the window shifted one step forward.
Fourier components and autoencoder latents are computed upstream, but are not
additional inputs to this fixed eight-column model. RandomForest feature
importance is a separate diagnostic, not Bayesian feature selection or XGBoost signals.
ARIMA and Gaussian-process forecasts are also diagnostic plots, not an ensemble head.

## Saved artifacts and compatibility

train.py saves the Generator state, fitted scaler and JSON configuration with
ordered feature_cols and input_dim=8. Paths use the persistent outputs directory
and a ticker/timeframe prefix; the existing filenames and Python interfaces remain.
src/models/artifacts.py validates metadata before saving and is shared by loaders.

* Explicit feature order must equal the canonical list above.
* Config input_dim, scaler width/names and checkpoint input/output widths must agree.
* Historical unnamed scalers without ordered metadata use canonical-eight compatibility
  only when the validated widths agree; arbitrary external order cannot be proven.
* Seven-feature or conflicting bundles require retraining, not silent column reassignment.

Only load trusted checkpoints and scalers; serialized model artifacts are not safe
untrusted interchange files. Existing saved files are not rewritten by this documentation.

## Predictions, actions and costs

The report extracts the final time step's first output, inverse-scales it to a
close log-return estimate, and shifts Predicted_Return by -1 for Signal_Prediction.
The trainer calls src/analysis/backtester.py with is_return=True and default threshold=0.
Positive predictions select long; negative predictions select short; zero keeps the
existing position. BUY or SELL appears on a position change; otherwise the row is HOLD.
HOLD therefore does not necessarily mean flat or uncertain. These are report simulation
rules, not a replacement for the live engine's separate filters and order gateway.

The trainer backtester compounds capital using price percentage changes and deducts
one round-trip cost fraction when closing a position. Defaults are Futures 0.0008,
Stocks 0.0010, Crypto 0.0020, ETF 0.0006 and Forex 0.0003 (fallback 0.0005).
These are simplified spread/commission assumptions, not measured fills or a full
slippage/liquidity model. They do not implement Kelly sizing or contract/tick accounting.
The dashboard's stop/take-profit suggestions use recent price standard deviation
multipliers (1.5 and 2.5), not model confidence or guaranteed protection.

## Reading the reported metrics

* RMSE compares predicted and observed close log returns, not price points,
  despite the dashboard's legacy Error Pts label.
* Accuracy is the fraction of matching return signs; the dashboard displays a percentage.
* Win Rate and Total Return % come from the trainer backtester, not live account results.
* Total Return % uses its recorded equity curve; final liquidation is not appended to
  that curve, so it need not match the separately returned final capital.

Although train.py labels the last 20% evaluation as held out, the shuffled training
loader already uses the full dataset and the scaler is fitted on the full series.
Those metrics are not an independent out-of-sample profitability validation.
Overlapping windows, prediction alignment and cost assumptions require independent
chronological evaluation before any claim of predictive skill.

## Limits and non-goals

Experimental adversarial code in src/models/gan.py and src/models/discriminator.py
is not run by the shipped train.py entrypoint. That path does not train a CNN critic,
perform adversarial/evolutionary optimization, or tune Bayesian hyperparameters.
This does not remove dependencies, experimental modules or the active legacy live path.
Some surrounding dashboard captions retain historical wording; this document does not
change those consumers. Diagnostic charts and training convergence are not proof of skill.
There is no validated predictive profitability or calibrated probability guarantee here.
Trading can lose capital; research metrics are not investment advice or execution assurance.
