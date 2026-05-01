const Header = ({ connectionStatus, systemStatus, accountData, activeSymbol, activeTF, onSymbolChange, onTFChange, onOpenSettings, onOpenSymbolSearch, currentView, onViewChange, showTape, toggleTape, showOrderEntry, toggleOrderEntry, showDom, toggleDom, onSaveWorkspace, layout, onLayoutChange, chartType, onChartTypeChange, realizedDailyPnl, lastMessageTime }) => {
  const { useState, useEffect, useRef } = React;
  const [saveStatus, setSaveStatus] = useState('idle');
  const [availableTimeframes, setAvailableTimeframes] = useState([]);
  useEffect(() => {
    const fetchTFs = async (plat) => {
      try {
        const res = await fetch(`/ api / timeframes ? platform = ${plat} `);
        if (res.ok) {
          const data = await res.json();
          if (data.timeframes) setAvailableTimeframes(data.timeframes);
        }
      } catch (err) {
        console.error("Failed to load native timeframes:", err);
      }
    };
    const initialPlatform = localStorage.getItem('platform') || 'mt5';
    fetchTFs(initialPlatform);
    const handlePlatformChange = (e) => fetchTFs(e.detail.newPlatform);
    window.addEventListener('platform_changed', handlePlatformChange);
    return () => window.removeEventListener('platform_changed', handlePlatformChange);
  }, []);
  const [isTFOpen, setIsTFOpen] = useState(false);
  const tfRef = useRef(null);
  useEffect(() => {
    const handleClickOutside = (event) => {
      if (tfRef.current && !tfRef.current.contains(event.target)) {
        setIsTFOpen(false);
      }
    };
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);
  const totalDailyPnl = (realizedDailyPnl ?? 0) + (accountData?.profit ?? 0);
  useEffect(() => {
    const handleStatus = (e) => {
      setSaveStatus(e.detail);
      if (e.detail === 'saved') {
        setTimeout(() => setSaveStatus('idle'), 3000);
      }
    };
    window.addEventListener('save_status', handleStatus);
    return () => window.removeEventListener('save_status', handleStatus);
  }, []);
  return (
    React.createElement("div", { className: "h-12 border-b border-border bg-panel flex items-center justify-between px-4 shrink-0 shadow-sm" },
    React.createElement("div", { className: "flex items-center gap-6" },
    React.createElement("a", { href: "https://llamaterminal.nbmsystemas.com", target: "_blank", rel: "noopener noreferrer", className: "flex items-center gap-3 hover:opacity-80 transition-opacity cursor-pointer" },
    React.createElement("img", { src: "/images/QuantumLLama.png", alt: "Logo", className: "h-8 w-8 object-contain drop-shadow-[0_0_5px_rgba(251,191,36,0.3)]" }),
    React.createElement("div", null,
    React.createElement("h1", { className: "font-bold text-xs tracking-widest text-accent leading-none" }, "QUANTUM LLAMA"),
    React.createElement("span", { className: "text-[8px] text-muted tracking-[0.1em] uppercase" }, "Professional Terminal")
    )
    ),
    React.createElement("div", { className: "h-6 w-px bg-border mx-2" }),
    React.createElement("div", { className: "flex items-center w-24 justify-center" },
    saveStatus === 'saving' && React.createElement("span", { className: "text-yellow-500 text-[10px] font-bold animate-pulse flex items-center" }, React.createElement("i", { className: "fas fa-sync fa-spin mr-1" }), " SAVING"),
    saveStatus === 'saved' && React.createElement("span", { className: "text-green-500 text-[10px] font-bold flex items-center animate-in fade-in zoom-in" }, React.createElement("i", { className: "fas fa-check mr-1" }), " SAVED"),
    saveStatus === 'error' && React.createElement("span", { className: "text-red-500 text-[10px] font-bold flex items-center" }, React.createElement("i", { className: "fas fa-exclamation-circle mr-1" }), " ERROR")
    ),
    React.createElement("div", { className: "h-6 w-px bg-border mx-2" }),
    React.createElement("div", { className: "flex bg-black rounded border border-border p-0.5 gap-1" },
    React.createElement("button", {
      onClick: () => onViewChange('chart'),
      className: `px - 3 py - 1 text - [10px] font - bold rounded - sm transition - all flex items - center gap - 2 ${currentView === 'chart' ? 'bg-white/10 text-white shadow' : 'text-muted hover:text-white'} ` },
    React.createElement("i", { className: "fas fa-chart-line" }), " TRADING"
    ),
    React.createElement("button", {
      onClick: () => onViewChange('algo'),
      className: `px - 3 py - 1 text - [10px] font - bold rounded - sm transition - all flex items - center gap - 2 ${currentView === 'algo' ? 'bg-white/10 text-accent shadow' : 'text-muted hover:text-white'} ` },
    React.createElement("i", { className: "fas fa-gauge-high" }), " ALGO PANEL"
    ),
    React.createElement("button", {
      onClick: () => onViewChange('editor'),
      className: `px - 3 py - 1 text - [10px] font - bold rounded - sm transition - all flex items - center gap - 2 ${currentView === 'editor' ? 'bg-white/10 text-accent shadow' : 'text-muted hover:text-white'} ` },
    React.createElement("i", { className: "fas fa-code" }), " ALGO LAB"
    ),
    React.createElement("button", {
      onClick: () => onViewChange('backtest'),
      className: `px - 3 py - 1 text - [10px] font - bold rounded - sm transition - all flex items - center gap - 2 ${currentView === 'backtest' ? 'bg-white/10 text-accent shadow' : 'text-muted hover:text-white'} ` },
    React.createElement("i", { className: "fas fa-vial" }), " BACKTEST"
    )
    ),
    React.createElement("div", { className: "h-6 w-px bg-border mx-2" }),
    currentView === 'chart' &&
    React.createElement("div", { className: "flex items-center gap-2" },
    React.createElement("div", { className: "flex bg-black rounded border border-border p-0.5 gap-1" },
    React.createElement(Tooltip, { text: "Single Chart" },
    React.createElement("button", { onClick: () => onLayoutChange('single'), className: `w - 6 h - 6 flex items - center justify - center rounded - sm transition - all ${layout === 'single' ? 'bg-white/10 text-accent' : 'text-muted hover:text-white'} ` },
    React.createElement("div", { className: "w-3 h-3 border border-current rounded-[1px]" })
    )
    ),
    React.createElement(Tooltip, { text: "Split Vertical" },
    React.createElement("button", { onClick: () => onLayoutChange('2v'), className: `w - 6 h - 6 flex items - center justify - center rounded - sm transition - all ${layout === '2v' ? 'bg-white/10 text-accent' : 'text-muted hover:text-white'} ` },
    React.createElement("div", { className: "flex w-3 h-3 gap-0.5" },
    React.createElement("div", { className: "w-1/2 h-full border border-current rounded-[1px]" }),
    React.createElement("div", { className: "w-1/2 h-full border border-current rounded-[1px]" })
    )
    )
    ),
    React.createElement(Tooltip, { text: "Split Horizontal" },
    React.createElement("button", { onClick: () => onLayoutChange('2h'), className: `w - 6 h - 6 flex items - center justify - center rounded - sm transition - all ${layout === '2h' ? 'bg-white/10 text-accent' : 'text-muted hover:text-white'} ` },
    React.createElement("div", { className: "flex flex-col w-3 h-3 gap-0.5" },
    React.createElement("div", { className: "w-full h-1/2 border border-current rounded-[1px]" }),
    React.createElement("div", { className: "w-full h-1/2 border border-current rounded-[1px]" })
    )
    )
    ),
    React.createElement(Tooltip, { text: "Grid (4)" },
    React.createElement("button", { onClick: () => onLayoutChange('4'), className: `w - 6 h - 6 flex items - center justify - center rounded - sm transition - all ${layout === '4' ? 'bg-white/10 text-accent' : 'text-muted hover:text-white'} ` },
    React.createElement("div", { className: "grid grid-cols-2 gap-0.5 w-3 h-3" },
    React.createElement("div", { className: "border border-current rounded-[1px]" }),
    React.createElement("div", { className: "border border-current rounded-[1px]" }),
    React.createElement("div", { className: "border border-current rounded-[1px]" }),
    React.createElement("div", { className: "border border-current rounded-[1px]" })
    )
    )
    )
    ),
    React.createElement("div", { className: "h-4 w-px bg-border mx-1" }),
    React.createElement("div", { className: "flex bg-black rounded border border-border p-0.5 gap-1" },
    React.createElement(Tooltip, { text: "Toggle Tape Panel" },
    React.createElement("button", { onClick: toggleTape, className: `px - 2 py - 1 text - [10px] rounded - sm transition - all ${showTape ? 'bg-white/10 text-accent' : 'text-muted hover:text-white'} ` },
    React.createElement("i", { className: "fas fa-list-ol" })
    )
    ),
    React.createElement(Tooltip, { text: "Toggle Trade Panel" },
    React.createElement("button", { onClick: toggleOrderEntry, className: `px - 2 py - 1 text - [10px] rounded - sm transition - all ${showOrderEntry ? 'bg-white/10 text-accent' : 'text-muted hover:text-white'} ` },
    React.createElement("i", { className: "fas fa-columns" })
    )
    ),
    React.createElement(Tooltip, { text: "Toggle DOM Panel" },
    React.createElement("button", { onClick: toggleDom, className: `px - 2 py - 1 text - [10px] rounded - sm transition - all ${showDom ? 'bg-white/10 text-accent' : 'text-muted hover:text-white'} ` },
    React.createElement("i", { className: "fas fa-layer-group" })
    )
    )
    )
    ),
    React.createElement("div", { className: "h-6 w-px bg-border mx-2" }),
    React.createElement("div", { className: "flex bg-black/40 rounded-full border border-border p-0.5 gap-0.5" },
    [
    { id: 'tradovate', label: 'TRADOVATE', color: 'text-emerald-400' },
    { id: 'crypto', label: 'CRYPTO', color: 'text-purple-400' },
    { id: 'mt5', label: 'CFD', color: 'text-blue-400' }].
    map((p) =>
    React.createElement("button", {
      key: p.id,
      onClick: () => {
        const oldPlatform = localStorage.getItem('platform') || 'tradovate';
        if (oldPlatform === p.id) return;
        window.dispatchEvent(new CustomEvent('platform_changed', {
          detail: { oldPlatform, newPlatform: p.id }
        }));
      },
      className: `px - 2 py - 0.5 text - [8px] font - bold rounded - full transition - all ${(localStorage.getItem('platform') || 'tradovate') === p.id ?
      'bg-white/10 ' + p.color :
      'text-muted hover:text-white hover:bg-white/5'} ` },
    p.label
    )
    )
    ),
    React.createElement("div", { className: "h-6 w-px bg-border mx-1" }),
    React.createElement("div", { className: "flex items-center gap-2" },
    React.createElement("button", {
      onClick: onOpenSymbolSearch,
      className: "flex items-center gap-2 text-sm font-bold text-white hover:text-accent transition-colors py-1.5 bg-black/30 px-3 rounded border border-transparent hover:border-accent/30" },
    React.createElement("i", { className: "fas fa-search text-[10px] text-muted" }),
    activeSymbol,
    React.createElement("i", { className: "fas fa-chevron-down text-[10px] opacity-50 ml-1" })
    )
    ),
    React.createElement("div", { className: "relative", ref: tfRef },
    React.createElement("button", {
      onClick: () => setIsTFOpen(!isTFOpen),
      className: "flex items-center gap-2 text-sm font-bold text-accent hover:text-white transition-colors py-1.5 bg-black/30 px-3 rounded border border-transparent hover:border-accent/30" },
    React.createElement("i", { className: "fas fa-clock text-[10px] text-muted" }),
    activeTF,
    React.createElement("i", { className: `fas fa - chevron - down text - [10px] opacity - 50 ml - 1 transition - transform ${isTFOpen ? 'rotate-180' : ''} ` })
    ),
    isTFOpen &&
    React.createElement("div", { className: "absolute top-full left-0 mt-1 w-24 max-h-[300px] overflow-y-auto custom-scrollbar bg-black border border-white/10 rounded-sm shadow-xl z-50 flex flex-col py-1" },
    (availableTimeframes.length > 0 ? availableTimeframes : ['1m']).map((tf) =>
    React.createElement("button", {
      key: tf,
      onClick: () => {
        onTFChange(tf);
        setIsTFOpen(false);
      },
      className: `px - 3 py - 1.5 text - left text - xs font - bold transition - colors hover: bg - white / 10 ${activeTF === tf ? 'text-accent bg-white/5' : 'text-gray-300'} ` },
    tf
    )
    )
    )
    ),
    React.createElement("div", { className: "flex items-center gap-1 bg-black/30 rounded px-1 border border-border/50" },
    React.createElement(Tooltip, { text: chartType === 'candle' ? "Switch to Area Chart" : "Switch to Candlestick Chart" },
    React.createElement("button", {
      onClick: () => onChartTypeChange(chartType === 'candle' ? 'line' : 'candle'),
      className: `p - 1.5 transition - colors ${chartType === 'line' ? 'text-accent' : 'text-muted hover:text-white'} ` },
    React.createElement("i", { className: `fas ${chartType === 'candle' ? 'fa-chart-area' : 'fa-chart-bar'} text - [10px]` })
    )
    ),
    React.createElement("div", { className: "w-px h-3 bg-border/50 mx-0.5" }),
    React.createElement(Tooltip, { text: "Refresh Active Chart - Reloads chart data and indicators" },
    React.createElement("button", {
      onClick: () => {
        window.dispatchEvent(new CustomEvent('refresh_chart', {
          detail: { symbol: activeSymbol, timeframe: activeTF }
        }));
        window.dispatchEvent(new CustomEvent('notify', {
          detail: { type: 'success', title: 'Chart Refreshing', message: `Reloading data for ${activeSymbol}(${activeTF})` }
        }));
      },
      className: "p-1.5 text-muted hover:text-accent transition-colors" },
    React.createElement("i", { className: "fas fa-sync-alt text-[10px]" })
    )
    )
    )
    ),
    React.createElement("div", { className: "flex items-center gap-6 text-xs font-mono" },
    React.createElement("div", { className: "flex flex-col items-end" },
    React.createElement("span", { className: "text-muted text-[10px]" }, "BALANCE"),
    React.createElement("span", { className: "text-white font-bold" }, "$", (accountData?.balance ?? systemStatus?.account?.balance ?? 0).toFixed(2))
    ),
    React.createElement("div", { className: "flex flex-col items-end" },
    React.createElement("span", { className: "text-muted text-[10px]" }, "EQUITY"),
    React.createElement("span", { className: "text-blue-400 font-bold" }, "$", (accountData?.equity ?? systemStatus?.account?.equity ?? 0).toFixed(2))
    ),
    React.createElement("div", { className: "flex flex-col items-end" },
    React.createElement("span", { className: "text-muted text-[10px]" }, "PNL DAY"),
    React.createElement("span", { className: `font - bold ${totalDailyPnl >= 0 ? 'text-success' : 'text-danger'} ` },
    totalDailyPnl >= 0 ? '+' : '', "$", totalDailyPnl.toFixed(2)
    )
    ),
    React.createElement(Tooltip, { text: "Save Workspace to Cloud" },
    React.createElement("button", {
      onClick: saveStatus === 'saving' ? undefined : onSaveWorkspace,
      className: `relative w-8 h-8 flex items-center justify-center transition-colors rounded-full ${saveStatus === 'saved' ? 'text-green-500' : saveStatus === 'error' ? 'text-red-500' : 'text-muted hover:text-accent hover:bg-white/5'}` },
    React.createElement("i", { className: `fas ${saveStatus === 'saved' ? 'fa-check' : saveStatus === 'error' ? 'fa-times' : 'fa-cloud-upload-alt'} text-sm z-10 transition-transform ${saveStatus === 'saved' ? 'animate-in zoom-in' : ''}` }),
    saveStatus === 'saving' &&
    React.createElement("svg", { className: "absolute inset-0 w-full h-full -rotate-90 animate-spin", viewBox: "0 0 24 24" },
    React.createElement("circle", { className: "opacity-20", cx: "12", cy: "12", r: "11", stroke: "currentColor", strokeWidth: "1.5", fill: "none" }),
    React.createElement("circle", { className: "text-accent", cx: "12", cy: "12", r: "11", stroke: "currentColor", strokeWidth: "1.5", fill: "none", strokeDasharray: "69", strokeDashoffset: "17", strokeLinecap: "round" })
    ),
    saveStatus === 'saved' &&
    React.createElement("svg", { className: "absolute inset-0 w-full h-full -rotate-90", viewBox: "0 0 24 24" },
    React.createElement("circle", {
      className: "text-green-500 animate-[dash_0.6s_ease-out_forwards]",
      cx: "12", cy: "12", r: "11",
      stroke: "currentColor",
      strokeWidth: "1.5",
      fill: "none",
      strokeDasharray: "69",
      strokeDashoffset: "69",
      strokeLinecap: "round" }
    ),
    React.createElement("style", null, `@keyframes dash { to { stroke-dashoffset: 0; } }`)
    )
    )
    ),
    React.createElement("button", { onClick: onOpenSettings, className: "p-2 text-muted hover:text-white transition-colors" },
    React.createElement("i", { className: "fas fa-cog" })
    ),
    React.createElement("div", { className: "h-6 w-px bg-border mx-2" }),
    React.createElement("div", { className: "flex items-center gap-2 bg-black/50 px-3 py-1.5 rounded-full border border-border" },
    React.createElement("div", { className: "relative" },
    React.createElement("div", { className: `w - 2 h - 2 rounded - full ${connectionStatus ? 'bg-success shadow-[0_0_5px_#10b981]' : 'bg-danger'} ` }),
    connectionStatus &&
    React.createElement("div", { className: `absolute - inset - 1 rounded - full animate - ping opacity - 20 ${Date.now() - (lastMessageTime || 0) < 15000 ? 'bg-success' :
      Date.now() - (lastMessageTime || 0) < 30000 ? 'bg-yellow-500' :
      'bg-danger'} ` }
    )
    ),
    React.createElement("span", { className: "text-[10px] font-bold tracking-wider" }, connectionStatus ? 'CONNECTED' : 'OFFLINE'),
    connectionStatus &&
    React.createElement("div", { className: "flex items-center gap-1 ml-1 pl-2 border-l border-white/10", title: "Data Heartbeat (Real-time connectivity pulse)" },
    React.createElement("div", { className: `w - 1 h - 1 rounded - full transition - all duration - 300 ${Date.now() - (lastMessageTime || 0) < 5000 ? 'bg-accent animate-pulse scale-125' :
      Date.now() - (lastMessageTime || 0) < 15000 ? 'bg-accent/40 scale-100' :
      'bg-red-500/40 scale-75'} ` }
    )
    )
    )
    )
    ));
};
window.Header = Header;