import os
import base64
from datetime import datetime
class DashboardGenerator:
    def __init__(self, output_dir=None):
        from src.services.database import get_outputs_dir
        self.output_dir = output_dir or get_outputs_dir()
        self.plots_dir = os.path.join(self.output_dir, 'plots')
        self.html_path = os.path.join(self.output_dir, 'dashboard.html')
    def _encode_image(self, image_path):
        try:
            with open(image_path, "rb") as image_file:
                return base64.b64encode(image_file.read()).decode('utf-8')
        except FileNotFoundError:
            return None
    def generate_dashboard(self, ticker, metrics, backtest_metrics, signals_df, history=None, asset_type="Futures", timeframe="1h"):
        safe_ticker = ticker.replace("=", "").replace("-", "")
        prefix = f"{safe_ticker}_{timeframe}"
        img_correlation      = self._encode_image(os.path.join(self.plots_dir, f'{prefix}_correlation_matrix.png'))
        img_dashboard        = self._encode_image(os.path.join(self.plots_dir, f'{prefix}_technical_dashboard.png'))
        img_arima            = self._encode_image(os.path.join(self.plots_dir, f'{prefix}_arima_forecast.png'))
        img_gpr              = self._encode_image(os.path.join(self.plots_dir, f'{prefix}_gaussian_process.png'))
        img_sentiment        = self._encode_image(os.path.join(self.plots_dir, f'{prefix}_sentiment_analysis.png'))
        img_features         = self._encode_image(os.path.join(self.plots_dir, f'{prefix}_feature_importance.png'))
        img_fourier          = self._encode_image(os.path.join(self.plots_dir, f'{prefix}_fourier_analysis.png'))
        img_epoch_1          = self._encode_image(os.path.join(self.plots_dir, f'{prefix}_prediction_epoch_1.png'))
        img_epoch_50         = self._encode_image(os.path.join(self.plots_dir, f'{prefix}_prediction_epoch_50.png'))
        img_epoch_200        = self._encode_image(os.path.join(self.plots_dir, f'{prefix}_prediction_epoch_200.png'))
        img_final            = self._encode_image(os.path.join(self.plots_dir, f'{prefix}_prediction_final.png'))
        img_losses           = self._encode_image(os.path.join(self.plots_dir, f'{prefix}_training_losses.png'))
        img_features_overview = self._encode_image(os.path.join(self.plots_dir, f'{prefix}_features_overview.png'))
        rmse_color = "#a3e635" if metrics['RMSE'] < 0.001 else "#fb923c"
        acc_color  = "#a3e635" if metrics['Accuracy'] > 0.55 else "#fb923c" if metrics['Accuracy'] > 0.50 else "#f87171"
        advice = "El modelo muestra un rendimiento sólido."
        if metrics['Accuracy'] < 0.50:
            advice = "El modelo no está aprendiendo (Accuracy < 50%). Se recomienda revisar los datos o hiperparámetros."
        elif metrics['Accuracy'] < 0.55:
            advice = "El modelo es aceptable pero podría mejorar. Intenta ajustar el Learning Rate o añadir más indicadores."
        last_signals   = signals_df.tail(10)
        latest_signal  = last_signals.iloc[-1]
        current_price  = latest_signal['Price']
        signal_type    = latest_signal['Signal']
        volatility     = signals_df['Price'].tail(20).std()
        sl_points      = volatility * 1.5
        tp_points      = volatility * 2.5
        if signal_type == "BUY":
            rec_sl = current_price - sl_points
            rec_tp = current_price + tp_points
            sig_color  = "var(--green)"
            sig_icon   = "▲"
            sig_label  = "LONG"
        elif signal_type == "SELL":
            rec_sl = current_price + sl_points
            rec_tp = current_price - tp_points
            sig_color  = "var(--red)"
            sig_icon   = "▼"
            sig_label  = "SHORT"
        else:
            rec_sl = rec_tp = 0
            sig_color = "var(--muted)"
            sig_icon  = "◆"
            sig_label = "NEUTRAL"
        rr_ratio = tp_points / sl_points if sl_points > 0 else 0
        signals_html = ""
        for _, row in last_signals.iterrows():
            badge_cls = "badge-buy" if row['Signal'] == "BUY" else "badge-sell" if row['Signal'] == "SELL" else "badge-hold"
            signals_html += f"""
            <tr>
                <td class="mono">{row['Date'].strftime('%m/%d %H:%M')}</td>
                <td class="mono">{row['Price']:.2f}</td>
                <td class="mono">{row['Prediction']:.2f}</td>
                <td><span class="badge {badge_cls}">{row['Signal']}</span></td>
                <td class="muted">{row['Position']}</td>
            </tr>"""
        comparative_html = ""
        if history:
            import pandas as pd
            hist_df = pd.DataFrame(history)
            if not hist_df.empty and 'asset_type' in hist_df.columns:
                perf_by_type = hist_df.groupby('asset_type')[['win_rate', 'total_return']].mean().reset_index()
                best_asset   = perf_by_type.loc[perf_by_type['total_return'].idxmax()]
                rows_html = ""
                for _, row in perf_by_type.iterrows():
                    latest_date = hist_df[hist_df['asset_type'] == row['asset_type']]['date'].max()
                    rows_html += f"""
                    <tr>
                        <td>{row['asset_type']}</td>
                        <td class="mono">{row['win_rate']:.2f}%</td>
                        <td class="mono">{row['total_return']:.2f}%</td>
                        <td class="muted mono">{latest_date}</td>
                    </tr>"""
                comparative_html = f"""
                <section class="section-block">
                    <div class="section-header"><span class="section-icon">🏆</span>Análisis Comparativo Multi-Activo</div>
                    <div class="comp-best">
                        <span class="label">Mejor Clase de Activo</span>
                        <span class="big-val accent">{best_asset['asset_type']}</span>
                        <span class="label">Retorno Promedio: {best_asset['total_return']:.2f}%</span>
                    </div>
                    <table class="data-table" style="margin-top:12px">
                        <thead><tr><th>Activo</th><th>Win Rate</th><th>Retorno</th><th>Último</th></tr></thead>
                        <tbody>{rows_html}</tbody>
                    </table>
                </section>"""
        doc_content = ""
        try:
            # Resolve documentation path correctly in development and production
            if getattr(sys, 'frozen', False):
                # In production (bundled), find inside the extraction directory
                base_path = getattr(sys, '_MEIPASS', os.path.dirname(sys.executable))
                doc_path = os.path.join(base_path, "src", "doctecnicaalgos", "EvolutionaryGAN.md")
            else:
                # In development, find relative to the current working directory or script
                doc_path = os.path.abspath("src/doctecnicaalgos/EvolutionaryGAN.md")

            if os.path.exists(doc_path):
                import re
                def slugify(t): return t.lower().replace(" ", "-").replace(".", "").replace(":", "")
                with open(doc_path, "r", encoding="utf-8") as f:
                    doc_lines = f.readlines()
                html_doc = ""
                for line in doc_lines:
                    line = line.strip()
                    line = re.sub(r'\[(.*?)\]\((.*?)\)', r'<a href="\2">\1</a>', line)
                    if line.startswith("# "):       html_doc += f"<h1 class='doc-title'>{line[2:]}</h1>"
                    elif line.startswith("## "):    html_doc += f"<h2 id='{slugify(line[3:])}' class='doc-section'>{line[3:]}</h2>"
                    elif line.startswith("### "):   html_doc += f"<h3 class='doc-subsection'>{line[4:]}</h3>"
                    elif line.startswith("* "):     html_doc += f"<li class='doc-item'>{line[2:]}</li>"
                    elif line.startswith("!["):
                        m = re.search(r'!\[(.*?)\]\((.*?)\)', line)
                        if m: html_doc += f"<div style='text-align:center;margin:16px 0'><img src='{m.group(2)}' alt='{m.group(1)}' style='max-width:100%;border-radius:6px'></div>"
                    elif line == "---":             html_doc += "<hr class='doc-divider'>"
                    elif line.startswith(("<div","</div","<h3","<p","<a")):
                        html_doc += line
                    elif line:
                        while "**" in line:
                            line = line.replace("**", "<strong>", 1).replace("**", "</strong>", 1)
                        html_doc += f"<p class='doc-text'>{line}</p>"
                doc_content = html_doc
        except Exception as e:
            doc_content = f"<p>Error loading documentation: {str(e)}</p>"
        def chart(b64, title, guide="", height="180px"):
            img_tag = f'<img src="data:image/png;base64,{b64}" alt="{title}">' if b64 else '<div class="no-img">Sin datos</div>'
            guide_html = f'<p class="chart-guide">{guide}</p>' if guide else ""
            return f"""
            <div class="chart-card">
                <div class="chart-title">{title}</div>
                <div class="chart-wrap" style="height:{height}" onclick="openLightbox(this)">
                    {img_tag}
                    <span class="zoom-hint">⊕ zoom</span>
                </div>
                {guide_html}
            </div>"""
        html_content = f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Quantum AI · {ticker}</title>
