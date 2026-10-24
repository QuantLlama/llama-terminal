"""CPU-only artifact contract checks; no existing outputs or venue access."""
import json
import sys
import types
from tempfile import TemporaryDirectory
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import pytest
import torch
from sklearn.preprocessing import MinMaxScaler

from src.data.loader import FEATURE_COLS
from src.models.generator import Generator


@pytest.fixture
def artifacts(monkeypatch):
    with TemporaryDirectory() as directory:
        root = Path(directory)
        (root / 'models').mkdir()
        import src.services.database as database
        monkeypatch.setattr(database, 'get_outputs_dir', lambda: str(root))
        import src.utils.device_utils as devices
        monkeypatch.setattr(devices, 'get_best_device', lambda: torch.device('cpu'))
        # live_trade's historical connector import instantiates a venue connector.
        connector = types.ModuleType('src.live.connector')
        connector.get_mt5_connector = lambda: pytest.fail('venue access forbidden')
        monkeypatch.setitem(sys.modules, 'src.live.connector', connector)
        from src.services.algo_engine.engine import AlgoEngine
        monkeypatch.setattr(AlgoEngine, '_instance', None)
        monkeypatch.setattr(AlgoEngine, '_setup_logging', lambda self: None)
        yield root, AlgoEngine('TEST', '1h')


def save_bundle(root, *, cols=None, dim=8, scaler_dim=8, named=False, generic=False):
    prefix = root if generic else root / 'models'
    paths = [prefix / name for name in (
        ('generator.pth', 'scaler.pkl', 'model_config.json') if generic else
        ('TEST_1h_generator.pth', 'TEST_1h_scaler.pkl', 'TEST_1h_config.json'))]
    model = Generator(dim, 4, 2, dim)
    torch.save(model.state_dict(), paths[0])
    data = np.arange(4 * scaler_dim).reshape(4, scaler_dim)
    if named:
        data = pd.DataFrame(data, columns=FEATURE_COLS[:scaler_dim])
    joblib.dump(MinMaxScaler((-1, 1)).fit(data), paths[1])
    conf = dict(hidden_dim=4, num_layers=2, seq_length=3)
    if cols is not None:
        conf.update(feature_cols=cols, input_dim=len(cols))
    paths[2].write_text(json.dumps(conf))
    return paths


@pytest.mark.parametrize('legacy', [False, True, 'config'])
@pytest.mark.parametrize('generic', [False, True])
def test_both_loaders_accept_proven_order_and_preserve_interface(artifacts, legacy, generic):
    root, engine = artifacts
    paths = save_bundle(root, cols=None if legacy is True else FEATURE_COLS,
                        named=legacy is True, generic=generic)
    if legacy == 'config':
        conf = json.loads(paths[2].read_text())
        del conf['input_dim']
        paths[2].write_text(json.dumps(conf))
    before = [p.read_bytes() for p in paths]
    assert engine.load_model() is True
    from src.live.live_trade import load_model_and_scaler
    model, scaler, device, timeframe, length = load_model_and_scaler('TEST', '1h')
    assert (str(device), timeframe, length) == ('cpu', '1h', 3)
    assert model(torch.zeros(1, 3, 8)).shape == (1, 3, 8)
    assert engine._model(torch.zeros(1, 3, 8)).shape == (1, 3, 8)
    assert tuple(model.feature_cols) == tuple(engine._feature_cols) == tuple(FEATURE_COLS)
    assert scaler.n_features_in_ == 8
    assert [p.read_bytes() for p in paths] == before


@pytest.mark.parametrize('case,error', [
    ('width', 'checkpoint width'), ('scaler', 'scaler width'),
    ('order', 'feature order'), ('unknown_seven', 'scaler width'),
    ('explicit_null', 'feature order'), ('legacy_input_dim', 'input_dim'),
    ('legacy_checkpoint', 'checkpoint width'),
    ('scaler_order', 'scaler feature order'), ('input_dim', 'input_dim'),
    ('seven', 'feature order'),
])
def test_rejection_is_clear_and_read_only(artifacts, caplog, case, error):
    root, engine = artifacts
    cols = list(reversed(FEATURE_COLS)) if case == 'order' else FEATURE_COLS
    if case == 'seven':
        cols = FEATURE_COLS[:7]
    legacy = case in ('unknown_seven', 'legacy_input_dim', 'legacy_checkpoint')
    paths = save_bundle(root, cols=None if legacy else cols,
                        dim=7 if case in ('width', 'seven', 'unknown_seven', 'legacy_checkpoint') else 8,
                        scaler_dim=7 if case in ('scaler', 'seven', 'unknown_seven') else 8)
    if case == 'scaler_order':
        scaler = joblib.load(paths[1])
        scaler.feature_names_in_ = np.array(list(reversed(FEATURE_COLS)))
        joblib.dump(scaler, paths[1])
    if case in ('input_dim', 'legacy_input_dim', 'explicit_null'):
        conf = json.loads(paths[2].read_text())
        if case == 'explicit_null':
            conf['feature_cols'] = None
        else:
            conf['input_dim'] = 7
        paths[2].write_text(json.dumps(conf))
    before = [p.read_bytes() for p in paths]
    assert engine.load_model() is False
    assert error in caplog.text
    assert engine._model is None
    from src.live.live_trade import load_model_and_scaler
    with pytest.raises(ValueError, match=error):
        load_model_and_scaler('TEST', '1h')
    assert [p.read_bytes() for p in paths] == before


