import matplotlib
matplotlib.use('Agg') # Fix for Tcl_AsyncDelete error in multi-threaded env
import torch
from src.utils.device_utils import get_best_device
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import DataLoader, TensorDataset
from src.config import config
from src.data.loader import load_data, preprocess_data
from src.features.indicators import add_technical_indicators
from src.features.fourier import apply_fourier_transform
from src.features.autoencoder import Autoencoder
from src.models.generator import Generator
# GAN and RL imports removed - using supervised LSTM now
from src.utils.visualizer import Visualizer
from rich.progress import track
import xgboost as xgb
import numpy as np
import pandas as pd
from statsmodels.tsa.arima.model import ARIMA
import yfinance as yf
from sklearn.gaussian_process import GaussianProcessRegressor
from sklearn.gaussian_process.kernels import RBF, ConstantKernel as C
import json
import os
import webbrowser
from datetime import datetime
from sklearn.metrics import mean_squared_error, mean_absolute_percentage_error
from src.analysis.backtester import Backtester
from src.utils.dashboard_gen import DashboardGenerator

def train_autoencoder(data, input_dim, encoding_dim=16, epochs=50, device='cpu'):
    print("Training Autoencoder for Feature Extraction...")
    model = Autoencoder(input_dim, encoding_dim).to(device)
    criterion = nn.MSELoss()
    optimizer = optim.Adam(model.parameters(), lr=0.001)
    
    # Convert data to tensor
    tensor_data = torch.FloatTensor(data).to(device)
    dataset = TensorDataset(tensor_data, tensor_data)
    loader = DataLoader(dataset, batch_size=64, shuffle=True)
    
    for epoch in range(epochs):
        total_loss = 0
        for batch in loader:
            inputs, _ = batch
            optimizer.zero_grad()
            encoded, decoded = model(inputs)
            loss = criterion(decoded, inputs)
            loss.backward()
            optimizer.step()
            total_loss += loss.item()
        if epoch % 10 == 0:
            print(f"Autoencoder Epoch {epoch}: Loss {total_loss/len(loader):.4f}")
            
    # Extract latent features
    with torch.no_grad():
        encoded, _ = model(tensor_data)
    return encoded.cpu().numpy()

def analyze_feature_importance(df, target_col='Close'):
    print("Analyzing Feature Importance with RandomForest...")
    from sklearn.ensemble import RandomForestRegressor
    X = df.drop(columns=[target_col])
    y = df[target_col]
    
    # Using RandomForestRegressor which runs natively without access violations under Wine
    model = RandomForestRegressor(n_estimators=100, random_state=42, n_jobs=1)
    model.fit(X, y)
    
    return X.columns, model.feature_importances_

def calculate_arima(df, order=(5,1,0)):
    print("Calculating ARIMA model...")
    # Use a subset for speed if needed
    train_data = df['Close'].iloc[:-100]
    test_data = df['Close'].iloc[-100:]
    
    history = [x for x in train_data]
    predictions = list()
    
    # Simple walk-forward validation or just a one-step forecast for demo
    # For speed in this demo, we'll fit once and forecast
    model = ARIMA(history, order=order)
    model_fit = model.fit()
    output = model_fit.forecast(steps=len(test_data))
    
    return train_data, test_data, output

def calculate_gaussian_process(df):
    print("Calculating Gaussian Process Regression...")
    # Use a small subset for GPR as it is O(N^3)
    # We'll take the last 200 points: 150 train, 50 test
    subset = df['Close'].tail(200)
    train_data = subset.iloc[:-50]
    test_data = subset.iloc[-50:]
    
    X_train = np.atleast_2d(np.arange(len(train_data))).T
    y_train = train_data.values
    
    X_test = np.atleast_2d(np.arange(len(train_data), len(train_data) + len(test_data))).T
    
    # Kernel: Constant * RBF
    kernel = C(1.0, (1e-3, 1e3)) * RBF(10, (1e-2, 1e2))
    gp = GaussianProcessRegressor(kernel=kernel, n_restarts_optimizer=9)
    
    gp.fit(X_train, y_train)
    
    y_pred, sigma = gp.predict(X_test, return_std=True)
    
    return train_data, test_data, y_pred, sigma

