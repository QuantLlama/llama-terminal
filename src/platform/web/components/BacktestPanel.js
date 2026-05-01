const { useState, useEffect, useRef } = React;

const DS = {
  card: "bg-[#0d0d0f]/95 border border-white/[0.06] rounded-2xl",
  label: "text-[9px] font-bold uppercase tracking-[0.15em] text-zinc-500",
  accent: "text-amber-500/80",
  bar: "w-full bg-white/5 rounded-full h-[3px] overflow-hidden"
};

const ActionBtn = ({ icon, label, sub, onClick, variant = "default", disabled = false }) => {
  const variants = {
    default: "border-white/[0.05] hover:border-white/20 hover:bg-white/[0.03] bg-white/[0.01]",
    amber: "border-amber-500/30 hover:border-amber-500/60 bg-amber-500/[0.08] hover:bg-amber-500/[0.12]",
    red: "border-red-500/20 hover:border-red-500/40 bg-red-900/10 hover:bg-red-900/20",
    blue: "border-sky-500/30 hover:border-sky-500/60 bg-sky-900/20 hover:bg-sky-900/30",
    emerald: "border-emerald-500/30 hover:border-emerald-500/60 bg-emerald-900/20 hover:bg-emerald-900/30"
  };
  const iconColors = {
    default: "text-zinc-400 group-hover:text-white",
    amber: "text-amber-400",
    red: "text-red-400",
    blue: "text-sky-400",
    emerald: "text-emerald-400"
  };
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      className={`group w-full flex items-center gap-3 px-4 py-3 border rounded-xl transition-all duration-200 text-left ${disabled ? 'opacity-50 cursor-not-allowed bg-white/[0.02]' : variants[variant]}`}
    >
      <div className={`w-8 h-8 rounded-lg flex items-center justify-center bg-black/40 border border-white/[0.06] flex-shrink-0 transition-colors shadow-inner ${iconColors[variant]}`}>
        <i className={`fas ${icon} text-xs`} />
      </div>
      <div className="overflow-hidden">
        <div className={`text-[11px] font-bold truncate transition-colors ${disabled ? 'text-zinc-600' : 'text-gray-200 group-hover:text-white'}`}>
          {label}
        </div>
        {sub && <div className="text-[9px] text-zinc-500 group-hover:text-zinc-400 truncate transition-colors font-mono mt-0.5">{sub}</div>}
      </div>
    </button>
  );
};

const MenuAccordion = ({ num, title, isActive, onClick, children }) => {
  return (
    <div className="mb-2">
      <button
        onClick={onClick}
        className={`w-full flex items-center justify-between px-4 py-3 rounded-lg border transition-all duration-300 flex-shrink-0 ${
          isActive 
            ? 'bg-amber-500/10 border-amber-500/40 shadow-[0_0_15px_rgba(245,158,11,0.1)]' 
            : 'bg-black/40 border-white/[0.08] hover:border-white/20 hover:bg-white/[0.04]'
        }`}
      >
        <div className="flex items-center gap-3">
          <span className={`text-[11px] font-mono font-bold ${isActive ? 'text-amber-400' : 'text-zinc-500'}`}>
            [{num}]
          </span>
          <span className={`text-[11px] font-bold tracking-wider ${isActive ? 'text-amber-50' : 'text-zinc-400'}`}>
            {title}
          </span>
        </div>
        <i className={`fas fa-chevron-${isActive ? 'up text-amber-500' : 'down text-zinc-600'} text-[10px] transition-transform`} />
      </button>
      <div 
        className={`overflow-hidden transition-all duration-300 ease-in-out ${isActive ? 'opacity-100 max-h-[1000px] mt-2' : 'opacity-0 max-h-0 mt-0 pointer-events-none'}`}
      >
        <div className="p-4 bg-black/50 border border-white/[0.04] rounded-lg shadow-inner">
          {children}
        </div>
      </div>
    </div>
  );
};

const MetricCard = ({ label, value, isPositive, isNeutral }) => (
  <div className="bg-white/[0.03] border border-white/[0.08] p-4 rounded-xl flex flex-col items-center justify-center relative overflow-hidden group hover:border-white/20 transition-all duration-300">
    <div className={`absolute left-0 top-0 bottom-0 w-1 ${isNeutral ? 'bg-zinc-500/50' : isPositive ? 'bg-emerald-500' : 'bg-red-500'}`} />
    <div className="text-[10px] font-black text-zinc-500 uppercase tracking-[0.1em] mb-1.5 text-center">{label}</div>
    <div className={`text-lg font-black font-mono tracking-tight ${isNeutral ? 'text-white' : isPositive ? 'text-emerald-400' : 'text-red-400'}`}>
      {value}
    </div>
  </div>
);