@pytest.mark.parametrize('generic', [False, True])
def test_baseline_numpy_scaler_bundle_loads_in_both_public_apis(artifacts, generic):
    root, engine = artifacts
    paths = save_bundle(root, generic=generic)
    conf = json.loads(paths[2].read_text())
    conf.update(train_timeframe='1h', trade_timeframe='1m', asset_type='Futures',
                ticker='TEST', last_training_date='2026-01-01 00:00')
    paths[2].write_text(json.dumps(conf))
    assert 'feature_cols' not in conf and 'input_dim' not in conf
    assert not hasattr(joblib.load(paths[1]), 'feature_names_in_')
    before = [p.read_bytes() for p in paths]
    from src.live.live_trade import load_model_and_scaler
    result = load_model_and_scaler('TEST', '1h')
    assert len(result) == 5
    model, scaler, device, timeframe, length = result
    assert (str(device), timeframe, length) == ('cpu', '1h', 3)
    assert model(torch.zeros(1, 3, 8)).shape == (1, 3, 8)
    assert engine.load_model() is True
    assert engine._model(torch.zeros(1, 3, 8)).shape == (1, 3, 8)
    assert model.feature_cols == engine._feature_cols == FEATURE_COLS
    assert scaler.n_features_in_ == 8
    assert [p.read_bytes() for p in paths] == before


def test_failed_reload_preserves_working_model_and_status(artifacts):
    root, engine = artifacts
    paths = save_bundle(root, cols=FEATURE_COLS)
    assert engine.load_model()
    working_model, working_scaler = engine._model, engine._scaler
    status = engine.get_status()
    paths[2].write_text('{broken json')
    before = [p.read_bytes() for p in paths]
    assert engine.load_model() is False
    assert engine._model is working_model and engine._scaler is working_scaler
    assert engine.get_status() == status
    assert [p.read_bytes() for p in paths] == before


def test_training_metadata_is_validated_and_matches_feature_truth(artifacts):
    from src.models.artifacts import feature_metadata
    root, _ = artifacts
    paths = save_bundle(root, cols=FEATURE_COLS)
    state, scaler = torch.load(paths[0], weights_only=True), joblib.load(paths[1])
    assert feature_metadata(scaler, state) == dict(feature_cols=FEATURE_COLS, input_dim=8)
    scaler.n_features_in_ = 7
    with pytest.raises(ValueError, match='scaler width'):
        feature_metadata(scaler, state)


def test_service_inference_uses_loaded_order_and_training_ema(artifacts, monkeypatch):
    root, engine = artifacts
    save_bundle(root, cols=FEATURE_COLS)
    assert engine.load_model()
    from src.analysis.market_filter import MarketFilter
    monkeypatch.setattr(MarketFilter, 'calculate_indicators', lambda self, df: df.assign(RSI=50., ADX=25., ATR=1., EMA=-999.))
    monkeypatch.setattr(MarketFilter, 'check_conditions', lambda *args: (True, 'OK'))
    captured = []
    engine._model.register_forward_pre_hook(lambda model, args: captured.append(args[0].clone()))
    close = np.arange(1., 81.)
    df = pd.DataFrame(dict(Open=close, Close=close, High=close+1, Low=close-.5, Volume=close))
    _, _, metadata = engine._generate_signal(df)
    assert 'predicted_return' in metadata
    raw = engine._scaler.inverse_transform(captured[0][0].numpy())
    np.testing.assert_allclose(raw[:, -1], df.Close.ewm(span=20, adjust=False).mean().tail(3), rtol=1e-5)