def train_model(ticker, period, epochs, asset_type, train_timeframe="1h", trade_timeframe="1h", seq_length=60, hidden_dim=128, num_layers=2):
    # Update config based on user input
    config.DEVICE = get_best_device()
    config.NUM_EPOCHS = epochs
    config.SEQ_LENGTH = seq_length
    config.HIDDEN_DIM_LSTM = hidden_dim
    config.NUM_LAYERS_LSTM = num_layers
    
    config.NUM_LAYERS_LSTM = num_layers
    
    # Sanitize ticker for filename prefix
    safe_ticker = ticker.replace("=", "").replace("-", "")
    plot_prefix = f"{safe_ticker}_{train_timeframe}"
    
    vis = Visualizer(filename_prefix=plot_prefix)
    
    print(f"Loading data for {ticker} ({asset_type}) with timeframe {train_timeframe}...")
    # 1. Load and Preprocess Data
    df = load_data(ticker, period=period, interval=train_timeframe)
    df = add_technical_indicators(df)
    
    # --- Advanced Visualizations (Original Repo Style) ---
    
    # 1. Correlation Matrix
    print("Generating Correlation Matrix...")
    # Adjust correlated assets based on Asset Type
    if asset_type == "Crypto":
        tickers = [ticker, "ETH-USD", "SOL-USD", "BNB-USD", "^VIX"]
    elif asset_type == "Stocks":
        tickers = [ticker, "SPY", "QQQ", "IWM", "^VIX"]
    else: # Futures / ETF / Default
        tickers = [ticker, "ES=F", "GC=F", "CL=F", "^VIX"]
        
    corr_data = yf.download(tickers, period="1y", interval="1d", progress=False)['Close']
    if not corr_data.empty:
        vis.plot_correlation_matrix(corr_data)
        
    # ... (Rest of visualization logic remains same) ...
    
    # 2. Sentiment Analysis (VIX Proxy)
    print("Generating Sentiment Analysis (VIX)...")
    try:
        # Download VIX matching the main timeframe if possible, or just 1y daily for the plot
        vix_df = yf.download("^VIX", period=period, interval="1h", progress=False)
        if not vix_df.empty:
            # Align VIX to main DF for plotting
            # We'll just plot them on the same chart using the visualizer
            # Need to ensure indices overlap
            # Create a temp df for plotting
            sentiment_df = pd.DataFrame(index=df.index)
            sentiment_df['Close'] = df['Close']
            # Resample VIX to match DF if needed, or reindex
            # Simplest is to just fetch VIX with same params and join
            vix_reindexed = vix_df['Close'].reindex(df.index, method='ffill')
            sentiment_df['VIX'] = vix_reindexed
            vis.plot_sentiment(sentiment_df, sentiment_col='VIX')
    except Exception as e:
        print(f"Warning: Could not generate Sentiment Plot: {e}")
    
    # 3. Technical Dashboard
    vis.plot_technical_dashboard(df.tail(200), ticker_name=ticker)
    
    # 4. ARIMA Analysis
    train_arima, test_arima, forecast_arima = calculate_arima(df)
    vis.plot_arima(train_arima, test_arima, forecast_arima)

    # 5. Gaussian Process Regression (NEW)
    train_gp, test_gp, pred_gp, sigma_gp = calculate_gaussian_process(df)
    vis.plot_gaussian_process(train_gp, test_gp, pred_gp, sigma_gp)

    # Plot Fourier Analysis
    if config.USE_FOURIER:
        df = apply_fourier_transform(df)
        vis.plot_fourier_components(df.tail(300))
    
    # Visualize basic features
    vis.plot_features(df.tail(500))
    
    # --- Feature Engineering & Selection ---
    # Prepare data for Autoencoder/XGBoost (drop non-numeric if any)
    feature_df = df.select_dtypes(include=[np.number]).dropna()
    
    # XGBoost Feature Importance
    features, importance = analyze_feature_importance(feature_df)
    vis.plot_feature_importance(features, importance)
    
    # Autoencoder Feature Extraction
    # Normalize first for Autoencoder
    from sklearn.preprocessing import MinMaxScaler
    ae_scaler = MinMaxScaler()
    scaled_data = ae_scaler.fit_transform(feature_df)
    
    latent_features = train_autoencoder(scaled_data, input_dim=scaled_data.shape[1], device=config.DEVICE)
    
    # Add latent features to dataframe
    for i in range(latent_features.shape[1]):
        df[f'Latent_{i}'] = np.nan # Initialize
        # Align indices
        df.iloc[-len(latent_features):, df.columns.get_loc(f'Latent_{i}')] = latent_features[:, i]
        
    df.dropna(inplace=True) # Drop rows with NaNs from alignment
        
    # --- GAN Training Preparation ---
    dataset, scaler = preprocess_data(df, config.SEQ_LENGTH)
    dataloader = DataLoader(dataset, batch_size=config.BATCH_SIZE, shuffle=True)
    
    input_dim = dataset.data.shape[1] # Number of features
    
    # 2. Initialize Model (Generator LSTM only, no Discriminator)
    generator = Generator(input_dim, config.HIDDEN_DIM_LSTM, config.NUM_LAYERS_LSTM, input_dim)
    generator = generator.to(config.DEVICE)
    
    # 3. Initialize Optimizer and Loss
    optimizer = optim.Adam(generator.parameters(), lr=config.LEARNING_RATE_G)
    criterion = nn.MSELoss()
    
    # Lists to store losses for plotting
    train_losses = []
    
    # 4. Training Loop (Supervised Learning)
    print("Starting Supervised LSTM Training Loop...")
    for epoch in track(range(config.NUM_EPOCHS), description="Training Epochs..."):
        epoch_loss = 0
        batches = 0
        
        generator.train()
        for i, (seq, target) in enumerate(dataloader):
            seq = seq.to(config.DEVICE)
            target = target.to(config.DEVICE)
            
            # Forward pass
            optimizer.zero_grad()
            prediction = generator(seq)
            
            # Compute loss between prediction sequence and target sequence
            # Both are shape (batch, seq_length, features)
            loss = criterion(prediction, target)
            
            # Backward pass
            loss.backward()
            optimizer.step()
            
            epoch_loss += loss.item()
            batches += 1
            
        # Average loss for the epoch
        avg_loss = epoch_loss / batches
        train_losses.append(avg_loss)
        print(f"Epoch {epoch+1}/{config.NUM_EPOCHS} - Loss: {avg_loss:.6f}", flush=True)
        
        # Snapshot Plotting
        if epoch == 0 or epoch == 49 or epoch == 199 or epoch == config.NUM_EPOCHS - 1:
            generator.eval()
            with torch.no_grad():
                sample_seq = seq[0].unsqueeze(0).to(config.DEVICE)
                prediction = generator(sample_seq).cpu().numpy()[0]
                
                # Desnormalizar (Inverse Transform)
                # El scaler espera 7 columnas: ['Log_Ret_Close', 'Log_Ret_High', 'Log_Ret_Low', 'Log_Vol', 'RSI', 'ADX', 'ATR']
                # Index 0 es Log_Ret_Close
                
                real_dummy = np.zeros((len(seq[0]), scaler.n_features_in_))
                pred_dummy = np.zeros((len(prediction), scaler.n_features_in_))
                
                # Fill index 0 with our data
                real_dummy[:, 0] = seq[0, :, 0].cpu().numpy()
                pred_dummy[:, 0] = prediction[:, 0]
                
                # Inverse Transform to get Real Log Returns
                real_returns = scaler.inverse_transform(real_dummy)[:, 0]
                pred_returns = scaler.inverse_transform(pred_dummy)[:, 0]
                
                # Reconstruct Price Index (Start at 100)
                # Price_t = Price_{t-1} * exp(Log_Return_t)
                # Index_t = 100 * exp(cumsum(Log_Returns))
                real_prices = 100 * np.exp(np.cumsum(real_returns))
                pred_prices = 100 * np.exp(np.cumsum(pred_returns))
                
                if epoch == 0:
                    vis.plot_training_snapshot(real_prices, pred_prices, epoch, 
                                             title='Price Index (Base 100) - Epoch 1',
                                             filename='prediction_epoch_1.png')
                
                if epoch == 49:
                    vis.plot_training_snapshot(real_prices, pred_prices, epoch, 
                                             title='Price Index (Base 100) - Epoch 50',
                                             filename='prediction_epoch_50.png')
                
                if epoch == 199:
                    vis.plot_training_snapshot(real_prices, pred_prices, epoch, 
                                             title='Price Index (Base 100) - Epoch 200',
                                             filename='prediction_epoch_200.png')
                
                if epoch == config.NUM_EPOCHS - 1:
                    vis.plot_training_snapshot(real_prices, pred_prices, epoch, 
                                             title='Final Price Index (Base 100)',
                                             filename='prediction_final.png')

    print("Training Completed.")
    
    # Plot training results
    vis.plot_training_losses(train_losses, [], is_supervised=True)
    
    # Save Models
    models_dir = 'outputs/models'
    if not os.path.exists(models_dir):
        os.makedirs(models_dir)
        
    # Sanitize ticker for filename
    safe_ticker = ticker.replace("=", "").replace("-", "")
    model_prefix = f"{models_dir}/{safe_ticker}_{train_timeframe}"
    
    torch.save(generator.state_dict(), f'{model_prefix}_generator.pth')
    # Discriminator removed - supervised LSTM only
    
    # Save Scaler (CRITICAL for live inference)
    import joblib
    joblib.dump(scaler, f'{model_prefix}_scaler.pkl')
    
    print(f"Models and Scaler saved to '{models_dir}' with prefix '{safe_ticker}_{train_timeframe}'.")
    
    # Save Model Config (Architecture & Timeframe)
    model_config = {
        "train_timeframe": train_timeframe,
        "trade_timeframe": trade_timeframe,
        "seq_length": seq_length,
        "hidden_dim": hidden_dim,
        "num_layers": num_layers,
        "asset_type": asset_type,
        "ticker": ticker,
        "last_training_date": datetime.now().strftime('%Y-%m-%d %H:%M')
    }
    with open(f'{model_prefix}_config.json', 'w') as f:
        json.dump(model_config, f, indent=4)
    print(f"Model Configuration saved to '{model_prefix}_config.json'.")
    
    # --- Final Metrics Report ---
    # --- Final Metrics Report ---
    print("\nCalculating Final Metrics...")
    print("\nCalculating Final Metrics...")
    
    generator.eval()
    
    print("Running Backtest Simulation...")
    # Create a sequential loader for the whole dataset (or test split)
    # We'll re-use the original df for simplicity to show full history backtest
    
    # Preprocess full df for prediction
    full_dataset, _ = preprocess_data(df, config.SEQ_LENGTH)
    full_loader = DataLoader(full_dataset, batch_size=config.BATCH_SIZE, shuffle=False)
    
    full_preds_scaled = []
    
    with torch.no_grad():
        for seq, _ in full_loader:
            seq = seq.to(config.DEVICE)
            pred = generator(seq).cpu().numpy()
            last_pred = pred[:, -1, 0] # Index 0 is Log_Ret_Close
            full_preds_scaled.extend(last_pred)
            
    # Inverse Transform Predictions
    num_features = scaler.n_features_in_
    dummy_preds = np.zeros((len(full_preds_scaled), num_features))
    dummy_preds[:, 0] = full_preds_scaled # Index 0
    
    inverse_preds = scaler.inverse_transform(dummy_preds)
    real_pred_returns = inverse_preds[:, 0] # These are Log Returns
    
    # Align predictions with DF
    valid_len = len(real_pred_returns)
    df_backtest = df.iloc[-valid_len:].copy()
    
    # Add Predicted Returns to DF
    df_backtest['Predicted_Return'] = real_pred_returns
    
    # --- FIX FOR BACKTESTER ---
    # The model predicts the return at time 't' (Close[t]/Close[t-1]).
    # To capture this, we must trade at 't-1'.
    # So for the backtester (which iterates row by row), at row 'i', 
    # we need the prediction for 'i+1'.
    df_backtest['Signal_Prediction'] = df_backtest['Predicted_Return'].shift(-1)
    
    # Run Backtester (Modified for Returns)
    # We pass the Predicted Return directly
    backtester = Backtester(initial_capital=10000)
    results, signals_df, final_capital = backtester.run_backtest(df_backtest, prediction_col='Signal_Prediction', price_col='Close', is_return=True)
    backtest_metrics = backtester.get_metrics()
    
    # Calculate technical metrics
    # RMSE on Returns (will be small)
    rmse = np.sqrt(mean_squared_error(df_backtest['Log_Ret_Close'], df_backtest['Predicted_Return']))
    # MAPE is not useful for returns (near zero). We use Directional Accuracy.
    # DA = Mean( Sign(Pred) == Sign(Real) )
    da = np.mean(np.sign(df_backtest['Predicted_Return']) == np.sign(df_backtest['Log_Ret_Close']))
    
    metrics = {
        'RMSE': rmse,
        'Accuracy': da # Renamed from MAPE
    }
    
    print("="*40)
    print("       FINAL MODEL REPORT")
    print("="*40)
    print(f"RMSE (Log Returns): {rmse:.5f}")
    print(f"Directional Accuracy: {da*100:.2f}%")
    print(f"Win Rate: {backtest_metrics['Win Rate']:.2f}%")
    print(f"Total Return: {backtest_metrics['Total Return %']:.2f}%")
    print("="*40)
    
    # --- Log History for Comparative Analysis ---
    history_file = 'history.json'
    history_entry = {
        'date': datetime.now().strftime('%Y-%m-%d %H:%M'),
        'ticker': ticker,
        'asset_type': asset_type,
        'timeframe': train_timeframe,
        'win_rate': backtest_metrics['Win Rate'],
        'total_return': backtest_metrics['Total Return %'],
        'mape': da
    }
    
    try:
        if os.path.exists(history_file):
            with open(history_file, 'r') as f:
                history = json.load(f)
        else:
            history = []
    except:
        history = []
        
    history.append(history_entry)
    with open(history_file, 'w') as f:
        json.dump(history, f, indent=4)
    
    # Generate Dashboard
    print("Generating Professional Dashboard...")
    dash_gen = DashboardGenerator()
    # Pass history to dashboard generator
    dashboard_path = dash_gen.generate_dashboard(ticker, metrics, backtest_metrics, signals_df, history, asset_type, timeframe=train_timeframe)
    
    # Enhanced dashboard opening logic
    abs_dashboard_path = os.path.abspath(dashboard_path)
    print(f"\n[SYSTEM] Dashboard generated successfully at: {abs_dashboard_path}")
    print(f"[SYSTEM] Tip: You can find all results in your 'Documents/Quantum Llama/outputs' folder.")
    
    if os.path.exists(abs_dashboard_path):
        print("Opening Dashboard in Browser...")
        try:
            webbrowser.open(f'file://{abs_dashboard_path}')
        except Exception as e:
            print(f"Warning: Could not open browser automatically: {e}")
    else:
        print(f"Error: Dashboard file not found at {abs_dashboard_path}")

if __name__ == "__main__":
    # Default fallback if run directly
    # ticker, period, epochs, asset_type, train_timeframe, trade_timeframe
    train_model("MNQ=F", "2y", 10, "Futures", "1h", "1h")
