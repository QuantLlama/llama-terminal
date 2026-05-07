import os

path = '/run/media/pabloezm/Respaldos/Pltaforma_Terminal_Llama/src/platform/web/index.html'
with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

# Identificar la sección de scripts y reemplazarla limpiamente
head_start = content.find('<head>')
head_end = content.find('</head>')

new_head_content = """<head>
    <script>
(function () {
  try {
    const lastCharts = localStorage.getItem("last_charts");
    if (lastCharts && lastCharts.includes("BTC/USDT") && !lastCharts.includes(":")) {
      console.warn("Legacy symbol format detected. Purging localStorage.");
      localStorage.removeItem("last_charts");
      localStorage.removeItem("last_symbol");
      localStorage.removeItem("mt5_positions");
    }
  } catch (e) {}
})();
</script>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <meta name="description" content="Quantum Llama - Terminal de Trading Profesional." />
    <title>Quantum Llama - Professional Trading Terminal</title>
    <link rel="icon" href="/images/QuantumLLama.png" type="image/png" />
    
    <script crossorigin src="/lib/react.production.min.js"></script>
    <script crossorigin src="/lib/react-dom.production.min.js"></script>
    <script src="/lib/babel.min.js"></script>
    <script src="/lib/lightweight-charts.standalone.production.js?v=4.2.1"></script>
    <script src="/lib/supabase-js.js"></script>
    <script src="https://cdn.tailwindcss.com"></script>
    
    <script src="components/VolumeProfileEngine.js?v=2.4.7"></script>
    <script src="components/VolumeProfileRenderer.js?v=2.4.7"></script>
    <script src="components/FootprintRenderer.js?v=1.0.2"></script>
    <script type="text/babel" src="components/DashboardModal.js?v=2.4.7"></script>
    <script type="text/babel" src="components/BacktestPanel.js?v=2.4.7"></script>
    <script type="text/babel" src="components/PlatformLoader.js?v=2.4.7"></script>
    <script type="text/babel" src="components/GridSplitter.js?v=1.0.1"></script>
    <script type="text/babel" src="components/ChartPane.js?v=2.8.0"></script>
    <script type="text/babel" src="components/DOMEngine.js?v=2.4.8"></script>
    <script type="text/babel" src="components/DOMRenderer.js?v=2.4.8"></script>
    <script type="text/babel" src="components/DOMHeatmapOverlay.js?v=1.0.14"></script>
    <script type="text/babel" src="components/DOMHistogramOverlay.js?v=2.4.18"></script>
    <script type="text/babel" src="components/DOMPanel.js?v=2.4.8"></script>
    <script type="text/babel" src="components/PriceSmoothingOverlay.js?v=2.4.7"></script>
    <script type="text/babel" src="components/UserDrawingOverlay.js?v=2.8.8"></script>
    <script type="text/babel" src="components/OrderFlowOverlay.js?v=2.4.8"></script>
    <script type="text/babel" src="components/PositionOverlay.js?v=2.5.1"></script>
    <script type="text/babel" src="components/ChartComponent.js?v=2.7.5"></script>
    <script type="text/babel" src="components/VixCorrelationPanel.js?v=2.4.9"></script>
    <script type="text/babel" src="components/ChartSettingsModal.js?v=2.5.0"></script>
    <script type="text/babel" src="components/WorkspacesModal.js?v=1.0.0"></script>
    <script type="text/babel" src="components/DeltaGridOverlay.js?v=2.1.2"></script>
    <script type="text/babel" src="components/TpoRenderer.js?v=1.0.0"></script>
    <script type="text/babel" src="components/BigTradeOverlay.js?v=2.1.2"></script>
    <script type="text/babel" src="components/NumInput.js?v=2.4.7"></script>
    <script type="text/babel" src="components/OrderEntry_Professional.js?v=2.4.7"></script>

    <link href="https://cdn.jsdelivr.net/npm/@fortawesome/fontawesome-free@6.4.2/css/all.min.css" rel="stylesheet" crossorigin="anonymous" />
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;700&display=swap" rel="stylesheet" />
    <script src="lib/monaco/vs/loader.js"></script>
    <script type="text/babel" src="/components/SymbolSearchModal.js?v=2.4.8"></script>
    <script type="text/babel" src="/components/WizardModal.js?v=2.4.7"></script>
    <script type="text/babel" src="/components/MappingEditor.js?v=2.4.7"></script>
    <script type="text/babel" src="/components/AlgoPanel.js?v=2.4.8"></script>
    <script type="text/babel" src="/components/DashboardModals.js?v=2.4.7"></script>
    <script type="text/babel" src="/components/SettingsModal.js?v=2.4.7"></script>
    <script type="text/babel" src="/components/EconomicCalendar.js?v=2.4.7"></script>
    <script type="text/babel" src="/components/CandleTimer.js?v=2.4.7"></script>
    <script type="text/babel" src="components/PriceChangeIndicator.js?v=1.0.0"></script>
    <script type="text/babel" src="components/AlgoLab.js?v=2.5.0"></script>
    <script type="text/babel" src="/components/useTradeStream.js?v=2.4.7"></script>
    <script type="text/babel" src="/components/TapeConfigModal.js?v=2.4.7"></script>
    <script type="text/babel" src="/components/TapePanel.js?v=2.4.7"></script>
    <script type="text/babel" src="/components/LoginModal.js?v=2.4.7"></script>
"""

# Reconstruir el contenido
new_content = content[:head_start] + new_head_content + content[head_end:]

with open(path, 'w', encoding='utf-8') as f:
    f.write(new_content)
