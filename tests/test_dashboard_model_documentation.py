"""Render the shipped reference with synthetic inputs, never model or market data."""
import base64
from html.parser import HTMLParser
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import types

import pandas as pd
import pytest

from src.utils.dashboard_gen import DashboardGenerator


REFERENCE = Path(__file__).resolve().parents[1] / "src/doctecnicaalgos/EvolutionaryGAN.md"
# Valid one-pixel PNG; no image library or browser required.
PIXEL = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jRZkAAAAASUVORK5CYII="


class RenderedText(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []

    def handle_data(self, data):
        self.parts.append(data)


@pytest.mark.parametrize("frozen", [False, True], ids=["development", "frozen"])
def test_dashboard_renders_current_model_reference_and_preserves_assets(monkeypatch, frozen):
    # Constructor imports database even with output_dir set. Isolate that unused
    # persistence resolver to avoid its import-time creation of runtime directories.
    database = types.ModuleType("src.services.database")
    database.get_outputs_dir = lambda: pytest.fail("explicit output_dir must be honored")
    monkeypatch.setitem(sys.modules, "src.services.database", database)

    with TemporaryDirectory(prefix="dashboard-reference-") as directory:
        root = Path(directory)
        monkeypatch.chdir(root)
        bundle = root / "bundle" if frozen else root
        doc = bundle / "src/doctecnicaalgos/EvolutionaryGAN.md"
        doc.parent.mkdir(parents=True)
        doc.write_bytes(REFERENCE.read_bytes())
        monkeypatch.setattr(sys, "frozen", frozen, raising=False)
        monkeypatch.setattr(sys, "_MEIPASS", str(bundle), raising=False)
        output = root / "report"
        plots = output / "plots"
        plots.mkdir(parents=True)
        (plots / "TEST_1h_training_losses.png").write_bytes(base64.b64decode(PIXEL))
        signals = pd.DataFrame({
            "Date": pd.date_range("2024-01-01", periods=3, freq="h"),
            "Price": [100.0, 101.0, 102.0],
            "Prediction": [0.001, 0.002, 0.003],
            "Signal": ["BUY", "HOLD", "HOLD"],
            "Position": ["LONG", "LONG", "LONG"],
        })
        path = DashboardGenerator(output_dir=str(output)).generate_dashboard(
            "TE-ST=", {"RMSE": 0.0012, "Accuracy": 0.52},
            {"Win Rate": 40.0, "Total Return %": -2.5}, signals,
            history=[{"asset_type": "Futures", "win_rate": 40.0,
                      "total_return": -2.5, "date": "2024-01-01"}],
            asset_type="Futures", timeframe="1h",
        )
        assert path == str(output / "dashboard.html")
        html = Path(path).read_text(encoding="utf-8")
        assert html.startswith("<!DOCTYPE html>")
        assert "<title>Quantum AI · TE-ST=</title>" in html
        assert 'id="doc-modal"' in html and "function openDoc()" in html
        assert 'id="lightbox"' in html and "function openLightbox(el)" in html
        assert f'src="data:image/png;base64,{PIXEL}"' in html
        assert 'class="no-img"' in html  # Missing optional charts still render.
        assert "52.00%" in html and "40.0%" in html and "-2.50%" in html
        assert 'class="badge badge-hold">HOLD' in html
        assert "https://fonts.googleapis.com/" in html
        assert "https://llamaterminal.nbmsystemas.com/llama-logo.png" in html

        modal = html.split('<div class="doc-content">', 1)[1].split('<div class="shell">', 1)[0]
        parser = RenderedText()
        parser.feed(modal)
        text = " ".join(" ".join(parser.parts).split())
        assert "Error loading documentation" not in text
        # Contract concepts, not a snapshot of prose or every sentence.
        for concept in ("supervised LSTM", "Tanh", "MSELoss", "historical UI",
                        "not a calibrated probability", "not an independent out-of-sample",
                        "not run by the shipped train.py", "no validated predictive profitability"):
            assert concept in text
        features = ("Log_Ret_Close", "Log_Ret_High", "Log_Ret_Low", "Log_Vol",
                    "RSI", "ADX", "ATR", "EMA")
        positions = [text.index(feature) for feature in features]
        assert positions == sorted(positions)
        for obsolete_promise in ("Nash Equilibrium", "Probabilidad del modelo > 0.6",
                                 "Validación robusta mediante discriminador",
                                 "guaranteed profits"):
            assert obsolete_promise not in text