const TradeTable = ({ trades }) => (
  <div className="overflow-x-auto custom-scrollbar">
    <table className="w-full text-left border-collapse">
      <thead className="sticky top-0 bg-[#0d0d0f] z-10">
        <tr className="border-b border-white/10">
          {["#", "Type", "Entry Time", "Entry", "Exit Time", "Exit", "Duration", "PnL ($)"].map(h => (
            <th key={h} className="px-4 py-3 text-[9px] font-bold text-zinc-500 uppercase tracking-widest">{h}</th>
          ))}
        </tr>
      </thead>
      <tbody className="divide-y divide-white/[0.03]">
        {trades.map((t, i) => (
          <tr key={i} className="hover:bg-white/[0.02] transition-colors group">
            <td className="px-4 py-2 text-[10px] font-mono text-zinc-600">{(i + 1).toString().padStart(3, "0")}</td>
            <td className={`px-4 py-2 text-[10px] font-bold ${(t.type === 'BUY' || t.type === 'LONG') ? 'text-emerald-400' : 'text-red-400'}`}>{t.type}</td>
            <td className="px-4 py-2 text-[9px] font-mono text-zinc-500">{t.entry_time || '--'}</td>
            <td className="px-4 py-2 text-[10px] font-mono text-zinc-400">{t.entry_price?.toFixed(2)}</td>
            <td className="px-4 py-2 text-[9px] font-mono text-zinc-500">{t.exit_time || '--'}</td>
            <td className="px-4 py-2 text-[10px] font-mono text-zinc-400">{t.exit_price?.toFixed(2)}</td>
            <td className="px-4 py-2 text-[10px] font-mono text-zinc-500">{t.duration || '--'}</td>
            <td className={`px-4 py-2 text-[10px] font-bold font-mono ${t.pnl >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
              {t.pnl >= 0 ? '+' : ''}{t.pnl?.toFixed(2)}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  </div>
);

const ResultTab = ({ id, label, icon, active, onClick }) => (
  <button
    onClick={() => onClick(id)}
    className={`flex items-center gap-2 px-4 py-2 border-b-2 transition-all duration-200 ${
      active ? 'border-amber-500 text-amber-400 bg-amber-500/5' : 'border-transparent text-zinc-500 hover:text-zinc-300 hover:bg-white/5'
    }`}
  >
    <i className={`fas ${icon} text-[10px]`} />
    <span className="text-[10px] font-bold uppercase tracking-widest">{label}</span>
  </button>
);

const StatusPill = ({ status }) => {
  const map = {
    idle: { bg: "bg-zinc-800/50", dot: "bg-zinc-500", text: "text-zinc-500" },
    running: { bg: "bg-blue-900/20", dot: "bg-blue-400/80 animate-pulse", text: "text-blue-400/80" },
    optimizing: { bg: "bg-amber-900/20", dot: "bg-amber-400/80 animate-pulse", text: "text-amber-400/80" },
    validating: { bg: "bg-purple-900/20", dot: "bg-purple-400/80 animate-pulse", text: "text-purple-400/80" },
    done: { bg: "bg-emerald-900/20", dot: "bg-emerald-400/80", text: "text-emerald-400/80" },
    error: { bg: "bg-red-900/20", dot: "bg-red-400/80", text: "text-red-400/80" }
  };
  const s = map[status] || map.idle;
  return (
    <div className={`flex items-center gap-2 px-3 py-1.5 rounded-full ${s.bg} border border-white/[0.04] backdrop-blur-sm`}>
      <span className={`w-1.5 h-1.5 rounded-full ${s.dot}`} />
      <span className={`text-[9px] font-bold font-mono uppercase tracking-widest ${s.text}`}>
        {status}
      </span>
    </div>
  );
};

const LogLine = ({ log, index }) => {
  const isError = log.includes("Error") || log.includes("Failed") || log.includes("ERROR");
  const isStart = log.includes("Starting") || log.includes("Loaded") || log.includes("Validating") || log.includes("Sending");
  const isSuccess = log.includes("Completed") || log.includes("success") || log.includes("OK") || log.includes("PASSED");
  const color = isError ? "text-red-400" : isSuccess ? "text-emerald-400" : isStart ? "text-sky-400" : "text-gray-400";
  return (
    <div className="group flex items-start gap-3 py-[3px] px-2 hover:bg-white/[0.025] rounded transition-colors">
      <span className="text-[9px] font-mono text-white/10 select-none pt-px flex-shrink-0 w-6 text-right">
        {(index + 1).toString().padStart(2, "0")}
      </span>
      <span className={`text-[10px] font-mono leading-relaxed ${color}`}>{log}</span>
    </div>
  );
};

const BacktestPanel = ({ activeSymbol, systemStatus }) => {
  const [status, setStatus] = useState("idle");
  const [logs, setLogs] = useState(["[SYSTEM] Backtest Engine Initialized"]);
  const logsEndRef = useRef(null);
  const fileInputRef = useRef(null);

  // Persistence Loaders
  const [activeMenuStep, setActiveMenuStep] = useState(() => Number(localStorage.getItem("bt_active_step")) || 1);
  const [strategies, setStrategies] = useState([]);
  const [selectedStrategy, setSelectedStrategy] = useState(() => localStorage.getItem("bt_strategy") || "");
  const [strategyParams, setStrategyParams] = useState(() => JSON.parse(localStorage.getItem("bt_params") || "{}"));
  const [optimizerParams, setOptimizerParams] = useState(() => JSON.parse(localStorage.getItem("bt_opt_params") || '{"population_size": 20, "generations": 5}'));
  
  const [dataSource, setDataSource] = useState(() => localStorage.getItem("bt_datasource") || "yahoo");
  const [symbol, setSymbol] = useState(() => localStorage.getItem("bt_symbol") || activeSymbol || "AAPL");
  const [timeframe, setTimeframe] = useState(() => localStorage.getItem("bt_timeframe") || "1d");
  const [initialCapital, setInitialCapital] = useState(() => Number(localStorage.getItem("bt_capital")) || 10000);
  
  const [results, setResults] = useState(null);
  const [optimizationProgress, setOptimizationProgress] = useState(0);
  const [activeResultTab, setActiveResultTab] = useState("equity"); 
  
  // Execution Controls
  const [maxTradesPerDay, setMaxTradesPerDay] = useState(() => Number(localStorage.getItem("bt_max_trades")) || 0);
  const [startHour, setStartHour] = useState(() => Number(localStorage.getItem("bt_start_hour")) || 0);
  const [endHour, setEndHour] = useState(() => Number(localStorage.getItem("bt_end_hour")) || 23);
  const [fromDate, setFromDate] = useState(() => localStorage.getItem("bt_from_date") || "");
  const [toDate, setToDate] = useState(() => localStorage.getItem("bt_to_date") || "");
  const [ignoreFilters, setIgnoreFilters] = useState(() => localStorage.getItem("bt_ignore_filters") === "true");
  const [slOverride, setSlOverride] = useState(() => Number(localStorage.getItem("bt_sl_override")) || 0);
  const [tpOverride, setTpOverride] = useState(() => Number(localStorage.getItem("bt_tp_override")) || 0);

  const sidebarRef = useRef(null);
  const [sidebarWidth, setSidebarWidth] = useState(() => {
    return localStorage.getItem("backtest_menu_width") || "25%";
  });

  // Persistence Effect
  useEffect(() => {
    localStorage.setItem("bt_active_step", activeMenuStep);
    localStorage.setItem("bt_symbol", symbol);
    localStorage.setItem("bt_timeframe", timeframe);
    localStorage.setItem("bt_capital", initialCapital);
    localStorage.setItem("bt_strategy", selectedStrategy);
    localStorage.setItem("bt_params", JSON.stringify(strategyParams));
    localStorage.setItem("bt_opt_params", JSON.stringify(optimizerParams));
    localStorage.setItem("bt_datasource", dataSource);
    localStorage.setItem("bt_max_trades", maxTradesPerDay);
    localStorage.setItem("bt_start_hour", startHour);
    localStorage.setItem("bt_end_hour", endHour);
    localStorage.setItem("bt_from_date", fromDate);
    localStorage.setItem("bt_to_date", toDate);
    localStorage.setItem("bt_ignore_filters", ignoreFilters);
    localStorage.setItem("bt_sl_override", slOverride);
    localStorage.setItem("bt_tp_override", tpOverride);
  }, [activeMenuStep, symbol, timeframe, initialCapital, selectedStrategy, strategyParams, optimizerParams, dataSource, maxTradesPerDay, startHour, endHour, fromDate, toDate, ignoreFilters, slOverride, tpOverride]);

  // Server Sync on Mount
  useEffect(() => {
    // 1. Check loaded data
    fetch("/api/backtest/data/info")
      .then(r => r.json())
      .then(data => {
        if (data.valid) {
          setSymbol(data.symbol || symbol);
          if (data.from_date) setFromDate(data.from_date.split(' ')[0]);
          if (data.to_date) setToDate(data.to_date.split(' ')[0]);
          setLogs(prev => [...prev, `[SYSTEM] RESTORED: Working with ${data.symbol || 'loaded data'} (${data.total_rows} rows)`]);
          if (activeMenuStep < 4) setActiveMenuStep(4);
        }
      });
    
    // 2. Fetch recent logs
    fetch("/api/backtest/logs?last=50")
      .then(r => r.json())
      .then(l => setLogs(l));

    // 3. Fetch latest results if any
    fetch("/api/backtest/results/latest")
      .then(r => r.json())
      .then(data => {
        if (data.backtest_results) {
          setResults(data.backtest_results);
          setLogs(prev => [...prev, `[SYSTEM] RESTORED: Previous results loaded.`]);
        }
      });

    // 4. Check optimizer status
    fetch("/api/backtest/optimize/status")
      .then(r => r.json())
      .then(job => {
        if (job.status === "running") {
          setStatus("optimizing");
          setOptimizationProgress(job.progress || 0);
          setLogs(prev => [...prev, `[SYSTEM] RESTORED: Resuming optimization polling...`]);
          startPollingOptimizer();
        }
      });
  }, []); // Run once on mount

  useEffect(() => {
    if (!sidebarRef.current) return;
    const observer = new ResizeObserver(entries => {
      for (let entry of entries) {
        if (entry.contentRect.width > 0) {
          const newWidth = `${entry.contentRect.width}px`;
          localStorage.setItem("backtest_menu_width", newWidth);
        }
      }
    });
    observer.observe(sidebarRef.current);
    return () => observer.disconnect();
  }, []);

  // Load Strategies matching the API
  useEffect(() => {
    fetch("/api/backtest/strategies")
      .then(res => res.json())
      .then(data => {
        if (data.strategies) {
          setStrategies(data.strategies);
          if (data.strategies.length > 0) {
            setSelectedStrategy(data.strategies[0].id);
          }
        }
      })
      .catch(err => setLogs(prev => [...prev, `[ERROR] Failed to fetch strategies: ${err.message}`]));
  }, []);

  // Update params based on selected strategy
  useEffect(() => {
    const strat = strategies.find(s => s.id === selectedStrategy);
    if (strat && strat.parameters) {
      const defaultParams = {};
      Object.entries(strat.parameters).forEach(([k, v]) => {
        defaultParams[k] = v.value;
      });
      setStrategyParams(defaultParams);
    }
  }, [selectedStrategy, strategies]);

  useEffect(() => {
    if (activeSymbol) setSymbol(activeSymbol);
  }, [activeSymbol]);

  useEffect(() => {
    if (logsEndRef.current) logsEndRef.current.scrollIntoView({ behavior: "smooth" });
  }, [logs]);

  // Handle Backend Execution
  const handleLoadData = async (source) => {
    setDataSource(source);
    setLogs(prev => [...prev, `[DATA] Sending request to Data Engine ${source} for ${symbol}...`]);
    try {
      const res = await fetch("/api/backtest/data/load", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ source, symbol: symbol.trim(), timeframe: timeframe || "1d" })
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail);
      const count = data.records || (data.info && data.info.rows) || 0;
      setLogs(prev => [...prev, `[DATA] Data loaded successfully: ${count} records detected.`]);
      setActiveMenuStep(4);
    } catch(e) {
      setLogs(prev => [...prev, `[ERROR] Loading data failed: ${e.message}`]);
    }
  };

  const handleFileUpload = (e) => {
    const file = e.target.files?.[0];
    if (!file) return;

    setLogs(prev => [...prev, `[DATA] Reading local file: ${file.name}...`]);
    setDataSource("csv");

    const reader = new FileReader();
    reader.onload = async (evt) => {
      try {
        const text = evt.target.result;
        setLogs(prev => [...prev, `[DATA] Uploading ${file.name} to engine...`]);
        const res = await fetch("/api/backtest/data/upload_raw_csv?filename=" + encodeURIComponent(file.name), {
          method: "POST",
          headers: { "Content-Type": "text/plain" },
          body: text
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail);
        setLogs(prev => [...prev, `[DATA] CSV loaded successfully: ${data.records} rows detected.`]);
        setActiveMenuStep(4);
      } catch (err) {
        setLogs(prev => [...prev, `[ERROR] CSV upload failed: ${err.message}`]);
      }
      
      // Reset input so the same file could be selected again if needed
      if(fileInputRef.current) fileInputRef.current.value = "";
    };
    reader.readAsText(file);
  };

  const handleStartOptimizer = async () => {
    setStatus("optimizing");
    setOptimizationProgress(0);
    setLogs(prev => [...prev, `[SYSTEM] Initializing Genetic Engine...`]);
    try {
      const res = await fetch("/api/backtest/optimize", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          strategy_name: selectedStrategy,
          population_size: optimizerParams.population_size,
          generations: optimizerParams.generations,
          initial_balance: initialCapital,
          max_trades_per_day: maxTradesPerDay > 0 ? maxTradesPerDay : null,
          start_hour: startHour,
          end_hour: endHour,
          from_date: fromDate,
          to_date: toDate,
          ignore_filters: ignoreFilters,
          sl_override: slOverride > 0 ? slOverride : null,
          tp_override: tpOverride > 0 ? tpOverride : null
        })
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail);
      setLogs(prev => [...prev, `[SYSTEM] ${data.message}`]);
      
      // Start polling
      const poll = setInterval(async () => {
        const sRes = await fetch("/api/backtest/optimize/status");
        const status = await sRes.json();
        if (status.status === "completed") {
          clearInterval(poll);
          setLogs(prev => [
            ...prev, 
            `[SYSTEM] Optimization Complete!`,
            `  - Best Fitness: ${status.best_fitness}`,
            `  - Recommended Params: ${JSON.stringify(status.best_params)}`
          ]);
          // Apply best params automatically
          setStrategyParams(prev => ({...prev, ...status.best_params}));
          setStatus("idle");
          setActiveMenuStep(7);
        } else if (status.status === "error") {
          clearInterval(poll);
          setLogs(prev => [...prev, `[ERROR] Optimizer failed: ${status.error}`]);
          setStatus("error");
        } else if (status.status === "running") {
          const lRes = await fetch("/api/backtest/logs?last=100");
          const updatedLogs = await lRes.json();
          setLogs(updatedLogs);
          if (status.progress) setOptimizationProgress(status.progress);
        }
      }, 2000);

    } catch(e) {
      setLogs(prev => [...prev, `[ERROR] Optimizer start failed: ${e.message}`]);
      setStatus("error");
    }
  };

  const startPollingOptimizer = () => {
    const poll = setInterval(async () => {
      try {
        const sRes = await fetch("/api/backtest/optimize/status");
        if (!sRes.ok) return;
        const status = await sRes.json();
        
        if (status.status === "completed") {
          clearInterval(poll);
          setLogs(prev => [
            ...prev, 
            `[SYSTEM] Optimization Complete!`,
            `  - Best Fitness: ${status.best_fitness}`,
            `  - Recommended Params: ${JSON.stringify(status.best_params)}`
          ]);
          setStrategyParams(prev => ({...prev, ...status.best_params}));
          setStatus("idle");
          setActiveMenuStep(7);
        } else if (status.status === "error" || status.status === "cancelled") {
          clearInterval(poll);
          setLogs(prev => [...prev, `[${status.status === 'error' ? 'ERROR' : 'SYSTEM'}] Optimizer ${status.status}: ${status.error || 'Stopped by user'}`]);
          setStatus("idle");
        } else if (status.status === "running") {
          const lRes = await fetch("/api/backtest/logs?last=100");
          if (lRes.ok) {
            const updatedLogs = await lRes.json();
            setLogs(updatedLogs);
          }
          if (status.progress) setOptimizationProgress(status.progress);
        }
      } catch (e) {
        console.error("Polling error:", e);
      }
    }, 2000);
    return () => clearInterval(poll);
  };

  const handleStopOptimizer = async () => {
    try {
      setLogs(prev => [...prev, `[SYSTEM] Requesting cancellation...`]);
      const res = await fetch("/api/backtest/optimize/stop", { method: "POST" });
      const data = await res.json();
      setLogs(prev => [...prev, `[SYSTEM] ${data.message}`]);
      setStatus("idle");
    } catch(e) {
      setLogs(prev => [...prev, `[ERROR] Stop request failed: ${e.message}`]);
    }
  };

  const handleValidateData = async () => {
    setStatus("validating");
    setLogs(prev => [...prev, `[VALIDATOR] Starting data quality scan for ${symbol}...`]);
    try {
      const res = await fetch("/api/backtest/data/validate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ source: dataSource, symbol })
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail);
      
      setLogs(prev => [
        ...prev, 
        `[VALIDATOR] Inspection Completed.`,
        `  - Errors found: ${data.issues ? data.issues.length : 0}`,
        `  - Warnings: ${data.warnings ? data.warnings.length : 0}`,
        `  - Global Status: ${data.valid ? 'DATA READY (OK)' : 'NOT READY (FAILED)'}`
      ]);
      setStatus("idle");
      setActiveMenuStep(5);
    } catch(e) {
      setStatus("error");
      setLogs(prev => [...prev, `[ERROR] Validation failed: ${e.message}`]);
    }
  };

  const handleRunBacktest = async () => {
    setStatus("running");
    setResults(null);
    setLogs(prev => [...prev, `[BACKTEST] Starting data partition for strategy ${selectedStrategy}...`]);
    try {
      const res = await fetch("/api/backtest/run", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          strategy_name: selectedStrategy,
          strategy_params: strategyParams,
          initial_balance: initialCapital,
          max_trades_per_day: maxTradesPerDay > 0 ? maxTradesPerDay : null,
          start_hour: startHour,
          end_hour: endHour,
          from_date: fromDate,
          to_date: toDate,
          ignore_filters: ignoreFilters,
          sl_override: slOverride > 0 ? slOverride : null,
          tp_override: tpOverride > 0 ? tpOverride : null
        })
      });
      const runJson = await res.json();
      if (!res.ok) throw new Error(runJson.detail);

      setResults(runJson);
      setStatus("done");
      const tradeCount = runJson?.metrics?.total_trades || 0;
      setLogs(prev => [...prev, `[BACKTEST] Analysis Generated. Trades executed: ${tradeCount}`]);
      setActiveResultTab("equity");
      setActiveMenuStep(888); // Switch to View Results
    } catch(e) {
      setStatus("error");
      setLogs(prev => [...prev, `[ERROR] Execution failed: ${e.message}`]);
    }
  };

  const drawChart = (canvasId, dataPoints, timestamps = [], color = '#f59e0b') => {
    const canvas = document.getElementById(canvasId);
    if (!canvas || !dataPoints || dataPoints.length === 0) return;
    
    const rect = canvas.getBoundingClientRect();
    canvas.width = rect.width * window.devicePixelRatio;
    canvas.height = rect.height * window.devicePixelRatio;
    
    const ctx = canvas.getContext('2d');
    ctx.scale(window.devicePixelRatio, window.devicePixelRatio);
    const width = rect.width;
    const height = rect.height;
    ctx.clearRect(0, 0, width, height);

    const marginLeft = 40;
    const marginBottom = 25;
    const chartWidth = width - marginLeft - 10;
    const chartHeight = height - marginBottom - 10;

    const min = Math.min(...dataPoints);
    const max = Math.max(...dataPoints);
    const range = Math.max(0.01, max - min);

    const getY = (val) => chartHeight - ((val - min) / range) * chartHeight + 10;
    const getX = (idx) => marginLeft + (idx / (dataPoints.length - 1)) * chartWidth;

    // Grid Lines (Horizontal)
    ctx.strokeStyle = 'rgba(255,255,255,0.05)';
    ctx.lineWidth = 1;
    ctx.font = '8px monospace';
    ctx.fillStyle = 'rgba(255,255,255,0.3)';
    ctx.textAlign = 'right';
    [0, 0.25, 0.5, 0.75, 1].forEach(p => {
      const y = getY(min + p * range);
      ctx.beginPath();
      ctx.moveTo(marginLeft, y);
      ctx.lineTo(width - 10, y);
      ctx.stroke();
      ctx.fillText((min + p * range).toFixed(2), marginLeft - 5, y + 3);
    });

    // X Axis Labels (Dates)
    if (timestamps && timestamps.length > 0) {
      ctx.textAlign = 'center';
      const labelCount = Math.min(6, timestamps.length);
      const step = Math.floor(dataPoints.length / (labelCount - 1));
      
      for (let i = 0; i < labelCount; i++) {
        const idx = Math.min(i * step, dataPoints.length - 1);
        const x = getX(idx);
        const dateStr = (timestamps[idx] || '').split(' ')[0]; // YYYY-MM-DD
        
        ctx.beginPath();
        ctx.moveTo(x, 10);
        ctx.lineTo(x, chartHeight + 10);
        ctx.stroke();
        
        if (dateStr) {
          ctx.fillText(dateStr, x, height - 5);
        }
      }
    }

    // Fill Gradient
    ctx.beginPath();
    ctx.moveTo(getX(0), chartHeight + 10);
    ctx.lineTo(getX(0), getY(dataPoints[0]));
    for (let i = 1; i < dataPoints.length; i++) {
      ctx.lineTo(getX(i), getY(dataPoints[i]));
    }
    ctx.lineTo(getX(dataPoints.length - 1), chartHeight + 10);
    ctx.closePath();
    const grad = ctx.createLinearGradient(0, 0, 0, height);
    grad.addColorStop(0, `${color}22`);
    grad.addColorStop(1, `${color}00`);
    ctx.fillStyle = grad;
    ctx.fill();

    // Main Line
    ctx.beginPath();
    ctx.moveTo(getX(0), getY(dataPoints[0]));
    for (let i = 1; i < dataPoints.length; i++) {
        ctx.lineTo(getX(i), getY(dataPoints[i]));
    }
    ctx.strokeStyle = color;
    ctx.lineWidth = 2;
    ctx.lineJoin = 'round';
    ctx.stroke();
  };

  useEffect(() => {
    if (!results) return;
    const ts = results.equity_timestamps || [];
    if (activeResultTab === 'equity' && results.equity_curve) {
      setTimeout(() => drawChart('equityCanvas', results.equity_curve, ts, '#f59e0b'), 50);
    } else if (activeResultTab === 'drawdown' && results.drawdown) {
      setTimeout(() => drawChart('drawdownCanvas', results.drawdown, ts, '#f43f5e'), 50);
    }
  }, [results, activeResultTab]);

  return (
    <div className="w-full h-full flex flex-col bg-[#050505] text-gray-300 font-sans p-2 gap-2"
         style={{ backgroundImage: 'radial-gradient(circle at 50% 0%, #1a1500 0%, transparent 70%)' }}>
      
      {/* Top Bar */}
      <div className={`flex items-center justify-between px-6 py-4 flex-shrink-0 ${DS.card}`}>
        <div className="flex items-center gap-4">
          <img src="/images/logobacktest.png" alt="Backtest Logo" className="w-10 h-10 object-contain drop-shadow-lg" onError={(e) => { e.target.style.display='none'; }}/>
          <div>
            <h1 className="text-sm font-black text-white tracking-widest uppercase flex items-center gap-2">
              ALGORITHMIC BACKTESTING
            </h1>
            <div className="text-[10px] text-zinc-500 font-mono tracking-wider mt-0.5">
              MAIN MENU - OPTIMAL EXECUTION FLOW
            </div>
          </div>
        </div>
        <StatusPill status={status} />
      </div>

      <div className="flex-1 min-h-0 flex gap-2 overflow-hidden px-2 pb-2">
        {/* LEFT PANEL: The Menu */}
        <div 
          ref={sidebarRef}
          style={{ width: sidebarWidth.includes('%') ? sidebarWidth : sidebarWidth }}
          className={`min-w-[320px] max-w-[650px] resize-x overflow-hidden flex flex-col ${DS.card}`}
        >
          <div className="flex-1 overflow-y-auto p-4 custom-scrollbar">
            
            <MenuAccordion num={1} title="SELECT ASSET / SYMBOL" isActive={activeMenuStep === 1} onClick={() => setActiveMenuStep(curr => curr === 1 ? null : 1)}>
              <div className="space-y-4">
                <div>
                  <label className="block text-[10px] font-bold text-zinc-500 mb-2 font-mono">TICKER SYMBOL</label>
                  <input type="text" value={symbol} onChange={e => setSymbol(e.target.value.toUpperCase())}
                         className="w-full bg-black border border-white/10 rounded-lg px-3 py-2 text-xs text-white font-mono focus:border-amber-500/50 outline-none" />
                </div>
                <div>
                  <label className="block text-[10px] font-bold text-zinc-500 mb-2 font-mono">TIMEFRAME</label>
                  <select value={timeframe} onChange={e => setTimeframe(e.target.value)}
                          className="w-full bg-black border border-white/10 rounded-lg px-3 py-2 text-xs text-white font-mono focus:border-amber-500/50 outline-none">
                    <option value="1m">1 Minute</option>
                    <option value="5m">5 Minutes</option>
                    <option value="15m">15 Minutes</option>
                    <option value="1h">1 Hour</option>
                    <option value="1d">1 Day</option>
                  </select>
                </div>
                <div className="grid grid-cols-2 gap-2">
                  <div>
                    <label className="block text-[10px] font-bold text-zinc-500 mb-2 font-mono uppercase">From Date</label>
                    <input type="date" value={fromDate} onChange={e => setFromDate(e.target.value)}
                           className="w-full bg-black border border-white/10 rounded-lg px-2 py-1.5 text-[10px] text-white font-mono focus:border-amber-500/50 outline-none" />
                  </div>
                  <div>
                    <label className="block text-[10px] font-bold text-zinc-500 mb-2 font-mono uppercase">To Date</label>
                    <input type="date" value={toDate} onChange={e => setToDate(e.target.value)}
                           className="w-full bg-black border border-white/10 rounded-lg px-2 py-1.5 text-[10px] text-white font-mono focus:border-amber-500/50 outline-none" />
                  </div>
                </div>
                <ActionBtn icon="fa-check" label="Confirm Asset & Range" variant="amber" onClick={() => setActiveMenuStep(2)} />
              </div>
            </MenuAccordion>

            <MenuAccordion num={2} title="FETCH PLATFORM DATA" isActive={activeMenuStep === 2} onClick={() => setActiveMenuStep(curr => curr === 2 ? null : 2)}>
              <div className="space-y-3">
                <div className="text-[10px] text-zinc-400 font-mono mb-2">Connect to local terminal to extract tick/M1 data.</div>
                <ActionBtn icon="fa-download" label="Extract Data from MT5" variant="blue" onClick={() => handleLoadData('mt5')} />
                <ActionBtn icon="fa-download" label="Extract Data from NinjaTrader" disabled={true} sub="Coming soon" />
              </div>
            </MenuAccordion>

            <MenuAccordion num={3} title="LOAD CSV / YAHOO DATA" isActive={activeMenuStep === 3} onClick={() => setActiveMenuStep(curr => curr === 3 ? null : 3)}>
               <div className="space-y-3">
                <div className="text-[10px] text-zinc-400 font-mono mb-2">External data sources and custom CSVs.</div>
                <ActionBtn icon="fa-cloud-download-alt" label="Download Yahoo Finance" variant="blue" onClick={() => handleLoadData('yahoo')} />
                
                {/* Hidden File Input */}
                <input 
                  type="file" 
                  accept=".csv" 
                  ref={fileInputRef} 
                  onChange={handleFileUpload} 
                  className="hidden" 
                />
                <ActionBtn icon="fa-file-csv" label="Load Local File (CSV)" onClick={() => fileInputRef.current?.click()} />
              </div>
            </MenuAccordion>

            <MenuAccordion num={4} title="VALIDATE DATA" isActive={activeMenuStep === 4} onClick={() => setActiveMenuStep(curr => curr === 4 ? null : 4)}>
               <div className="space-y-3">
                <div className="text-[10px] text-zinc-400 font-mono mb-2">Inspect gaps, normalize OHLCV candles & check timestamps.</div>
                <ActionBtn icon="fa-shield-alt" label="Execute Normalization & Validation" variant="emerald" onClick={handleValidateData} />
              </div>
            </MenuAccordion>

            <MenuAccordion num={5} title="STRATEGY CONFIGURATION" isActive={activeMenuStep === 5} onClick={() => setActiveMenuStep(curr => curr === 5 ? null : 5)}>
              <div className="space-y-4">
                <div>
                  <label className="block text-[10px] font-bold text-amber-500 mb-2 font-mono uppercase">Select Algorithmic Engine</label>
                  <select value={selectedStrategy} onChange={e => setSelectedStrategy(e.target.value)}
                          className="w-full bg-black border border-amber-500/30 rounded-lg px-3 py-2 text-xs text-amber-400 font-bold focus:border-amber-500 outline-none">
                    {strategies.map(s => <option key={s.id} value={s.id}>{s.name || s.id}</option>)}
                  </select>
                </div>
                <div className="pt-2 border-t border-white/5 space-y-3">
                  <span className="text-[9px] font-bold text-zinc-500 uppercase tracking-widest font-mono">Internal Parameters</span>
                  {Object.entries(strategyParams).map(([k, v]) => (
                    <div className="flex items-center justify-between group" key={k}>
                      <span className="text-[10px] font-mono text-zinc-400 group-hover:text-amber-400 transition-colors uppercase">{k}</span>
                      <input type={typeof v === 'number' ? 'number' : 'text'} value={v}
                             onChange={e => setStrategyParams(p => ({...p, [k]: parseFloat(e.target.value) || e.target.value}))}
                             className="w-20 bg-black/60 border border-white/10 rounded text-right px-2 py-1 text-[10px] text-white font-mono focus:border-amber-500/50 outline-none" />
                    </div>
                  ))}
                </div>
                <div>
                  <label className="block text-[10px] font-bold text-zinc-500 mb-2 font-mono pt-4 border-t border-white/5">Initial Capital / Starting Balance</label>
                  <input type="number" value={initialCapital} onChange={e => setInitialCapital(Number(e.target.value))}
                         className="w-full bg-black border border-white/10 rounded-lg px-3 py-2 text-xs text-emerald-400 font-mono font-bold focus:border-emerald-500/50 outline-none" />
                </div>
                <ActionBtn icon="fa-check" label="Save & Continue" variant="amber" onClick={() => setActiveMenuStep(6)} />
              </div>
            </MenuAccordion>

            <MenuAccordion num={6} title="OPTIMIZE PARAMETERS" isActive={activeMenuStep === 6} onClick={() => setActiveMenuStep(curr => curr === 6 ? null : 6)}>
               <div className="space-y-4">
                <div className="text-[10px] text-zinc-400 font-mono italic">Genetic engine maximizing Sharpe/PnL parameters.</div>
                <div className="grid grid-cols-2 gap-2">
                  <div>
                    <span className="text-[9px] font-mono text-zinc-500 uppercase">Population</span>
                    <input type="number" value={optimizerParams.population_size} onChange={e => setOptimizerParams(p=>({...p, population_size: Number(e.target.value)}))}
                           className="w-full bg-black/60 border border-white/10 rounded px-2 py-1.5 text-[10px] text-white font-mono mt-1" />
                  </div>
                  <div>
                    <span className="text-[9px] font-mono text-zinc-500 uppercase">Generations</span>
                    <input type="number" value={optimizerParams.generations} onChange={e => setOptimizerParams(p=>({...p, generations: Number(e.target.value)}))}
                           className="w-full bg-black/60 border border-white/10 rounded px-2 py-1.5 text-[10px] text-white font-mono mt-1" />
                  </div>
                </div>
                <div className="flex gap-2">
                  <ActionBtn icon="fa-dna" label="Start Genetic Optimizer" variant="amber" onClick={handleStartOptimizer} disabled={status === "optimizing"} />
                  {status === "optimizing" && <ActionBtn icon="fa-stop" label="Stop" variant="red" onClick={handleStopOptimizer} />}
                </div>
                {status === "optimizing" && (
                  <div className="mt-2 space-y-1">
                    <div className="flex justify-between items-center text-[9px] font-mono text-amber-500/80 uppercase">
                       <span className="animate-pulse">Optimizing...</span>
                       <span>{optimizationProgress}%</span>
                    </div>
                    <div className={DS.bar}>
                      <div className="h-full bg-amber-500 transition-all duration-500" style={{ width: `${optimizationProgress}%` }} />
                    </div>
                  </div>
                )}
                <ActionBtn icon="fa-forward" label="Skip Optimization" onClick={() => setActiveMenuStep(7)} />
              </div>
            </MenuAccordion>

            <MenuAccordion num={7} title="EXECUTION CONSTRAINTS" isActive={activeMenuStep === 7} onClick={() => setActiveMenuStep(curr => curr === 7 ? null : 7)}>
               <div className="space-y-4">
                <div className="text-[10px] text-zinc-400 font-mono mb-2">Limit trade frequency and define allowed trading sessions.</div>
                
                <div>
                  <div className="flex justify-between items-center mb-1.5">
                    <label className={DS.label}>Max Trades Per Day</label>
                    <span className="text-[10px] font-mono text-amber-500 font-bold">{maxTradesPerDay === 0 ? 'UNLIMITED' : maxTradesPerDay}</span>
                  </div>
                  <input type="range" min="0" max="50" step="1" value={maxTradesPerDay} onChange={e => setMaxTradesPerDay(Number(e.target.value))}
                         className="w-full accent-amber-500 h-1 bg-white/10 rounded-lg appearance-none cursor-pointer" />
                </div>

                <div className="grid grid-cols-2 gap-4 pt-2">
                  <div>
                    <label className={DS.label}>Start Hour (UTC)</label>
                    <select value={startHour} onChange={e => setStartHour(Number(e.target.value))}
                            className="w-full bg-black border border-white/10 rounded-lg px-2 py-1.5 text-[10px] text-white font-mono mt-1">
                      {Array.from({length: 24}).map((_, i) => <option key={i} value={i}>{i.toString().padStart(2, '0')}:00</option>)}
                    </select>
                  </div>
                  <div>
                    <label className={DS.label}>End Hour (UTC)</label>
                    <select value={endHour} onChange={e => setEndHour(Number(e.target.value))}
                            className="w-full bg-black border border-white/10 rounded-lg px-2 py-1.5 text-[10px] text-white font-mono mt-1">
                      {Array.from({length: 24}).map((_, i) => <option key={i} value={i}>{i.toString().padStart(2, '0')}:00</option>)}
                    </select>
                  </div>
                </div>

                <div className="pt-4 border-t border-white/5 mt-2">
                  <div className="flex items-center justify-between group cursor-pointer" onClick={() => setIgnoreFilters(!ignoreFilters)}>
                    <div className="flex flex-col">
                      <span className="text-[10px] font-bold text-zinc-300 group-hover:text-amber-400 transition-colors uppercase tracking-widest">Ignore Session & Trade Limits</span>
                      <span className="text-[8px] text-zinc-500 font-mono mt-0.5">Bypass time and trade limits during simulation</span>
                    </div>
                    <div className={`w-8 h-4 rounded-full transition-all duration-300 relative ${ignoreFilters ? 'bg-amber-500/80 shadow-[0_0_8px_rgba(245,158,11,0.4)]' : 'bg-zinc-800'}`}>
                      <div className={`absolute top-0.5 w-3 h-3 rounded-full bg-white transition-all duration-300 ${ignoreFilters ? 'left-4.5' : 'left-0.5'}`}
                           style={{ left: ignoreFilters ? '18px' : '2px' }} />
                    </div>
                  </div>
                </div>

                {/* SL/TP Global Override */}
                <div className="pt-4 border-t border-white/5 mt-2">
                  <span className="block text-[10px] font-bold text-emerald-500 mb-2 font-mono uppercase">Global Exit Override (Ticks)</span>
                  <div className="grid grid-cols-2 gap-3">
                    <div>
                      <label className="block text-[9px] font-bold text-zinc-500 mb-1 font-mono uppercase">Global SL</label>
                      <input type="number" min="0" value={slOverride} onChange={e => setSlOverride(Number(e.target.value))}
                             className="w-full bg-black border border-white/10 rounded px-2 py-1.5 text-xs text-emerald-400 font-mono focus:border-emerald-500/50 outline-none" />
                      <span className="text-[8px] text-zinc-600 font-mono italic block mt-1">0 = Strategy Default</span>
                    </div>
                    <div>
                      <label className="block text-[9px] font-bold text-zinc-500 mb-1 font-mono uppercase">Global TP</label>
                      <input type="number" min="0" value={tpOverride} onChange={e => setTpOverride(Number(e.target.value))}
                             className="w-full bg-black border border-white/10 rounded px-2 py-1.5 text-xs text-emerald-400 font-mono focus:border-emerald-500/50 outline-none" />
                      <span className="text-[8px] text-zinc-600 font-mono italic block mt-1">0 = Strategy Default</span>
                    </div>
                  </div>
                </div>

                <div className="bg-amber-500/5 border border-amber-500/10 p-2 rounded-lg text-[9px] text-zinc-500 font-mono leading-relaxed mt-2">
                  <i className="fas fa-info-circle mr-1 text-amber-500/50" />
                  {ignoreFilters 
                    ? "OPTIMIZATION MODE: All restrictive filters are DISABLED. Strategy will explore every opportunity."
                    : `Trades generated outside ${startHour.toString().padStart(2, '0')}:00 and ${endHour.toString().padStart(2, '0')}:00 will be automatically ignored.`
                  }
                </div>

                <ActionBtn icon="fa-check-double" label="Apply Constraints" variant="amber" onClick={() => setActiveMenuStep(8)} />
              </div>
            </MenuAccordion>

            <MenuAccordion num={8} title="EXECUTE BACKTESTING" isActive={activeMenuStep === 8} onClick={() => setActiveMenuStep(curr => curr === 8 ? null : 8)}>
               <div className="space-y-4 pt-2">
                <ActionBtn icon="fa-play" label={`Run Strategy: ${selectedStrategy || 'Selected'}`} variant="amber" onClick={handleRunBacktest} />
              </div>
            </MenuAccordion>

            <MenuAccordion num="..." title="VIEW RESULTS" isActive={activeMenuStep === 888} onClick={() => setActiveMenuStep(curr => curr === 888 ? null : 888)}>
               <div className="text-[10px] text-zinc-400 font-mono text-center py-2 italic font-bold">
                Simulation complete. Refer to the dashboard panel.
               </div>
            </MenuAccordion>

          </div>
        </div>

        {/* CENTER PANEL: Results & Charts */}
        <div className={`flex-1 min-w-0 flex flex-col overflow-hidden gap-2`}>
          
          <div className={`flex flex-col h-[75%] min-h-[350px] max-h-[90%] resize-y overflow-hidden ${DS.card} p-0`}>
            {results ? (
              <div className="flex flex-col h-full">
                 {/* Results Header */}
                 <div className="flex justify-between items-center px-6 py-4 border-b border-white/10 bg-white/[0.02]">
                   <div>
                     <h2 className="text-sm font-black tracking-[0.2em] text-amber-500 uppercase">Backtest Analysis Report</h2>
                     <div className="text-[9px] font-mono text-zinc-500 mt-0.5">{symbol} • {timeframe} • Strategy: <span className="text-zinc-300">{selectedStrategy}</span></div>
                   </div>
                   <div className="flex gap-2">
                     <button 
                       onClick={() => window.open('/api/backtest/export/pdf', '_blank')}
                       className="px-3 py-1.5 bg-amber-500/10 hover:bg-amber-500/20 border border-amber-500/30 text-amber-400 rounded text-[9px] font-bold tracking-widest transition-all"
                     >
                       <i className="fas fa-file-pdf mr-2" /> EXPORT REPORT
                     </button>
                   </div>
                 </div>

                 {/* Results Content */}
                 <div className="flex-1 overflow-y-auto custom-scrollbar p-6 space-y-8">
                    {/* Primary Metrics Grid */}
                    <div className="grid grid-cols-7 gap-3">
                      <MetricCard label="Net Profit" value={`$${results?.metrics?.total_pnl?.toFixed(2) || 0}`} isPositive={(results?.metrics?.total_pnl || 0) >= 0} />
                      <MetricCard label="Win Rate" value={`${((results?.metrics?.win_rate || 0)*100).toFixed(1)}%`} isNeutral={true} />
                      <MetricCard label="Profit Factor" value={results?.metrics?.profit_factor?.toFixed(2) || '0.00'} isNeutral={true} />
                      <MetricCard label="Max DD" value={`${((results?.metrics?.max_drawdown || 0)*100).toFixed(2)}%`} isPositive={false} />
                      <MetricCard label="Period" value={results?.duration || 'N/A'} isNeutral={true} />
                      <MetricCard label="Total Trades" value={results?.metrics?.total_trades || 0} isNeutral={true} />
                      <MetricCard label="Sharpe" value={results?.metrics?.sharpe_ratio?.toFixed(2) || '0.00'} isNeutral={true} />
                    </div>

                    {/* Dashboard Tabs & Chart/Log Area */}
                    <div className="flex flex-col bg-black/40 border border-white/[0.06] rounded-2xl overflow-hidden min-h-[400px]">
                      <div className="flex bg-white/[0.03] border-b border-white/[0.06] px-2">
                         <ResultTab id="equity" label="Equity Curve" icon="fa-chart-line" active={activeResultTab === "equity"} onClick={setActiveResultTab} />
                         <ResultTab id="drawdown" label="Drawdown" icon="fa-chart-area" active={activeResultTab === "drawdown"} onClick={setActiveResultTab} />
                         <ResultTab id="trades" label="Trade Log" icon="fa-list-ul" active={activeResultTab === "trades"} onClick={setActiveResultTab} />
                      </div>
                      <div className="flex-1 min-h-[300px] relative p-4">
                         {activeResultTab === "equity" && (
                           <div className="w-full h-full flex flex-col pt-8">
                              <div className="absolute top-4 left-6 text-[9px] font-bold text-zinc-500 uppercase tracking-widest font-mono">Simulated Balance Growth</div>
                              <canvas id="equityCanvas" className="w-full flex-1 max-h-[300px]"></canvas>
                           </div>
                         )}
                         {activeResultTab === "drawdown" && (
                            <div className="w-full h-full flex flex-col pt-8">
                               <div className="absolute top-4 left-6 text-[9px] font-bold text-red-500/80 uppercase tracking-widest font-mono">Simulated Drawdown Heatmap (%)</div>
                               <canvas id="drawdownCanvas" className="w-full flex-1 max-h-[300px]"></canvas>
                            </div>
                         )}
                         {activeResultTab === "trades" && (
                           <TradeTable trades={results.trades || []} />
                         )}
                      </div>
                    </div>
                 </div>
              </div>
            ) : (
              <div className="flex-1 flex flex-col items-center justify-center pointer-events-none select-none">
                <img src="/images/QuantumLLama.png" alt="Platform Logo" className="w-20 h-20 object-contain opacity-40 grayscale mb-6" onError={(e) => e.target.style.display='none'}/>
                <div className="text-xs font-mono tracking-widest uppercase text-zinc-600">Waiting For Simulation Results</div>
                <div className="text-[10px] mt-2 opacity-30 text-zinc-500 font-bold tracking-widest">
                  COMPLETE STEPS 1 THROUGH 7 IN THE LEFT MENU TO INITIATE SIMULATION
                </div>
              </div>
            )}
          </div>

          {/* BOTTOM LOGS */}
          <div className={`flex flex-col flex-1 min-h-[100px] ${DS.card} overflow-hidden`}>
            <div className="px-4 py-2 bg-white/[0.02] border-b border-white/[0.04] flex justify-between items-center">
              <span className="text-[10px] font-bold tracking-[0.2em] text-zinc-500 uppercase">TERMINAL LOGS</span>
              <button 
                onClick={() => setLogs([])}
                className="text-[9px] font-bold text-zinc-600 hover:text-white transition-colors uppercase tracking-widest">
                CLEAR
              </button>
            </div>
            <div className="flex-1 overflow-y-auto p-2 bg-[#050505]/50 custom-scrollbar font-mono">
              {logs.map((log, i) => <LogLine key={i} log={log} index={i} />)}
              <div ref={logsEndRef} />
            </div>
          </div>
        </div>

      </div>
    </div>
  );
};

window.BacktestPanel = BacktestPanel;