<link rel="icon" href="https://llamaterminal.nbmsystemas.com/llama-logo.png" type="image/png">
<link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;600&family=DM+Sans:wght@300;400;600;700&display=swap" rel="stylesheet">
<style>
/* ── Reset & Base ────────────────────────────────── */
*, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
:root {{
  --bg:       #070709;
  --surface:  #0d0d10;
  --border:   rgba(255,255,255,0.06);
  --border-s: rgba(255,255,255,0.12);
  --text:     #d4d4d8;
  --muted:    #52525b;
  --accent:   #a78bfa;
  --accent2:  #60a5fa;
  --green:    #4ade80;
  --red:      #f87171;
  --orange:   #fb923c;
  --yellow:   #fbbf24;
  --r: 8px;
}}
html {{ font-size: 13px; scroll-behavior: smooth; }}
body {{
  font-family: 'DM Sans', sans-serif;
  background: var(--bg);
  color: var(--text);
  min-height: 100vh;
  padding: 0;
  background-image:
    radial-gradient(ellipse 60% 40% at 80% 0%, rgba(167,139,250,0.05) 0%, transparent 60%),
    radial-gradient(ellipse 40% 30% at 0% 80%, rgba(96,165,250,0.04) 0%, transparent 50%);
}}
.mono {{ font-family: 'IBM Plex Mono', monospace; font-size: 0.85em; }}
.muted {{ color: var(--muted); }}
.accent {{ color: var(--accent); }}
/* ── Layout ─────────────────────────────────────── */
.shell {{
  max-width: 1280px;
  margin: 0 auto;
  padding: 16px 20px 40px;
}}
/* ── Top Bar ─────────────────────────────────────── */
.topbar {{
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 0 14px;
  border-bottom: 1px solid var(--border);
  margin-bottom: 16px;
}}
.topbar-brand {{ display: flex; align-items: center; gap: 10px; }}
.topbar-logo {{
  width: 32px; height: 32px;
  border-radius: 8px;
  object-fit: contain;
  background: rgba(167,139,250,0.08);
  border: 1px solid rgba(167,139,250,0.2);
  padding: 3px;
  filter: drop-shadow(0 0 6px rgba(167,139,250,0.3));
}}
.topbar-name {{
  font-size: 0.95rem;
  font-weight: 700;
  letter-spacing: -0.02em;
  background: linear-gradient(90deg, var(--accent), var(--accent2));
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
}}
.topbar-sub {{ font-size: 0.7rem; color: var(--muted); letter-spacing: 0.06em; text-transform: uppercase; }}
.topbar-right {{ display: flex; align-items: center; gap: 12px; }}
.ticker-pill {{
  display: flex; align-items: center; gap: 8px;
  background: var(--surface);
  border: 1px solid var(--border-s);
  border-radius: 6px;
  padding: 5px 10px;
}}
.ticker-sym {{ font-family: 'IBM Plex Mono', monospace; font-weight: 600; font-size: 0.9rem; color: #fff; }}
.ticker-meta {{ font-size: 0.7rem; color: var(--muted); }}
.doc-btn {{
  font-family: 'DM Sans', sans-serif;
  font-size: 0.75rem; font-weight: 600;
  padding: 5px 12px;
  border: 1px solid rgba(167,139,250,0.3);
  background: rgba(167,139,250,0.06);
  color: var(--accent);
  border-radius: 6px;
  cursor: pointer;
  transition: all .2s;
  letter-spacing: 0.02em;
}}
.doc-btn:hover {{ background: rgba(167,139,250,0.15); border-color: var(--accent); }}
/* ── Signal Banner ───────────────────────────────── */
.signal-banner {{
  display: grid;
  grid-template-columns: auto 1fr auto;
  align-items: center;
  gap: 16px;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--r);
  padding: 14px 18px;
  margin-bottom: 14px;
  position: relative;
  overflow: hidden;
}}
.signal-banner::before {{
  content: '';
  position: absolute;
  left: 0; top: 0; bottom: 0;
  width: 3px;
  background: var(--sig-color);
  border-radius: 2px 0 0 2px;
}}
.signal-type {{
  display: flex; flex-direction: column; gap: 2px;
}}
.signal-label {{
  font-size: 0.65rem; text-transform: uppercase; letter-spacing: 0.1em; color: var(--muted);
}}
.signal-val {{
  font-family: 'IBM Plex Mono', monospace;
  font-size: 1.4rem; font-weight: 600;
  color: var(--sig-color);
  line-height: 1;
}}
.signal-levels {{
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 10px;
}}
.level-box {{
  display: flex; flex-direction: column; align-items: center;
  background: rgba(255,255,255,0.025);
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 8px 10px;
  gap: 2px;
}}
.level-tag {{ font-size: 0.6rem; text-transform: uppercase; letter-spacing: 0.08em; }}
.level-num {{ font-family: 'IBM Plex Mono', monospace; font-size: 0.9rem; font-weight: 600; color: #fff; }}
.level-sub {{ font-size: 0.65rem; color: var(--muted); }}
.signal-price {{
  text-align: right;
}}
.price-val {{ font-family: 'IBM Plex Mono', monospace; font-size: 1.6rem; font-weight: 600; color: #fff; line-height: 1; }}
.price-label {{ font-size: 0.65rem; color: var(--muted); margin-top: 2px; }}
.sig-note {{
  grid-column: 1 / -1;
  font-size: 0.72rem; color: var(--muted);
  padding: 7px 10px;
  background: rgba(255,255,255,0.02);
  border: 1px solid var(--border);
  border-radius: 5px;
}}
/* ── Advice ──────────────────────────────────────── */
.advice {{
  display: flex; align-items: flex-start; gap: 10px;
  background: rgba(167,139,250,0.04);
  border: 1px solid rgba(167,139,250,0.12);
  border-radius: var(--r);
  padding: 10px 14px;
  margin-bottom: 14px;
  font-size: 0.8rem; color: var(--text);
}}
.advice-icon {{ font-size: 0.9rem; flex-shrink: 0; margin-top: 1px; }}
/* ── Metrics Row ─────────────────────────────────── */
.metrics-row {{
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 10px;
  margin-bottom: 14px;
}}
.metric-card {{
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--r);
  padding: 12px 14px;
  transition: border-color .2s;
}}
.metric-card:hover {{ border-color: var(--border-s); }}
.metric-label {{ font-size: 0.65rem; text-transform: uppercase; letter-spacing: 0.08em; color: var(--muted); margin-bottom: 6px; }}
.metric-val {{ font-family: 'IBM Plex Mono', monospace; font-size: 1.35rem; font-weight: 600; line-height: 1; }}
/* ── Section Block ───────────────────────────────── */
.section-block {{
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--r);
  padding: 14px 16px;
  margin-bottom: 14px;
}}
.section-header {{
  display: flex; align-items: center; gap: 6px;
  font-size: 0.75rem; font-weight: 600; text-transform: uppercase;
  letter-spacing: 0.08em; color: var(--muted);
  margin-bottom: 12px;
}}
.section-icon {{ font-size: 0.85rem; }}
/* ── Chart Grids ─────────────────────────────────── */
.grid-2  {{ display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }}
.grid-3  {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px; }}
.grid-4  {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 10px; }}
@media(max-width:900px) {{ .grid-3,.grid-4 {{ grid-template-columns: 1fr 1fr; }} }}
@media(max-width:600px) {{ .grid-2,.grid-3,.grid-4,.metrics-row {{ grid-template-columns: 1fr; }} }}
/* ── Chart Card ──────────────────────────────────── */
.chart-card {{
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--r);
  overflow: hidden;
  transition: border-color .2s;
}}
.chart-card:hover {{ border-color: var(--border-s); }}
.chart-title {{
  font-size: 0.68rem; font-weight: 600;
  text-transform: uppercase; letter-spacing: 0.07em;
  color: var(--muted);
  padding: 8px 10px 0;
}}
.chart-wrap {{
  position: relative; cursor: zoom-in;
  display: flex; align-items: center; justify-content: center;
  background: #09090c;
  overflow: hidden;
  margin: 6px;
  border-radius: 5px;
}}
.chart-wrap img {{ max-width: 100%; max-height: 100%; object-fit: contain; display: block; transition: transform .3s; }}
.chart-wrap:hover img {{ transform: scale(1.03); }}
.zoom-hint {{
  position: absolute; bottom: 5px; right: 6px;
  font-size: 0.6rem; font-family: 'IBM Plex Mono', monospace;
  color: rgba(255,255,255,0.2);
  pointer-events: none;
  transition: opacity .2s;
}}
.chart-wrap:hover .zoom-hint {{ opacity: 1; color: var(--accent); }}
.chart-guide {{
  font-size: 0.68rem; color: var(--muted);
  padding: 6px 10px 9px;
  line-height: 1.5;
}}
.chart-guide strong {{ color: var(--accent); font-weight: 600; }}
.no-img {{
  height: 100%; display: flex; align-items: center; justify-content: center;
  color: var(--muted); font-size: 0.75rem; font-family: 'IBM Plex Mono', monospace;
}}
/* ── Evolution Gallery ───────────────────────────── */
.evo-gallery {{
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 10px;
}}
@media(max-width:900px) {{ .evo-gallery {{ grid-template-columns: 1fr 1fr; }} }}
.evo-item {{ position: relative; }}
.evo-label {{
  font-size: 0.6rem; text-transform: uppercase; letter-spacing: 0.1em;
  color: var(--accent); margin-bottom: 4px; padding: 0 10px;
  padding-top: 8px;
}}
/* ── Comparative ─────────────────────────────────── */
.comp-best {{
  display: flex; align-items: center; gap: 12px;
  padding: 10px 12px;
  background: rgba(167,139,250,0.05);
  border: 1px solid rgba(167,139,250,0.12);
  border-radius: 6px;
  margin-bottom: 10px;
}}
.comp-best .big-val {{ font-family: 'IBM Plex Mono', monospace; font-size: 1.2rem; font-weight: 600; }}
.label {{ font-size: 0.65rem; color: var(--muted); }}
/* ── Data Table ──────────────────────────────────── */
.data-table {{ width: 100%; border-collapse: collapse; }}
.data-table th {{
  font-size: 0.65rem; text-transform: uppercase; letter-spacing: 0.07em;
  color: var(--muted); font-weight: 600;
  padding: 6px 8px; border-bottom: 1px solid var(--border);
  text-align: left;
}}
.data-table td {{ padding: 7px 8px; border-bottom: 1px solid var(--border); font-size: 0.8rem; }}
.data-table tr:last-child td {{ border-bottom: none; }}
.data-table tr:hover td {{ background: rgba(255,255,255,0.02); }}
/* ── Badges ──────────────────────────────────────── */
.badge {{
  font-family: 'IBM Plex Mono', monospace;
  font-size: 0.62rem; font-weight: 600;
  padding: 2px 6px; border-radius: 4px;
  text-transform: uppercase; letter-spacing: 0.05em;
  display: inline-block;
}}
.badge-buy  {{ background: rgba(74,222,128,0.1); color: var(--green); border: 1px solid rgba(74,222,128,0.2); }}
.badge-sell {{ background: rgba(248,113,113,0.1); color: var(--red);   border: 1px solid rgba(248,113,113,0.2); }}
.badge-hold {{ background: rgba(113,113,122,0.1); color: var(--muted); border: 1px solid rgba(113,113,122,0.2); }}
/* ── Lightbox ────────────────────────────────────── */
.lightbox {{
  display: none; position: fixed;
  inset: 0; z-index: 9999;
  background: rgba(0,0,0,0.96);
  justify-content: center; align-items: center;
  cursor: zoom-out;
}}
.lightbox img {{
  max-width: 92vw; max-height: 88vh;
  object-fit: contain;
  border: 1px solid rgba(167,139,250,0.3);
  border-radius: 8px;
  box-shadow: 0 0 60px rgba(167,139,250,0.12);
}}
/* ── Doc Modal ───────────────────────────────────── */
.doc-modal {{
  display: none; position: fixed;
  inset: 0; z-index: 9998;
  background: rgba(0,0,0,0.92);
  justify-content: center; align-items: center;
}}
.doc-content {{
  background: var(--surface);
  border: 1px solid rgba(167,139,250,0.2);
  border-radius: 12px;
  width: 80%; max-width: 860px; height: 85%;
  padding: 36px 40px;
  overflow-y: auto;
  position: relative;
  box-shadow: 0 0 80px rgba(167,139,250,0.08);
}}
.doc-content::-webkit-scrollbar {{ width: 4px; }}
.doc-content::-webkit-scrollbar-thumb {{ background: rgba(167,139,250,0.2); border-radius: 4px; }}
.close-doc {{
  position: absolute; top: 16px; right: 18px;
  font-size: 1.2rem; color: var(--muted);
  background: none; border: none; cursor: pointer;
  transition: color .2s;
}}
.close-doc:hover {{ color: #fff; }}
.doc-title {{ color: var(--accent); font-size: 1.3rem; border-bottom: 1px solid var(--border); padding-bottom: 10px; margin-bottom: 16px; }}
.doc-section {{ color: #fff; margin-top: 24px; margin-bottom: 6px; font-size: 1rem; }}
.doc-subsection {{ color: var(--text); font-size: 0.9rem; margin-bottom: 4px; }}
.doc-text {{ color: var(--muted); line-height: 1.7; font-size: 0.85rem; margin-bottom: 8px; }}
.doc-item {{ color: var(--muted); font-size: 0.85rem; margin-left: 18px; margin-bottom: 4px; list-style: disc; }}
.doc-divider {{ border: none; border-top: 1px solid var(--border); margin: 20px 0; }}
/* ── Footer ──────────────────────────────────────── */
footer {{
  border-top: 1px solid var(--border);
  margin-top: 32px;
  padding-top: 16px;
  text-align: center;
  font-size: 0.7rem; color: var(--muted);
}}
footer a {{ color: var(--accent); text-decoration: none; }}
/* ── Scrollbar ───────────────────────────────────── */
::-webkit-scrollbar {{ width: 5px; height: 5px; }}
::-webkit-scrollbar-track {{ background: var(--bg); }}
::-webkit-scrollbar-thumb {{ background: rgba(255,255,255,0.08); border-radius: 4px; }}
</style>
</head>
<body>
<!-- Lightbox -->
<div id="lightbox" class="lightbox" onclick="closeLightbox()">
  <img id="lightbox-img" src="" alt="">
</div>
<!-- Doc Modal -->
<div id="doc-modal" class="doc-modal">
  <div class="doc-content">
    <button class="close-doc" onclick="closeDoc()">✕</button>
    {doc_content}
  </div>
</div>
<div class="shell">
  <!-- Top Bar -->
  <header class="topbar">
    <div class="topbar-brand">
      <img src="https://llamaterminal.nbmsystemas.com/llama-logo.png" alt="Logo" class="topbar-logo">
      <div>
        <div class="topbar-name">Quantum AI Laboratory</div>
        <div class="topbar-sub">Multi-Asset Neural Prediction</div>
      </div>
    </div>
    <div class="topbar-right">
      <div class="ticker-pill">
        <div>
          <div class="ticker-sym">{ticker}</div>
          <div class="ticker-meta">{asset_type} · {timeframe} · {datetime.now().strftime('%Y-%m-%d %H:%M')}</div>
        </div>
      </div>
      <button class="doc-btn" onclick="openDoc()">📘 Documentación</button>
    </div>
  </header>
  <!-- Advice -->
  <div class="advice">
    <span class="advice-icon">💡</span>
    <span><strong>Análisis del Sistema:</strong> {advice}</span>
  </div>
  <!-- Signal Banner -->
  <div class="signal-banner" style="--sig-color:{sig_color}">
    <div class="signal-type">
      <span class="signal-label">Señal Actual</span>
      <span class="signal-val">{sig_icon} {sig_label}</span>
    </div>
    <div class="signal-levels">
      <div class="level-box">
        <span class="level-tag" style="color:var(--red)">Stop Loss</span>
        <span class="level-num">{rec_sl:.2f}</span>
        <span class="level-sub">−{sl_points:.2f} pts</span>
      </div>
      <div class="level-box">
        <span class="level-tag" style="color:var(--yellow)">Risk / Reward</span>
        <span class="level-num">1 : {rr_ratio:.1f}</span>
        <span class="level-sub">ratio</span>
      </div>
      <div class="level-box">
        <span class="level-tag" style="color:var(--green)">Take Profit</span>
        <span class="level-num">{rec_tp:.2f}</span>
        <span class="level-sub">+{tp_points:.2f} pts</span>
      </div>
    </div>
    <div class="signal-price">
      <div class="price-val">{current_price:.2f}</div>
      <div class="price-label">Precio Actual</div>
    </div>
    <div class="sig-note">
      <strong>Nota:</strong> Niveles dinámicos basados en volatilidad actual ({volatility:.2f} pts). Ajuste según su gestión de riesgo.
    </div>
  </div>
  <!-- Key Metrics -->
  <div class="metrics-row">
    <div class="metric-card">
      <div class="metric-label">RMSE (Error Pts)</div>
      <div class="metric-val" style="color:{rmse_color}">{metrics['RMSE']:.4f}</div>
    </div>
    <div class="metric-card">
      <div class="metric-label">Directional Accuracy</div>
      <div class="metric-val" style="color:{acc_color}">{metrics['Accuracy']*100:.2f}%</div>
    </div>
    <div class="metric-card">
      <div class="metric-label">Win Rate (Backtest)</div>
      <div class="metric-val" style="color:var(--green)">{backtest_metrics['Win Rate']:.1f}%</div>
    </div>
    <div class="metric-card">
      <div class="metric-label">Retorno Total</div>
      <div class="metric-val">{backtest_metrics['Total Return %']:.2f}%</div>
    </div>
  </div>
  <!-- Training Convergence + Features Overview -->
  <div class="section-block">
    <div class="section-header"><span class="section-icon">📉</span>Convergencia & Features</div>
    <div class="grid-2">
      {chart(img_losses, "Training Losses",
             "<strong>Cómo leerlo:</strong> Curvas G/D a lo largo del entrenamiento. Buscamos estabilidad y convergencia. Picos = inestabilidad.", "160px")}
      {chart(img_features_overview, "Features Overview",
             "<strong>Cómo leerlo:</strong> Variables de entrada normalizadas. Detecta anomalías en datos crudos antes del modelo.", "160px")}
    </div>
  </div>
  <!-- Evolution Gallery -->
  <div class="section-block">
    <div class="section-header"><span class="section-icon">🧬</span>Evolución del Aprendizaje</div>
    <div class="evo-gallery">
      <div class="chart-card">
        <div class="evo-label">Época 1 — Inicio</div>
        {chart(img_epoch_1, "", "<strong>Interpretación:</strong> Ruido inicial. El modelo adivina aleatoriamente.", "140px").replace('<div class="chart-card">', '').replace('</div>', '', 1).strip()}
      </div>
      <div class="chart-card">
        <div class="evo-label">Época 50 — Aprendiendo</div>
        {chart(img_epoch_50, "", "<strong>Interpretación:</strong> Primeras formas de onda. Capta volatilidad básica.", "140px").replace('<div class="chart-card">', '').replace('</div>', '', 1).strip()}
      </div>
      <div class="chart-card">
        <div class="evo-label">Época 200 — Madurez</div>
        {chart(img_epoch_200, "", "<strong>Interpretación:</strong> Ajuste fino. El error disminuye progresivamente.", "140px").replace('<div class="chart-card">', '').replace('</div>', '', 1).strip()}
      </div>
      <div class="chart-card">
        <div class="evo-label">Resultado Final</div>
        {chart(img_final, "", "<strong>Interpretación:</strong> Predicción optimizada. Mejor estimación del modelo.", "140px").replace('<div class="chart-card">', '').replace('</div>', '', 1).strip()}
      </div>
    </div>
  </div>
  <!-- Analysis Grid -->
  <div class="section-block">
    <div class="section-header"><span class="section-icon">🔬</span>Análisis Estadístico</div>
    <div class="grid-3">
      {chart(img_correlation, "Matriz de Correlación",
             "🟢 +1 = movimiento conjunto &nbsp;|&nbsp; 🔴 −1 = opuesto &nbsp;|&nbsp; VIX negativo = cobertura natural")}
      {chart(img_gpr, "Gaussian Process",
             "Zona sombreada = intervalo de confianza 95%. Banda estrecha = mayor certeza del modelo.")}
      {chart(img_arima, "Proyección ARIMA",
             "Tendencia estadística pura, independiente de la red neuronal. Referencia de media reversión.")}
    </div>
  </div>
  <!-- Technical Dashboard Full Width -->
  <div class="section-block">
    <div class="section-header"><span class="section-icon">📊</span>Dashboard Técnico</div>
    {chart(img_dashboard, "Indicadores Técnicos · Cruces de medias, MACD y señales",
           "Cruces de medias móviles, MACD e histogramas de momentum. Confirma o contradice la señal del modelo.", "320px")}
  </div>
  <!-- Sentiment + Features + Fourier -->
  <div class="section-block">
    <div class="section-header"><span class="section-icon">🌊</span>Sentimiento, Features & Ciclos</div>
    <div class="grid-3">
      {chart(img_sentiment, "Sentimiento (VIX)",
             "Picos de miedo extremo (VIX > 30) históricamente coinciden con oportunidades de compra.")}
      {chart(img_features, "Feature Importance",
             "Qué indicadores pesan más en la decisión del modelo. Úsalo para simplificar o enriquecer inputs.")}
      {chart(img_fourier, "Ciclos de Fourier",
             "Ciclos ocultos de mercado descompuestos en frecuencias. Ideal para detectar patrones cíclicos.")}
    </div>
  </div>
  <!-- Comparative Analysis -->
  {comparative_html}
  <!-- Signals Table -->
  <div class="section-block">
    <div class="section-header"><span class="section-icon">📡</span>Últimas Señales de Trading</div>
    <table class="data-table">
      <thead>
        <tr>
          <th>Fecha</th>
          <th>Precio Real</th>
          <th>Predicción</th>
          <th>Señal</th>
          <th>Posición</th>
        </tr>
      </thead>
      <tbody>{signals_html}</tbody>
    </table>
  </div>
  <footer>
    <p>&copy; {datetime.now().year} Quantum AI System &mdash; Powered by <a href="https://llamaterminal.nbmsystemas.com/">NBM Systems</a></p>
    <p style="margin-top:4px;opacity:.6">Disclaimer: Sistema educativo/investigación. Trading de futuros y cripto conlleva riesgo significativo de pérdida.</p>
  </footer>
</div>
<script>
function openLightbox(el) {{
  const img = el.querySelector('img');
  if (!img) return;
  document.getElementById('lightbox-img').src = img.src;
  document.getElementById('lightbox').style.display = 'flex';
}}
function closeLightbox() {{
  document.getElementById('lightbox').style.display = 'none';
}}
function openDoc() {{
  document.getElementById('doc-modal').style.display = 'flex';
}}
function closeDoc() {{
  document.getElementById('doc-modal').style.display = 'none';
}}
window.addEventListener('click', e => {{
  if (e.target.id === 'doc-modal') closeDoc();
}});
document.addEventListener('keydown', e => {{
  if (e.key === 'Escape') {{ closeLightbox(); closeDoc(); }}
}});
</script>
</body>
</html>"""
        with open(self.html_path, "w", encoding="utf-8") as f:
            f.write(html_content)
        return self.html_path