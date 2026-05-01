const { useState, useEffect, useRef } = React;
const DS = {
  card: "bg-[#0d0d0f]/95 border border-white/[0.06] rounded-2xl",
  label: "text-[9px] font-bold uppercase tracking-[0.15em] text-zinc-500",
  accent: "text-amber-500/80",
  bar: "w-full bg-white/5 rounded-full h-[3px] overflow-hidden"
};
const MetricBar = ({ label, value = 0, color = "bg-blue-500" }) =>
React.createElement("div", { className: "space-y-1.5" },
React.createElement("div", { className: "flex justify-between items-baseline" },
React.createElement("span", { className: DS.label }, label),
React.createElement("span", { className: "text-[10px] font-mono font-bold text-white" }, Math.round(value), "%")
),
React.createElement("div", { className: DS.bar },
React.createElement("div", {
  className: `h-full ${color} transition-all duration-700 ease-out`,
  style: { width: `${value}%` } }
)
)
);
const StatusPill = ({ status }) => {
  const map = {
    idle: { bg: "bg-zinc-800/50", dot: "bg-zinc-500", text: "text-zinc-500" },
    training: { bg: "bg-amber-900/20", dot: "bg-amber-400/80 animate-pulse", text: "text-amber-400/80" },
    active: { bg: "bg-amber-500/10", dot: "bg-amber-500/80 animate-pulse", text: "text-amber-500/80" }
  };
  const s = map[status] || map.idle;
  return (
    React.createElement("div", { className: `flex items-center gap-2 px-3 py-1.5 rounded-full ${s.bg} border border-white/[0.04] backdrop-blur-sm` },
    React.createElement("span", { className: `w-1.5 h-1.5 rounded-full ${s.dot}` }),
    React.createElement("span", { className: `text-[9px] font-bold font-mono uppercase tracking-widest ${s.text}` },
    status
    )
    ));
};
const ActionBtn = ({ icon, label, sub, onClick, variant = "default" }) => {
  const variants = {
    default: "border-white/[0.05] hover:border-white/20 hover:bg-white/[0.03]",
    amber: "border-amber-500/20 hover:border-amber-500/40 hover:bg-amber-500/[0.04] bg-amber-500/[0.02]",
    red: "border-red-500/20 hover:border-red-500/40 bg-red-900/5 hover:bg-red-900/10",
    blue: "border-sky-500/20 hover:border-sky-500/40 bg-sky-900/5 hover:bg-sky-900/10",
    green: "border-white/[0.05] hover:border-emerald-500/30 hover:bg-emerald-900/5"
  };
  const iconColors = {
    default: "text-zinc-500",
    amber: "text-amber-500/70",
    red: "text-red-400/80",
    blue: "text-sky-400/80",
    green: "text-zinc-500 group-hover:text-emerald-400/80"
  };
  return (
    React.createElement("button", {
      onClick: onClick,
      className: `group w-full flex items-center gap-3 px-4 py-3.5 border rounded-xl transition-all duration-200 text-left ${variants[variant]}` },
    React.createElement("div", { className: `w-8 h-8 rounded-lg flex items-center justify-center bg-white/[0.03] border border-white/[0.06] flex-shrink-0 transition-colors ${iconColors[variant]}` },
    React.createElement("i", { className: `fas ${icon} text-xs` })
    ),
    React.createElement("div", { className: "overflow-hidden" },
    React.createElement("div", { className: `text-[11px] font-bold truncate ${variant === "red" ? "text-red-300" : variant === "blue" ? "text-blue-300" : "text-gray-200 group-hover:text-white"} transition-colors` },
    label
    ),
    sub && React.createElement("div", { className: "text-[9px] text-gray-600 group-hover:text-gray-500 truncate transition-colors mt-0.5" }, sub)
    )
    ));
};
const LogLine = ({ log, index }) => {
  const isError = log.includes("Error");
  const isStart = log.includes("Iniciando");
  const color = isError ? "text-red-400" : isStart ? "text-sky-400" : "text-gray-400";
  return (
    React.createElement("div", { className: "group flex items-start gap-3 py-[3px] px-2 hover:bg-white/[0.025] rounded transition-colors" },
    React.createElement("span", { className: "text-[9px] font-mono text-white/10 select-none pt-px flex-shrink-0 w-6 text-right" },
    (index + 1).toString().padStart(2, "0")
    ),
    React.createElement("span", { className: `text-[10px] font-mono leading-relaxed ${color}` }, log)
    ));
};
const AlgoPanel = ({ indicators, refreshIndicators, onClose }) => {
  const [status, setStatus] = useState("idle");
  const [logs, setLogs] = useState([]);
  const logsEndRef = useRef(null);
  const [trainWizardOpen, setTrainWizardOpen] = useState(false);
  const [liveWizardOpen, setLiveWizardOpen] = useState(false);
  const [mappingOpen, setMappingOpen] = useState(false);
  const [dashOpen, setDashOpen] = useState(false);
  const [liveDashOpen, setLiveDashOpen] = useState(false);
  const [cleanConfirmOpen, setCleanConfirmOpen] = useState(false);
  const [availableModels, setAvailableModels] = useState([]);
  const [algorithms, setAlgorithms] = useState({});
  const [selectedAlgo, setSelectedAlgo] = useState("EvolutionaryGAN");
  const [telemetry, setTelemetry] = useState(null);
  const [accounts, setAccounts] = useState([]);
  useEffect(() => {
    const fetchAccounts = () => {
      fetch("/api/accounts").
      then((r) => r.json()).
      then((d) => setAccounts(d)).
      catch((e) => console.error("Accounts Fetch Error:", e));
    };
    fetchAccounts();
  }, []);
  useEffect(() => {
    if (logsEndRef.current) logsEndRef.current.scrollIntoView({ behavior: "smooth" });
  }, [logs]);
  useEffect(() => {
    const checkStatus = () => {
      fetch("/api/algo/status").
      then((r) => r.json()).
      then((d) => {
        if (d && d.status) {
          setStatus(d.status);
          if (d.status !== "idle") {
            fetch("/api/logs").
            then((r) => r.json()).
            then((lines) => {
              if (lines && lines.length > 0) setLogs(lines.map((l) => l.trim()));
            }).
            catch((e) => console.error(e));
          }
        }
      }).
      catch((e) => console.error("Status Check Error:", e));
    };
    checkStatus();
    const interval = setInterval(checkStatus, 1000);
    return () => clearInterval(interval);
  }, []);
  useEffect(() => {
    const fetchTelemetry = () => {
      fetch("/api/system/telemetry").
      then((r) => r.json()).
      then((d) => setTelemetry(d)).
      catch((e) => console.error("Telemetry Fetch Error:", e));
    };
    fetchTelemetry();
    const interval = setInterval(fetchTelemetry, 2500);
    return () => clearInterval(interval);
  }, []);
  useEffect(() => {
    fetch("/api/algorithms").
    then((r) => r.json()).
    then((data) => setAlgorithms(data)).
    catch((e) => console.error("Error fetching algorithms:", e));
  }, []);
  const addLog = (msg) => {
    setLogs((prev) => [...prev.slice(-19), `[${new Date().toLocaleTimeString()}] ${msg}`]);
  };
  const runTraining = async (data) => {
    setStatus("training");
    addLog(`Iniciando Entrenamiento: ${data.ticker} (${data.asset_type})`);
    const payload = {
      asset_type: data.asset_type, ticker: data.ticker,
      period: data.period || "2y", epochs: parseInt(data.epochs || 50),
      train_timeframe: data.train_tf || "1h", trade_timeframe: data.trade_tf || "1h",
      seq_length: 60, hidden_dim: 128, num_layers: 2
    };
    if (data.mode === "Scalping (1m)") {payload.train_timeframe = "1m";payload.trade_timeframe = "1m";payload.seq_length = 60;payload.hidden_dim = 64;} else
    if (data.mode === "Intraday (5m)") {payload.train_timeframe = "5m";payload.trade_timeframe = "5m";payload.seq_length = 48;payload.hidden_dim = 128;} else
    if (data.mode === "Intraday (10m)") {payload.train_timeframe = "10m";payload.trade_timeframe = "10m";payload.seq_length = 36;payload.hidden_dim = 128;} else
    if (data.mode === "Intraday (15m)") {payload.train_timeframe = "15m";payload.trade_timeframe = "15m";payload.seq_length = 32;payload.hidden_dim = 128;} else
    if (data.mode === "Intraday (30m)") {payload.train_timeframe = "30m";payload.trade_timeframe = "30m";payload.seq_length = 24;payload.hidden_dim = 192;payload.num_layers = 3;} else
    if (data.mode === "Swing (1h)") {payload.train_timeframe = "1h";payload.trade_timeframe = "1h";payload.seq_length = 24;payload.hidden_dim = 256;payload.num_layers = 3;}
    try {
      const res = await fetch("/api/algo/start", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) });
      const d = await res.json();
      addLog(d.message);
    } catch (e) {addLog(`Error: ${e.message}`);setStatus("idle");}
  };
  const runLive = async (data) => {
    setStatus("active");
    const selectedPlatform = data.platform || "mt5";
    addLog(`Iniciando LIVE TRADING en ${selectedPlatform.toUpperCase()} :: ${data.ticker} (${data.timeframe})`);
    try {
      let algoConfig = data.algo_config || {};
      if (data.algorithm === "FourierCycle" && Object.keys(algoConfig).length === 0) {
        algoConfig = { fourier_period: 120, harmonics_count: 8, projection_bars: 20, signal_threshold: 0.5, cooldown_bars: 5, reward_ratio: 2.5, position_size: 1 };
      }
      const sanitizedConfig = {};
      Object.entries(algoConfig).forEach(([key, value]) => {
        sanitizedConfig[key] = typeof value === "string" && !isNaN(value) ? parseFloat(value) : value;
      });
      const payload = {
        platform: selectedPlatform,
        account_id: data.account_id,
        asset_type: data.asset_type || "Futures",
        ticker: data.ticker, timeframe: data.timeframe,
        algorithm: data.algorithm || "EvolutionaryGAN",
        config: sanitizedConfig
      };
      const res = await fetch("/api/algo/live", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) });
      if (!res.ok) {const err = await res.json();throw new Error(err.detail || "Server Error");}
      const d = await res.json();
      addLog(d.message);
    } catch (e) {addLog(`Error: ${e.message}`);setStatus("idle");}
  };
  const gpu = telemetry?.gpu;
  const hasCuda = gpu?.cuda?.available;
  const hasGpu = gpu?.detected && gpu?.devices?.length > 0;
  const gpuLoad = hasGpu ? Math.round(gpu.devices[0].load || 0) : 0;
  const vramPct = hasGpu ?
  Math.round(gpu.devices[0].memory_used / gpu.devices[0].memory_total * 100) :
  0;
  const gpuTemp = hasGpu ? (gpu.devices[0].temperature || 0) : 0;
  const gpuBackend = gpu?.backend || 'none';
  const deviceName = hasCuda ? gpu.cuda.device_name : hasGpu ? gpu.devices[0].name : "System Processor";
  const gpuErrorDetail = !hasGpu && gpu?.error_detail ? gpu.error_detail : null;
  const gpuInfo = !hasGpu && gpu?.info ? gpu.info : null;
  const trainSteps = [
  {
    label: "Select Asset Class",
    description: "Choose the market type for the AI model.",
    render: (data, update) =>
    React.createElement("div", { className: "space-y-4" },
    React.createElement("p", { className: "text-xs text-gray-500" }, "Each asset class has specific feature engineering pipelines optimized for its volatility profile."),
    React.createElement("div", { className: "grid grid-cols-2 gap-2" },
    ["Futures", "Stocks", "Crypto", "ETF"].map((opt) =>
    React.createElement("div", { key: opt, onClick: () => update("asset_type", opt),
      className: `p-4 border rounded-xl cursor-pointer transition-all ${data.asset_type === opt ? "border-amber-500/50 bg-amber-500/10 text-white" : "border-white/[0.07] text-gray-400 hover:bg-white/5 hover:border-white/20"}` },
    React.createElement("div", { className: "font-bold text-sm mb-1" }, opt),
    React.createElement("div", { className: "text-[10px] opacity-60" },
    opt === "Crypto" ? "24/7 Volatility" : opt === "Futures" ? "Tick Data" : "Daily Close"
    )
    )
    )
    )
    )
  },
  {
    label: "Select Ticker",
    description: "Enter the symbol to train on.",
    render: (data, update) =>
    React.createElement("div", { className: "space-y-4" },
    React.createElement("p", { className: "text-xs text-gray-500" }, "Use Yahoo Finance format (e.g., BTC-USD, ES=F, AAPL). The system will fetch historical data automatically."),
    React.createElement("input", { autoFocus: true, type: "text", placeholder: "e.g. MNQ=F, AAPL, BTC-USD",
      value: data.ticker || "", onChange: (e) => update("ticker", e.target.value),
      className: "w-full bg-black border border-white/10 p-4 rounded-xl text-white outline-none focus:border-amber-500/50 text-lg font-mono tracking-wider transition-colors" })
    )
  },
  {
    label: "Strategy Mode",
    description: "Define the trading timeframe and style.",
    render: (data, update) =>
    React.createElement("div", { className: "space-y-4" },
    React.createElement("p", { className: "text-xs text-gray-500" }, "Select a preset to automatically configure lookback windows and prediction horizons."),
    React.createElement("div", { className: "space-y-2" },
    [
    { id: "Scalping (1m)", desc: "High frequency, 1m timeframe target." },
    { id: "Intraday (5m)", desc: "Balanced risk/reward, 5m timeframe." },
    { id: "Intraday (10m)", desc: "Medium frequency, 10m timeframe." },
    { id: "Intraday (15m)", desc: "Intraday standard, 15m timeframe." },
    { id: "Intraday (30m)", desc: "Lower frequency intraday, 30m." },
    { id: "Swing (1h)", desc: "Multi-day positions, 1h timeframe." },
    { id: "Custom", desc: "Manually configure all parameters." }].
    map((opt) =>
    React.createElement("div", { key: opt.id, onClick: () => update("mode", opt.id),
      className: `p-3 border rounded-xl cursor-pointer flex justify-between items-center transition-all ${data.mode === opt.id ? "border-amber-500/50 bg-amber-500/10 text-white" : "border-white/[0.07] text-gray-400 hover:bg-white/5"}` },
    React.createElement("span", { className: "font-bold text-sm" }, opt.id),
    React.createElement("span", { className: "text-[10px] opacity-50" }, opt.desc)
    )
    )
    )
    )
  },
  {
    label: "Configuration",
    description: "Fine-tune model hyperparameters.",
    render: (data, update) =>
    React.createElement("div", { className: "space-y-6" },
    React.createElement("p", { className: "text-xs text-gray-500" }, "Adjust training epochs and historical data range to prevent overfitting."),
    React.createElement("div", { className: "grid grid-cols-2 gap-6" },
    React.createElement("div", null,
    React.createElement("label", { className: "text-[10px] text-amber-500/80 font-bold block mb-2 uppercase tracking-wider" }, "Training Epochs"),
    React.createElement("input", { type: "number", min: "1", max: "1000", value: data.epochs || 50,
      onChange: (e) => update("epochs", e.target.value),
      className: "w-full bg-black border border-white/10 p-3 rounded-xl text-white outline-none focus:border-amber-500/50 transition-colors" }),
    React.createElement("div", { className: "text-[9px] text-gray-600 mt-1" }, "Recommended: 50\u2013200 for LSTM")
    ),
    React.createElement("div", null,
    React.createElement("label", { className: "text-[10px] text-amber-500/80 font-bold block mb-2 uppercase tracking-wider" }, "Historical Data"),
    React.createElement("select", { value: data.period || "2y", onChange: (e) => update("period", e.target.value),
      className: "w-full bg-black border border-white/10 p-3 rounded-xl text-white outline-none focus:border-amber-500/50 appearance-none transition-colors" },
    React.createElement("option", { value: "1mo" }, "1 Month (Testing)"),
    React.createElement("option", { value: "6mo" }, "6 Months (Scalping)"),
    React.createElement("option", { value: "1y" }, "1 Year (Intraday)"),
    React.createElement("option", { value: "2y" }, "2 Years (Standard)"),
    React.createElement("option", { value: "5y" }, "5 Years (Robust)"),
    React.createElement("option", { value: "max" }, "Max Available")
    )
    )
    )
    )
  }];
  const liveSteps = [
  {
    label: "Execution Platform",
    description: "Select where to deploy this strategy.",
    render: (data, update) =>
    React.createElement("div", { className: "space-y-3" },
    React.createElement("p", { className: "text-xs text-gray-500" }, "Choose the execution environment for live trading."),
    React.createElement("div", { className: "grid grid-cols-2 gap-3" },
    [
    { id: "mt5", name: "MetaTrader 5", icon: "fa-chart-bar", desc: "Futures, Forex & Stocks", color: "border-sky-500/50 bg-sky-500/10", accent: "text-sky-400", dot: "bg-sky-400" },
    { id: "tradovate", name: "Tradovate", icon: "fa-bolt", desc: "CME Futures", color: "border-emerald-500/50 bg-emerald-500/10", accent: "text-emerald-400", dot: "bg-emerald-400" },
    { id: "crypto", name: "Crypto Exchange", icon: "fa-coins", desc: "Spot & Perpetual", color: "border-amber-500/50 bg-amber-500/10", accent: "text-amber-400", dot: "bg-amber-400" }].
    map((p) =>
    React.createElement("div", {
      key: p.id,
      onClick: () => {
        update("platform", p.id);
        update("account_id", null);
        if (p.id === "crypto") update("asset_type", "Crypto");else
        if (p.id === "tradovate") update("asset_type", "Futures");
      },
      className: `p-4 border rounded-xl cursor-pointer transition-all ${data.platform === p.id ? p.color : "border-white/[0.07] hover:border-white/20 hover:bg-white/5"}` },
    React.createElement("div", { className: "flex items-center gap-3 mb-2" },
    React.createElement("div", { className: `w-9 h-9 rounded-xl flex items-center justify-center ${data.platform === p.id ? "bg-white/10" : "bg-white/5"}` },
    React.createElement("i", { className: `fas ${p.icon} text-sm ${data.platform === p.id ? p.accent : "text-gray-500"}` })
    ),
    React.createElement("div", null,
    React.createElement("div", { className: "font-bold text-sm text-white" }, p.name),
    React.createElement("div", { className: "text-[10px] text-gray-500" }, p.desc)
    )
    ),
    data.platform === p.id &&
    React.createElement("div", { className: `flex items-center gap-1.5 mt-1 text-[9px] font-bold uppercase tracking-wider ${p.accent}` },
    React.createElement("span", { className: `w-1.5 h-1.5 rounded-full ${p.dot} animate-pulse` }), "Selected"
    )
    )
    )
    )
    )
  },
  {
    label: "Account & Category",
    description: "Select specific account and market type.",
    render: (data, update) => {
      const filteredAccounts = accounts.filter((acc) => acc.platform === data.platform);
      return (
        React.createElement("div", { className: "space-y-6" },
        React.createElement("div", null,
        React.createElement("label", { className: "text-[10px] text-amber-500/80 font-bold block mb-2 uppercase tracking-wider" }, "Target Account"),
        React.createElement("div", { className: "space-y-2 max-h-40 overflow-y-auto custom-scrollbar pr-1" },
        filteredAccounts.length > 0 ?
        filteredAccounts.map((acc) =>
        React.createElement("div", { key: acc.id, onClick: () => update("account_id", acc.id),
          className: `p-3 border rounded-xl cursor-pointer flex justify-between items-center transition-all ${data.account_id === acc.id ? "border-amber-500/50 bg-amber-500/10 text-white" : "border-white/[0.07] text-gray-400 hover:bg-white/5"}` },
        React.createElement("div", null,
        React.createElement("div", { className: "font-bold text-xs" }, acc.name),
        React.createElement("div", { className: "text-[9px] opacity-60" }, acc.broker, " \u2022 ", acc.account_type)
        ),
        data.account_id === acc.id && React.createElement("i", { className: "fas fa-check-circle text-amber-500 text-xs" })
        )
        ) :
        React.createElement("div", { className: "p-4 bg-red-900/10 border border-red-500/20 rounded-xl text-[10px] text-red-400" }, "No account found for this platform. Please add one in Accounts first."
        )
        )
        ),
        React.createElement("div", null,
        React.createElement("label", { className: "text-[10px] text-amber-500/80 font-bold block mb-2 uppercase tracking-wider" }, "Asset Category"),
        React.createElement("div", { className: "grid grid-cols-2 gap-2" },
        ["Futures", "Stocks", "Crypto", "ETF", "Forex"].map((cat) =>
        React.createElement("button", { key: cat, onClick: () => update("asset_type", cat),
          className: `py-2 px-3 text-[10px] font-bold rounded-lg border transition-all ${data.asset_type === cat ? "bg-amber-500/20 text-amber-500 border-amber-500/50" : "bg-transparent text-gray-500 border-white/10 hover:border-white/30"}` },
        cat
        )
        )
        ),
        React.createElement("p", { className: "text-[9px] text-gray-600 mt-2 italic" }, "Matching logic will search this category first in Symbol Mappings.")
        )
        ));
    }
  },
  {
    label: "Select Algorithm",
    description: "Choose the trading logic to deploy.",
    render: (data, update) => {
      const algos = Object.keys(algorithms).length > 0 ?
      Object.keys(algorithms) :
      ["FourierCycle", "EvolutionaryGAN", "ReinforcementDQN", "SentimentAnalysis"];
      return (
        React.createElement("div", { className: "grid grid-cols-2 gap-2 max-h-[300px] overflow-y-auto pr-2" },
        algos.map((algo) =>
        React.createElement("div", { key: algo, onClick: () => {
            update("algorithm", algo);
            setSelectedAlgo(algo);
            if (algo === 'StrategyETF_Portfolio') {
              update("ticker", "ALL_ETF");
              update("asset_type", "ETF");
            } else if (data.ticker === 'ALL_ETF') {
              update("ticker", "");
            }
          },
          className: `p-3 border rounded-xl cursor-pointer flex justify-between items-center transition-all ${data.algorithm === algo ? "border-blue-500 bg-blue-500/10 text-white" : "border-white/[0.07] text-gray-400 hover:bg-white/5"}` },
        React.createElement("div", { className: "flex items-center gap-3" },
        React.createElement("div", { className: `w-8 h-8 rounded-lg flex items-center justify-center text-xs ${data.algorithm === algo ? "bg-blue-500 text-black" : "bg-white/5 text-gray-500"}` },
        React.createElement("i", { className: "fas fa-microchip" })
        ),
        React.createElement("div", null,
        React.createElement("span", { className: "font-bold text-sm block" }, algo),
        React.createElement("span", { className: "text-[9px] opacity-50" },
        algo === "FourierCycle" ? "Cycle Analysis & Projections" : algo === "EvolutionaryGAN" ? "Deep Learning Prediction" : algo === "ReinforcementDQN" ? "Adaptive Decision Making" : "Standard Logic"
        )
        )
        ),
        data.algorithm === algo && React.createElement("i", { className: "fas fa-check-circle text-blue-500 text-sm" })
        )
        )
        ));
    }
  },
  {
    label: "Parameters",
    description: "Configure strategy-specific settings.",
    render: (data, update) => {
      const algo = data.algorithm || selectedAlgo;
      const config = data.algo_config || {};
      const updateConfig = (k, v) => update("algo_config", { ...config, [k]: v });
      if (algo === "FourierCycle") {
        return (
          React.createElement("div", { className: "grid grid-cols-2 gap-4" },
          [
          { key: "fourier_period", label: "Base Period", def: 120, type: "int" },
          { key: "harmonics_count", label: "Harmonics", def: 8, type: "int" },
          { key: "signal_threshold", label: "Signal Threshold", def: 0.5, step: 0.1, type: "float" },
          { key: "projection_bars", label: "Projection Bars", def: 20, type: "int" }].
          map(({ key, label, def, step, type }) =>
          React.createElement("div", { key: key },
          React.createElement("label", { className: "text-[10px] text-gray-500 uppercase font-bold block mb-1" }, label),
          React.createElement("input", { type: "number", step: step, value: config[key] ?? def,
            onChange: (e) => updateConfig(key, type === "float" ? parseFloat(e.target.value) : parseInt(e.target.value)),
            className: "w-full bg-black border border-white/10 p-2 rounded-lg text-white text-xs outline-none focus:border-purple-500 transition-colors" })
          )
          )
          ));
      }
      if (algo?.includes("StrategyETF")) {
        return (
          React.createElement("div", { className: "grid grid-cols-2 gap-4" },
          [
          { key: "stop_loss", label: "Stop Loss (%)", def: 2.0, step: 0.1, type: "float" },
          { key: "take_profit", label: "Take Profit (%)", def: 4.0, step: 0.1, type: "float" },
          { key: "retrain_interval", label: "Retrain Days", def: 63, type: "int" },
          { key: "max_position_pct", label: "Max Alloc (%)", def: 0.25, step: 0.05, type: "float", hide: algo !== 'StrategyETF_Portfolio' }].
          filter((f) => !f.hide).map(({ key, label, def, step, type }) =>
          React.createElement("div", { key: key },
          React.createElement("label", { className: "text-[10px] text-gray-500 uppercase font-bold block mb-1" }, label),
          React.createElement("input", { type: "number", step: step, value: config[key] ?? def,
            onChange: (e) => updateConfig(key, type === "float" ? parseFloat(e.target.value) : parseInt(e.target.value)),
            className: "w-full bg-black border border-white/10 p-2 rounded-lg text-white text-xs outline-none focus:border-amber-500/50 transition-colors" })
          )
          )
          ));
      }
      return (
        React.createElement("div", { className: "space-y-4" },
        React.createElement("div", { className: "p-3 bg-yellow-900/10 border border-yellow-500/20 rounded-xl text-yellow-500 text-xs" }, "Using default configuration for ",
        React.createElement("b", null, algo), "."
        ),
        React.createElement("div", null,
        React.createElement("label", { className: "text-[10px] text-gray-500 uppercase font-bold block mb-1" }, "Risk per Trade (%)"),
        React.createElement("input", { type: "number", step: "0.1", value: config.risk_percent || 1.0,
          onChange: (e) => updateConfig("risk_percent", parseFloat(e.target.value)),
          className: "w-full bg-black border border-white/10 p-2 rounded-lg text-white text-xs outline-none focus:border-purple-500 transition-colors" })
        )
        ));
    }
  },
  {
    label: "Exec. Context",
    description: "Ticker and Timeframe setup.",
    render: (data, update) =>
    React.createElement("div", { className: "space-y-4" },
    React.createElement("div", null,
    React.createElement("label", { className: "text-[10px] text-gray-500 uppercase font-bold block mb-2" }, "Ticker Symbol"),
    React.createElement("div", { className: "relative" },
    React.createElement("input", { type: "text", placeholder: data.platform === 'crypto' ? 'e.g. BTCUSDT, ETHUSDT, SOLUSDT' : data.platform === 'tradovate' ? 'e.g. MNQH26, MESZ25' : 'e.g. EURUSD, NQ, MES',
      value: data.algorithm === 'StrategyETF_Portfolio' ? 'ALL_ETF' : data.ticker || '',
      onChange: (e) => update('ticker', e.target.value),
      disabled: data.algorithm === 'StrategyETF_Portfolio',
      className: `w-full bg-black border border-white/10 p-3 rounded-xl text-white font-mono tracking-wider outline-none focus:border-amber-500/50 transition-colors ${data.algorithm === 'StrategyETF_Portfolio' ? 'opacity-60 cursor-not-allowed' : ''}` }),
    data.algorithm === 'StrategyETF_Portfolio' &&
    React.createElement("div", { className: "absolute right-3 top-1/2 -translate-y-1/2 text-[8px] font-bold text-amber-500/60 uppercase" }, "Locked")
    ),
    data.platform === 'crypto' &&
    React.createElement("div", { className: "text-[9px] text-amber-500/60 mt-1 ml-1" }, "Use exchange format. Check Symbol Mapping for broker ticker.")
    ),
    React.createElement("div", null,
    React.createElement("label", { className: "text-[10px] text-gray-500 uppercase font-bold block mb-2" }, "Trading Timeframe"),
    React.createElement("div", { className: "grid grid-cols-4 gap-2" },
    ["1m", "5m", "10m", "15m", "30m", "1h", "4h", "1d"].map((tf) =>
    React.createElement("button", { key: tf, onClick: () => update("timeframe", tf),
      className: `py-2.5 text-xs font-bold rounded-lg border transition-all ${data.timeframe === tf ? "bg-white text-black border-white" : "bg-transparent text-gray-400 border-white/10 hover:border-white/30"}` },
    tf
    )
    )
    )
    )
    )
  }];
  return (
    React.createElement("div", { className: "h-full w-full bg-[#080809] text-white font-sans flex flex-col overflow-hidden" },
    React.createElement("header", { className: "flex-shrink-0 flex items-center justify-between px-6 py-4 border-b border-white/[0.06] bg-[#080809]/80 backdrop-blur-sm" },
    React.createElement("div", { className: "flex items-center gap-3" },
    React.createElement("div", { className: "w-10 h-10 rounded-xl bg-amber-500/10 border border-amber-500/20 flex items-center justify-center overflow-hidden flex-shrink-0" },
    React.createElement("img", { src: "/images/AlgoLab.png", alt: "AlgoLab", className: "w-full h-full object-cover scale-150" })
    ),
    React.createElement("div", null,
    React.createElement("h1", { className: "text-sm font-bold bg-clip-text text-transparent bg-gradient-to-r from-amber-200 to-amber-500/70 leading-tight" }, "Quantum AI Laboratory"
    ),
    React.createElement("p", { className: `${DS.label} mt-0.5` }, "Neural Network & Algo Trading Hub")
    )
    ),
    React.createElement("div", { className: "flex items-center gap-4" },
    React.createElement(StatusPill, { status: status }),
    React.createElement("div", { className: "w-px h-6 bg-white/[0.08]" }),
    React.createElement("button", { onClick: onClose,
      className: "flex items-center gap-2 px-4 py-2 bg-white/[0.03] hover:bg-white/[0.07] border border-white/[0.08] hover:border-amber-500/30 rounded-full transition-all group" },
    React.createElement("i", { className: "fas fa-chart-line text-amber-500/60 text-xs group-hover:scale-110 transition-transform" }),
    React.createElement("span", { className: "text-[10px] font-bold text-gray-400 group-hover:text-white uppercase tracking-wider" }, "Ver Gr\xE1fico")
    )
    )
    ),
    React.createElement("div", { className: "flex flex-1 gap-5 p-5 overflow-hidden min-h-0" },
    React.createElement("aside", { className: "w-72 flex flex-col gap-4 overflow-y-auto flex-shrink-0 pr-1 custom-scrollbar" },
    React.createElement("section", { className: `${DS.card} p-4 flex-shrink-0` },
    React.createElement("h3", { className: `${DS.label} mb-3 flex items-center gap-2` },
    React.createElement("i", { className: "fas fa-bolt text-amber-500/80" }), "AI Operations"
    ),
    React.createElement("div", { className: "space-y-2" },
    React.createElement(ActionBtn, {
      icon: "fa-robot", label: "Train New Model",
      sub: "Design, train and validate neural networks",
      onClick: () => setTrainWizardOpen(true),
      variant: "amber" }
    ),
    status === "active" ?
    React.createElement(React.Fragment, null,
    React.createElement(ActionBtn, { icon: "fa-stop-circle", label: "DETENER ALGORITMO", onClick: () => fetch("/api/algo/stop", { method: "POST" }).then(() => setStatus("idle")), variant: "red" }),
    React.createElement(ActionBtn, { icon: "fa-external-link-alt", label: "Dashboard en Vivo", onClick: () => setLiveDashOpen(true), variant: "blue" })
    ) :
    React.createElement(ActionBtn, { icon: "fa-play-circle", label: "Live Trading", sub: "Deploy strategies to MT5/Crypto", onClick: () => setLiveWizardOpen(true), variant: "green" })
    )
    ),
    React.createElement("section", { className: `${DS.card} p-4 flex-shrink-0` },
    React.createElement("h3", { className: `${DS.label} mb-3` }, "Tools"),
    React.createElement("div", { className: "grid grid-cols-2 gap-2" },
    React.createElement("button", { onClick: () => setDashOpen(true),
      className: "flex flex-col items-center gap-1.5 py-3 bg-white/[0.02] hover:bg-white/[0.06] border border-white/[0.06] hover:border-amber-500/30 rounded-xl transition-all group" },
    React.createElement("i", { className: "fas fa-chart-pie text-amber-500/60 text-base group-hover:scale-110 transition-transform" }),
    React.createElement("span", { className: DS.label }, "Dashboard")
    ),
    React.createElement("button", { onClick: () => setMappingOpen(true),
      className: "flex flex-col items-center gap-1.5 py-3 bg-white/[0.02] hover:bg-white/[0.06] border border-white/[0.06] hover:border-blue-500/30 rounded-xl transition-all group" },
    React.createElement("i", { className: "fas fa-network-wired text-blue-400 text-base group-hover:scale-110 transition-transform" }),
    React.createElement("span", { className: DS.label }, "Mapping")
    )
    )
    )
    ),
    React.createElement("main", { className: "flex-1 flex flex-col gap-4 min-h-0 min-w-0" },
    React.createElement("section", { className: `${DS.card} p-4 flex-shrink-0` },
    React.createElement("div", { className: "flex items-center justify-between mb-4" },
    React.createElement("h3", { className: DS.label }, "System Telemetry"),
    hasCuda ?
    React.createElement("span", { className: "text-[8px] px-2 py-1 bg-amber-500/10 text-amber-500/80 border border-amber-500/20 rounded-full uppercase font-bold flex items-center gap-1", title: `Backend: ${gpuBackend}` },
    React.createElement("i", { className: "fas fa-bolt text-[7px]" }), " CUDA Accelerated"
    ) :
    hasGpu ?
    React.createElement("span", { className: "text-[8px] px-2 py-1 bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 rounded-full uppercase font-bold flex items-center gap-1", title: `Backend: ${gpuBackend}` },
    React.createElement("i", { className: "fas fa-microchip text-[7px]" }), " GPU Active"
    ) :
    React.createElement("span", { className: "text-[8px] px-2 py-1 bg-blue-500/10 text-blue-400 border border-blue-500/20 rounded-full uppercase font-bold", title: gpuErrorDetail || "No GPU detected" }, "CPU Engine"
    )
    ),
    React.createElement("div", { className: `grid gap-x-8 gap-y-3 ${hasGpu ? "grid-cols-4" : "grid-cols-2"}` },
    React.createElement(MetricBar, { label: "CPU Load", value: telemetry?.cpu?.usage || 0, color: "bg-zinc-700" }),
    React.createElement(MetricBar, { label: "RAM Usage", value: telemetry?.memory?.percent || 0, color: "bg-amber-600/60" }),
    hasGpu &&
    React.createElement(React.Fragment, null,
    React.createElement(MetricBar, { label: "GPU Load", value: gpuLoad, color: "bg-emerald-600/60" }),
    React.createElement(MetricBar, { label: "VRAM Usage", value: vramPct, color: "bg-amber-500/60" })
    )
    ),
    !hasGpu && gpuInfo &&
    React.createElement("div", { className: "mt-2 px-2 py-1.5 bg-zinc-800/40 border border-white/[0.06] rounded-lg" },
    React.createElement("span", { className: "text-[9px] text-zinc-500 font-mono block truncate", title: gpuInfo },
    React.createElement("i", { className: "fas fa-info-circle mr-1 text-[8px] text-zinc-600" }),
    gpuInfo
    )
    ),
    !hasGpu && gpuErrorDetail &&
    React.createElement("div", { className: "mt-2 px-2 py-1.5 bg-red-900/10 border border-red-500/10 rounded-lg" },
    React.createElement("span", { className: "text-[9px] text-red-400/60 font-mono block truncate", title: gpuErrorDetail },
    React.createElement("i", { className: "fas fa-exclamation-triangle mr-1 text-[8px]" }),
    gpuErrorDetail.length > 80 ? gpuErrorDetail.substring(0, 80) + '...' : gpuErrorDetail
    )
    ),
    React.createElement("div", { className: "mt-3 pt-3 border-t border-white/[0.04] flex items-center justify-between" },
    React.createElement("div", { className: "flex items-center gap-2" },
    React.createElement("i", { className: `fas fa-microchip text-[10px] ${hasGpu ? "text-amber-500/60" : "text-zinc-600"}` }),
    React.createElement("span", { className: "text-[9px] text-zinc-500 font-mono truncate max-w-[160px]", title: deviceName }, deviceName)
    ),
    React.createElement("div", { className: "flex items-center gap-3" },
    gpuTemp > 0 &&
    React.createElement("span", { className: `text-[9px] font-mono ${gpuTemp > 80 ? "text-red-400" : gpuTemp > 65 ? "text-amber-400" : "text-emerald-400/70"}` },
    React.createElement("i", { className: "fas fa-thermometer-half mr-1 text-[8px]" }),
    gpuTemp, "\u00B0C"
    ),
    React.createElement("span", { className: `text-[9px] font-mono font-bold ${status === "active" ? "text-amber-500/80" : status === "training" ? "text-amber-400" : "text-zinc-600"}` },
    status.toUpperCase()
    )
    )
    )
    ),
    React.createElement("section", { className: `${DS.card} flex flex-col flex-1 min-h-0 overflow-hidden` },
    React.createElement("div", { className: "flex items-center justify-between px-4 py-3 border-b border-white/[0.05] flex-shrink-0" },
    React.createElement("span", { className: `${DS.label} flex items-center gap-2 text-amber-500/80` },
    React.createElement("i", { className: "fas fa-terminal" }), " Quantum Terminal"
    ),
    React.createElement("div", { className: "flex items-center gap-2" },
    React.createElement("span", { className: `w-1.5 h-1.5 rounded-full ${status === "active" ? "bg-amber-500 animate-pulse" : "bg-red-500/50"}` }),
    React.createElement("span", { className: `${DS.label} text-[8px]` }, "LIVE STREAM")
    )
    ),
    React.createElement("div", { className: "flex-1 overflow-y-auto custom-scrollbar bg-black/40 p-3 font-mono" },
    logs.length === 0 ?
    React.createElement("div", { className: "h-full flex items-center justify-center" },
    React.createElement("span", { className: "text-[10px] text-white/10 italic tracking-wider" }, "Waiting for command input...")
    ) :
    logs.map((log, i) => React.createElement(LogLine, { key: i, log: log, index: i })),
    status === "training" &&
    React.createElement("div", { className: "pl-2 mt-1" },
    React.createElement("span", { className: "text-amber-500/80 animate-pulse text-sm font-mono" }, "_")
    ),
    React.createElement("div", { ref: logsEndRef })
    )
    )
    )
    ),
    React.createElement(WizardModal, {
      isOpen: trainWizardOpen, onClose: () => setTrainWizardOpen(false),
      title: "Training Wizard", steps: trainSteps, onComplete: runTraining }
    ),
    React.createElement(WizardModal, {
      isOpen: liveWizardOpen, onClose: () => setLiveWizardOpen(false),
      title: "Live Trading Configuration", steps: liveSteps, onComplete: runLive }
    ),
    window.DashboardModals ?
    React.createElement(window.DashboardModals, {
      dashOpen: dashOpen, setDashOpen: setDashOpen,
      liveDashOpen: liveDashOpen, setLiveDashOpen: setLiveDashOpen,
      mappingOpen: mappingOpen, setMappingOpen: setMappingOpen,
      cleanConfirmOpen: cleanConfirmOpen, setCleanConfirmOpen: setCleanConfirmOpen }
    ) :
    null
    ));
};
window.AlgoPanel = AlgoPanel;
