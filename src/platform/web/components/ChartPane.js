const { useState, useEffect, useRef, useMemo, useCallback } = React;
const ChartComponent = window.ChartComponent;
const ErrorBoundary = window.ErrorBoundary;
const QuantumLoader = ({ message = "Loading...", size = "md" }) => {
  const sizeClasses = {
    sm: "w-6 h-6",
    md: "w-12 h-12",
    lg: "w-20 h-20",
    xl: "w-28 h-28"
  };
  const textSizes = {
    sm: "text-[9px]",
    md: "text-[10px]",
    lg: "text-[11px]",
    xl: "text-xs"
  };
  return (
    React.createElement("div", { className: "flex flex-col items-center justify-center gap-3 p-4" },
    React.createElement("div", { className: "relative" },
    React.createElement("div", {
      className: `${sizeClasses[size]} border border-transparent border-t-accent/80 border-r-accent/30 rounded-full animate-spin`,
      style: { animationDuration: '0.8s' } }
    ),
    React.createElement("div", { className: "absolute inset-0 flex items-center justify-center" },
    React.createElement("img", {
      src: "/images/QuantumLLama.png",
      alt: "QuantumLlama",
      className: "w-3/4 h-3/4 object-contain animate-pulse opacity-80",
      style: {
        filter: "drop-shadow(0 0 8px rgba(251, 191, 36, 0.2))"
      } }
    )
    ),
    React.createElement("div", {
      className: `absolute inset-[-4px] border border-transparent border-b-accent/50 border-l-accent/20 rounded-full animate-spin`,
      style: {
        animationDirection: "reverse",
        animationDuration: "1.5s"
      } }
    )
    ),
    React.createElement("div", {
      className: `${textSizes[size]} text-muted/60 font-medium animate-pulse tracking-[0.1em] uppercase` },
    message
    ),
    React.createElement("div", { className: "w-16 h-[2px] bg-white/5 rounded-full overflow-hidden" },
    React.createElement("div", { className: "h-full bg-accent/40 animate-pulse" })
    )
    ));
};
const DrawingToolBtn = ({ id, icon, label, activeTool, onSelect, desc }) =>
React.createElement("div", { className: "group relative flex items-center justify-center" },
React.createElement("button", {
  className: `p-1.5 rounded hover:bg-white/10 transition-colors relative group/btn w-full ${activeTool === id ? "text-accent bg-white/5" : "text-gray-400"}`,
  onClick: (e) => {
    e.stopPropagation();
    onSelect(id);
  },
  title: `${label} - ${desc}` },
React.createElement("i", { className: `fas ${icon} text-xs` }),
id !== "cursor" && activeTool === id &&
React.createElement("span", { className: "absolute top-0.5 right-0.5 w-1 h-1 bg-accent rounded-full animate-pulse" })
)
);
const DrawingToolbar = ({
  activeTool,
  onToolChange,
  onClear,
  isExpanded,
  visible = true
}) => {
  if (!visible || !isExpanded) return null;
  return (
    React.createElement("div", {
      className: "absolute top-1/2 -translate-y-1/2 left-2 z-50 flex flex-col bg-black/80 border border-white/10 rounded-full shadow-2xl overflow-hidden backdrop-blur-xl w-[32px] py-3 animate-in fade-in slide-in-from-left-2 duration-200 max-h-[85vh] overflow-y-auto no-scrollbar",
      onClick: (e) => e.stopPropagation() },
    React.createElement("div", { className: "flex flex-col p-1 gap-1.5" },
    React.createElement(DrawingToolBtn, {
      id: "cursor",
      icon: "fa-mouse-pointer",
      label: "Cursor",
      desc: "Select",
      activeTool: activeTool,
      onSelect: onToolChange }
    ),
    React.createElement(DrawingToolBtn, {
      id: "crosshair",
      icon: "fa-crosshairs",
      label: "Crosshair",
      desc: "Measure",
      activeTool: activeTool,
      onSelect: onToolChange }
    ),
    React.createElement(DrawingToolBtn, {
      id: "hline",
      icon: "fa-minus",
      label: "Horz Line",
      desc: "Level",
      activeTool: activeTool,
      onSelect: onToolChange }
    ),
    React.createElement(DrawingToolBtn, {
      id: "pencil",
      icon: "fa-pencil-alt",
      label: "Pencil",
      desc: "Freehand",
      activeTool: activeTool,
      onSelect: onToolChange }
    ),
    React.createElement(DrawingToolBtn, {
      id: "rect",
      icon: "fa-vector-square",
      label: "Rectangle",
      desc: "Box",
      activeTool: activeTool,
      onSelect: onToolChange }
    ),
    React.createElement(DrawingToolBtn, {
      id: "circle",
      icon: "fa-circle-notch",
      label: "Circle",
      desc: "Circle",
      activeTool: activeTool,
      onSelect: onToolChange }
    ),
    React.createElement(DrawingToolBtn, {
      id: "text",
      icon: "fa-font",
      label: "Text",
      desc: "Label",
      activeTool: activeTool,
      onSelect: onToolChange }
    ),
    React.createElement(DrawingToolBtn, {
      id: "arrow",
      icon: "fa-long-arrow-alt-right",
      label: "Arrow",
      desc: "Direction",
      activeTool: activeTool,
      onSelect: onToolChange }
    ),
    React.createElement(DrawingToolBtn, {
      id: "fib",
      icon: "fa-bars",
      label: "Fibonacci",
      desc: "Retracement",
      activeTool: activeTool,
      onSelect: onToolChange }
    ),
    React.createElement(DrawingToolBtn, {
      id: "risk",
      icon: "fa-ruler-combined",
      label: "Risk/Reward",
      desc: "R/R Tool",
      activeTool: activeTool,
      onSelect: onToolChange }
    ),
    React.createElement(DrawingToolBtn, {
      id: "measure",
      icon: "fa-ruler-horizontal",
      label: "Measure",
      desc: "Ruler",
      activeTool: activeTool,
      onSelect: onToolChange }
    )
    ),
    React.createElement("div", { className: "p-1 border-t border-white/5" },
    React.createElement("button", {
      onClick: (e) => {
        e.stopPropagation();
        onClear && onClear();
        window.dispatchEvent(new CustomEvent('clear_drawings_local'));
      },
      className: "w-full py-1 rounded hover:bg-red-500/20 text-gray-500 hover:text-red-500 transition-colors text-[10px]",
      title: "Clear All" },
    React.createElement("i", { className: "fas fa-trash" })
    )
    )
    ));
};
const ChartPane = React.memo(({
  chartSettings,
  onOpenSettings,
  session,
  chartId,
  symbol,
  tf,
  isActive,
  activeTool,
  systemStatus,
  onOrder,
  onActivate,
  tickData,
  indicators,
  globalBigTradesRef,
  mt5Positions,
  mt5PendingOrders,
  onUpdateSettings,
  setLastCandleTime,
  isPopout = false,
  platform,
  onSymbolChange,
  onTFChange,
  onOpenSymbolSearch,
  onToolChange,
  symbolMetadata,
  volume,
  refreshKey
}) => {
  const [historicalData, setHistoricalData] = useState(null);
  const [loadingError, setLoadingError] = useState(null);
  const [isFetching, setIsFetching] = useState(false);
  const lastFetchedSymbolRef = useRef(null);
  const lastFetchedTfRef = useRef(null);
  const lastFetchedPlatformRef = useRef(null);
  const loadingTimeoutRef = useRef(null);
  const lastRefreshKeyRef = useRef(null);
  const showVolume = chartSettings?.overlays?.showVolume ?? true;
  const showDelta = chartSettings?.overlays?.showDelta ?? true;
  const showAllOverlays = chartSettings?.overlays?.showAll ?? true;
  const chartType = chartSettings?.chartType || "candle";
  const [isLlamaActive, setIsLlamaActive] = useState(false);
  const [availableTimeframes, setAvailableTimeframes] = useState([]);
  const [isTFOpen, setIsTFOpen] = useState(false);
  useEffect(() => {
    const fetchTFs = async (plat) => {
      try {
        const res = await window.authFetch(`/api/timeframes?platform=${plat}`);
        if (res.ok) {
          const data = await res.json();
          if (data.timeframes) setAvailableTimeframes(data.timeframes);
        }
      } catch (err) {
        console.error("Failed to load native timeframes:", err);
      }
    };
    const initialPlatform = detectPlatformType();
    fetchTFs(initialPlatform);
    const handlePlatformChange = (e) => fetchTFs(e.detail.newPlatform);
    window.addEventListener('platform_changed', handlePlatformChange);
    return () => window.removeEventListener('platform_changed', handlePlatformChange);
  }, []);
  const platformType = detectPlatformType();
  const mappedSymbol = getUniversalSymbol(symbol, platformType);
  useEffect(() => {
    if (
    lastFetchedSymbolRef.current === mappedSymbol &&
    lastFetchedTfRef.current === tf &&
    lastFetchedPlatformRef.current === platformType &&
    lastRefreshKeyRef.current === refreshKey)
    {
      return;
    }
    const symChanged = lastFetchedSymbolRef.current !== mappedSymbol;
    const tfChanged = lastFetchedTfRef.current !== tf;
    const platChanged = lastFetchedPlatformRef.current !== platformType;
    const manualRefresh = lastRefreshKeyRef.current !== refreshKey;
    if (symChanged || tfChanged || platChanged || manualRefresh) {
      setIsFetching(true);
      setLoadingError(null);
    }
    loadingTimeoutRef.current = setTimeout(() => {
      setLoadingError({
        symbol: mappedSymbol,
        platform: platformType,
        message: "No data received from server"
      });
    }, 10000);
    const ctrl = new AbortController();
    const fetchHistory = async () => {
      try {
        let candleLimits = {
          "1m": 3000,
          "5m": 5000,
          "15m": 2500,
          "30m": 2000,
          "1h": 2000,
          "4h": 1000,
          "1d": 500
        };
        try {
          const storedLimits = localStorage.getItem("chart_history_limits");
          if (storedLimits) {
            candleLimits = { ...candleLimits, ...JSON.parse(storedLimits) };
          }
        } catch (e) {
          console.warn("Failed to parse history limits", e);
        }
        const historyLimit = candleLimits[tf] || 2500;
        const url = `/api/history?symbol=${encodeURIComponent(mappedSymbol)}&timeframe=${tf}&limit=${historyLimit}&platform=${platformType}`;
        const res = await window.authFetch(url, { signal: ctrl.signal });
        if (!res.ok) {
          clearTimeout(loadingTimeoutRef.current);
          setLoadingError({
            symbol: mappedSymbol,
            platform: platformType,
            message: `Error ${res.status}: ${res.statusText}`
          });
          return;
        }
        const hist = await res.json();
        clearTimeout(loadingTimeoutRef.current);
        if (Array.isArray(hist) && hist.length > 0) {
          setHistoricalData(hist);
          setIsFetching(false);
          setLoadingError(null);
          lastFetchedSymbolRef.current = mappedSymbol;
          lastFetchedTfRef.current = tf;
          lastFetchedPlatformRef.current = platformType;
          lastRefreshKeyRef.current = refreshKey;
        } else {
          clearTimeout(loadingTimeoutRef.current);
          setLoadingError({
            symbol: mappedSymbol,
            platform: platformType,
            message: "Server has no data for this symbol"
          });
        }
      } catch (e) {
        if (e.name === 'AbortError') return;
        clearTimeout(loadingTimeoutRef.current);
        setLoadingError({
          symbol: mappedSymbol,
          platform: platformType,
          message: `Connection error: ${e.message}`
        });
      }
    };
    fetchHistory();
    return () => {
      ctrl.abort();
      if (loadingTimeoutRef.current) clearTimeout(loadingTimeoutRef.current);
    };
  }, [mappedSymbol, tf, platformType, refreshKey]);

  const isAlgoLive =
  systemStatus && (
  systemStatus.symbol === symbol ||
  systemStatus.ticker === symbol ||
  systemStatus.platform_symbol === symbol ||
  systemStatus.symbol === mappedSymbol ||
  systemStatus.ticker === mappedSymbol ||
  systemStatus.platform_symbol === mappedSymbol);
  const [localTool, setLocalTool] = useState("cursor");
  const [isToolbarExpanded, setIsToolbarExpanded] = useState(() => {
    return localStorage.getItem(`drawing_toolbar_expanded_${chartId}`) !== "false";
  });
  useEffect(() => {
    localStorage.setItem(`drawing_toolbar_expanded_${chartId}`, isToolbarExpanded);
  }, [isToolbarExpanded, chartId]);
  useEffect(() => {
    if (!isPopout && activeTool) setLocalTool(activeTool);
  }, [activeTool, isPopout]);
  const handleToolFinish = useCallback(() => {
    if (localTool === "pencil") return;
    if (isPopout) setLocalTool("cursor");
    else if (onToolChange) onToolChange("cursor");
  }, [localTool, isPopout, onToolChange]);
  const handlePaneClick = useCallback(() => {
    if (onActivate) onActivate(chartId);
  }, [onActivate, chartId]);
  const handleOpenSettingsLocal = useCallback(() => {
    if (onOpenSettings) onOpenSettings(chartId);
  }, [onOpenSettings, chartId]);

  // Positioning logic for panels
  const renderPanel = (type) => {
    const layout = chartSettings?.layout || {};
    
    // Skip redundant side panels in popout mode since index.html handles them manually
    if (isPopout && (type === 'tape' || type === 'orderEntry')) return null;

    if (type === 'dom' && layout.showDom && window.DOMPanel && window.ResizablePanel) {
      const sidePref = layout.domSide || 'left';
      return React.createElement(window.ResizablePanel, {
        width: layout.domWidth || 250,
        onResize: (w) => onUpdateSettings({ ...chartSettings, layout: { ...layout, domWidth: w } }),
        side: sidePref === 'left' ? 'right' : 'left', // Handle on opposite side of panel's position
        minWidth: 150,
        maxWidth: 500,
        className: `${sidePref === 'left' ? 'border-r' : 'border-l'} border-border bg-[#111] z-20 shadow-xl flex`
      }, React.createElement(window.DOMPanel, {
        symbol: symbol,
        onClose: () => onUpdateSettings({ ...chartSettings, layout: { ...layout, showDom: false } })
      }));
    }
    if (type === 'tape' && layout.showTape && window.TapePanel && window.ResizablePanel) {
      const sidePref = layout.tapeSide || 'left';
      return React.createElement(window.ResizablePanel, {
        width: layout.tapeWidth || 220,
        onResize: (w) => onUpdateSettings({ ...chartSettings, layout: { ...layout, tapeWidth: w } }),
        side: sidePref === 'left' ? 'right' : 'left',
        minWidth: 120,
        maxWidth: 450,
        className: `${sidePref === 'left' ? 'border-r' : 'border-l'} border-border bg-[#111] z-20 shadow-xl flex`
      }, React.createElement(window.TapePanel, {
        symbol: symbol,
        lastPrice: tickData?.last || (historicalData && historicalData.length > 0 ? historicalData[historicalData.length-1].close : 0),
        volume: tickData?.volume || (historicalData && historicalData.length > 0 ? historicalData[historicalData.length-1].volume : 0),
        timestamp: tickData?.time || Date.now(),
        title: "Time & Sales",
        configId: `chart-${chartId}`,
        onClose: () => onUpdateSettings({ ...chartSettings, layout: { ...layout, showTape: false } })
      }));
    }
    if (type === 'orderEntry' && layout.showOrderEntry && window.OrderEntryPanel && window.ResizablePanel) {
      const sidePref = layout.orderEntrySide || 'right';
      return React.createElement(window.ResizablePanel, {
        width: layout.orderEntryWidth || 320,
        onResize: (w) => onUpdateSettings({ ...chartSettings, layout: { ...layout, orderEntryWidth: w } }),
        side: sidePref === 'left' ? 'right' : 'left',
        minWidth: 200,
        maxWidth: 600,
        className: `${sidePref === 'left' ? 'border-r' : 'border-l'} border-border bg-[#111] z-20 shadow-xl flex`
      }, React.createElement(window.OrderEntryPanel, {
        showOrderEntry: true,
        orderEntryWidth: layout.orderEntryWidth || 320,
        setOrderEntryWidth: (w) => onUpdateSettings({ ...chartSettings, layout: { ...layout, orderEntryWidth: w } }),
        status: systemStatus,
        handleOrder: onOrder,
        activeSymbol: symbol,
        tickData: { [getUniversalSymbol(symbol)]: tickData },
        mt5Positions: mt5Positions,
        mt5PendingOrders: mt5PendingOrders,
        oneClick: localStorage.getItem("oneClickTrading") === "true",
        setOneClick: (val) => {
          localStorage.setItem("oneClickTrading", val ? "true" : "false");
          window.dispatchEvent(new CustomEvent("one_click_changed", { detail: val }));
        },
        indicators: indicators,
        onSymbolChange: onSymbolChange,
        isPopout: isPopout,
        availableAccounts: [],
        symbolMetadata: symbolMetadata,
        isInitialRender: { current: false },
        volume: volume,
        onVolumeChange: () => {}
      }));
    }
    return null;
  };

  const layout = chartSettings?.layout || {};
  const leftPanels = [];
  const rightPanels = [];
  ['dom', 'tape', 'orderEntry'].forEach(p => {
    const side = p === 'orderEntry' ? (layout.orderEntrySide || 'right') : (p === 'dom' ? (layout.domSide || 'left') : (layout.tapeSide || 'left'));
    if (side === 'left') leftPanels.push(renderPanel(p));
    else rightPanels.push(renderPanel(p));
  });

  return (
    React.createElement("div", {
      className: `h-full w-full min-h-0 min-w-0 flex flex-col relative group/pane overflow-hidden chart-pane-container transition-shadow duration-300 ${isActive ? "bg-accent/[0.02] ring-1 ring-accent/20" : "bg-black/20"}`,
      onClick: handlePaneClick },
    React.createElement(ErrorBoundary, null,
    React.createElement("div", { className: "flex-1 flex overflow-hidden relative" },
    leftPanels,
    React.createElement("div", { className: "flex-1 relative overflow-hidden" },
    (isActive || isPopout) &&
    React.createElement(DrawingToolbar, {
      activeTool: localTool,
      isExpanded: isToolbarExpanded,
      onToolChange: (tool) => {
        setLocalTool(tool);
        if (!isPopout && onToolChange) onToolChange(tool);
      },
      onClear: () => window.dispatchEvent(new CustomEvent('clear_drawings_local')) }
    ),
    React.createElement("div", { className: "absolute top-2 left-2 z-30 flex items-center gap-1.5 pointer-events-auto opacity-0 group-hover/pane:opacity-100 transition-opacity whitespace-nowrap" },
    React.createElement("div", { className: "flex items-center gap-1 shrink-0" },
    React.createElement("span", {
      className: `bg-black/60 text-white/90 text-[8px] px-1.5 py-0.5 rounded-sm font-semibold border border-white/5 backdrop-blur-sm shadow-sm flex items-center gap-1.5 whitespace-nowrap ${isPopout ? "cursor-pointer hover:bg-black/80 hover:border-accent/30 transition-colors" : ""}`,
      onClick: () => isPopout && onOpenSymbolSearch && onOpenSymbolSearch() },
    symbol.split(':')[0],
    isPopout && React.createElement("i", { className: "fas fa-search text-[7px] text-accent/50 ml-0.5" })
    ),
    isPopout &&
    React.createElement("div", {
      className: "relative flex bg-black/40 rounded px-1.5 py-0.5 items-center gap-1 border border-white/5 backdrop-blur-sm group-hover/pane:opacity-100 opacity-60 transition-opacity cursor-pointer hover:bg-black/60 hover:border-accent/30",
      onClick: (e) => {e.stopPropagation();setIsTFOpen(!isTFOpen);},
      onMouseLeave: () => setIsTFOpen(false) },
    React.createElement("span", { className: "text-accent text-[8px] font-bold uppercase w-6 text-center" }, tf),
    React.createElement("i", { className: `fas fa-chevron-down text-[6px] text-muted transition-transform ${isTFOpen ? 'rotate-180' : ''}` }),
    isTFOpen &&
    React.createElement("div", { className: "absolute top-full left-0 mt-1 w-16 max-h-[250px] overflow-y-auto no-scrollbar bg-black border border-white/10 rounded-sm shadow-xl z-50 flex flex-col py-0.5",
      onClick: (e) => e.stopPropagation() },
    (availableTimeframes.length > 0 ? availableTimeframes : ['1m']).map((t) =>
    React.createElement("button", {
      key: t,
      onClick: (e) => { e.stopPropagation(); onTFChange && onTFChange(t); setIsTFOpen(false); },
      className: `px-2 py-1 text-left text-[9px] font-bold transition-colors hover:bg-white/10 uppercase ${tf === t ? 'text-accent bg-white/5' : 'text-gray-300'}` },
    t
    )
    )
    )
    )
    ),
    isActive &&
    React.createElement("span", { className: "bg-accent/50 text-black text-[8px] px-1.5 py-0.5 rounded-sm font-bold shadow-sm tracking-tighter shrink-0 whitespace-nowrap" }, "ACTIVE"),
    platformType !== "futures" &&
    React.createElement("span", {
      className: `text-white text-[8px] px-1.5 py-0.5 rounded-sm font-bold shadow-sm shrink-0 whitespace-nowrap ${platformType === "mt5" ? "bg-blue-600/50" : platformType === "crypto" ? "bg-purple-600/50" : "bg-gray-600/50"}` },
    getPlatformDisplayName(platformType)
    ),
    React.createElement("div", { className: "ml-2 opacity-0 group-hover/pane:opacity-100 transition-opacity shrink-0" },
    React.createElement("button", {
      onClick: (e) => { e.stopPropagation(); handleOpenSettingsLocal(); },
      className: "bg-black/40 hover:bg-black/60 text-gray-400 hover:text-accent p-0.5 rounded transition-colors border border-white/5 backdrop-blur-sm flex items-center justify-center w-[18px] h-[16px]",
      title: "Chart Settings" },
    React.createElement("i", { className: "fas fa-cog text-[9px]" })
    )
    ),
    React.createElement("div", { className: "ml-1 opacity-0 group-hover/pane:opacity-100 transition-opacity shrink-0" },
    React.createElement("button", {
      onClick: (e) => { e.stopPropagation(); setIsToolbarExpanded(!isToolbarExpanded); },
      className: `hover:bg-black/60 p-0.5 rounded transition-colors border border-white/5 backdrop-blur-sm flex items-center justify-center w-[18px] h-[16px] ${isToolbarExpanded ? "bg-accent/20 text-accent" : "bg-black/40 text-gray-400 hover:text-white"}`,
      title: isToolbarExpanded ? "Hide Drawing Toolbar" : "Show Drawing Toolbar" },
    React.createElement("i", { className: "fas fa-pencil-alt text-[8px]" })
    )
    ),
    !isPopout &&
    React.createElement("div", { className: "ml-1 opacity-0 group-hover/pane:opacity-100 transition-opacity shrink-0" },
    React.createElement("button", {
      onClick: async (e) => {
        e.stopPropagation();
        let sessionData = session;
        if (!sessionData && window.supabase?.auth?.getSession) {
          try {
            const { data } = await window.supabase.auth.getSession();
            sessionData = data?.session || null;
          } catch (err) {}
        }
        const url = new URL(window.location.origin + window.location.pathname);
        url.searchParams.set("popout", "true");
        url.searchParams.set("symbol", symbol);
        url.searchParams.set("tf", tf);
        const currentPlat = platform || (window.detectPlatformType ? window.detectPlatformType(symbol) : (localStorage.getItem("platform") || "mt5"));
        url.searchParams.set("platform", currentPlat);
        if (sessionData && sessionData.access_token) {
          try {
            localStorage.setItem("ql_transfer_session", JSON.stringify(sessionData));
            localStorage.setItem("ql_transfer_access_token", sessionData.access_token);
            setTimeout(() => localStorage.removeItem("ql_transfer_session"), 15000);
            setTimeout(() => localStorage.removeItem("ql_transfer_access_token"), 15000);
          } catch (e) {}
          url.searchParams.set("access_token", sessionData.access_token);
          url.hash = `access_token=${sessionData.access_token}&type=recovery`;
        }
        if (window.pywebview && window.pywebview.api && typeof window.pywebview.api.open_chart_window === 'function') {
          if (sessionData && typeof window.pywebview.api.set_session_data === 'function') {
            try {await window.pywebview.api.set_session_data(JSON.stringify(sessionData));} catch (e) {}
          }
          window.pywebview.api.open_chart_window(url.toString(), `Chart ${symbol} ${tf}`);
        } else {
          window.open(url.toString(), `chart_${symbol}_${tf}_${Date.now()}`, "width=1000,height=700");
        }
      },
      className: "bg-black/40 hover:bg-black/60 text-gray-400 hover:text-accent p-0.5 rounded transition-colors border border-white/5 backdrop-blur-sm flex items-center justify-center w-[18px] h-[16px]",
      title: "Desprender Gráfico (Pop-out)" },
    React.createElement("i", { className: "fas fa-external-link-alt text-[9px]" })
    )
    ),
    React.createElement("div", { className: "ml-auto flex items-center gap-1.5 px-2" },
    isLlamaActive &&
    React.createElement("div", { className: "flex items-center gap-1 bg-accent/20 text-accent text-[8px] px-1.5 py-0.5 rounded border border-accent/40 backdrop-blur-md shadow-[0_0_8px_rgba(var(--accent-rgb),0.15)] animate-pulse h-[16px]" },
    React.createElement("i", { className: "fas fa-microchip text-[7px]" }),
    React.createElement("span", { className: "font-black uppercase tracking-tighter" }, "LLAMA SMART")
    ),
    React.createElement("div", { className: "flex items-center gap-1 bg-black/40 text-white text-[8px] px-1.5 py-0.5 rounded border border-white/5 backdrop-blur-sm hover:bg-black/60 transition-colors h-[16px]" },
    React.createElement("button", {
      className: "hover:text-accent pointer-events-auto flex items-center",
      onClick: (e) => { e.stopPropagation(); onUpdateSettings({ ...chartSettings, overlays: { ...chartSettings.overlays, showVolume: !showVolume } }); },
      title: showVolume ? "Hide Volume" : "Show Volume" },
    React.createElement("i", { className: `fas ${showVolume ? "fa-eye" : "fa-eye-slash"} text-[8px] mr-1` }),
    React.createElement("span", { className: "text-accent font-bold" }, "VOL")
    )
    ),
    React.createElement("div", { className: "flex items-center gap-1 bg-black/40 text-white text-[8px] px-1.5 py-0.5 rounded border border-white/5 backdrop-blur-sm hover:bg-black/60 transition-colors h-[16px]" },
    React.createElement("button", {
      className: "hover:text-accent pointer-events-auto flex items-center",
      onClick: (e) => { e.stopPropagation(); onUpdateSettings({ ...chartSettings, overlays: { ...chartSettings.overlays, showDelta: !showDelta } }); },
      title: showDelta ? "Hide Delta" : "Show Delta" },
    React.createElement("i", { className: `fas ${showDelta ? "fa-eye" : "fa-eye-slash"} text-[8px] mr-1` }),
    React.createElement("span", { className: "text-accent font-bold" }, "DELTA")
    )
    ),
    React.createElement("div", { className: "flex items-center gap-1 bg-black/40 text-white text-[8px] px-1.5 py-0.5 rounded border border-white/5 backdrop-blur-sm hover:bg-black/60 transition-colors h-[16px]" },
    React.createElement("button", {
      className: "hover:text-accent pointer-events-auto flex items-center",
      onClick: (e) => { e.stopPropagation(); onUpdateSettings({ ...chartSettings, overlays: { ...chartSettings.overlays, showAll: !showAllOverlays } }); },
      title: showAllOverlays ? "Hide All Overlays" : "Show All Overlays" },
    React.createElement("i", { className: `fas ${showAllOverlays ? "fa-eye" : "fa-eye-slash"} text-[8px] mr-1 text-accent` }),
    React.createElement("span", { className: "text-accent font-bold" }, "ALL")
    )
    )
    )
    ),
    historicalData &&
    React.createElement(ChartComponent, {
      historicalData: historicalData,
      activeTool: isActive ? localTool : "cursor",
      onToolFinish: handleToolFinish,
      activeSymbol: symbol,
      activeTimeframe: tf,
      systemStatus: systemStatus,
      onOrder: onOrder,
      tickData: tickData,
      showAllOverlays: showAllOverlays,
      showVolume: showVolume,
      showDelta: showDelta,
      onLlamaActiveChange: setIsLlamaActive,
      indicators: indicators,
      globalBigTradesRef: globalBigTradesRef,
      mt5Positions: mt5Positions,
      mt5PendingOrders: mt5PendingOrders,
      setLastCandleTime: setLastCandleTime,
      chartType: chartType,
      chartSettings: chartSettings,
      chartId: chartId,
      platform: platformType,
      marketStatus: session?.marketStatus || systemStatus?.market_session,
      symbolMetadata: symbolMetadata,
      onUpdateSettings: onUpdateSettings,
      volume: volume }
    ),
    (isFetching || !historicalData) && !loadingError &&
    React.createElement("div", {
      className: "absolute inset-0 grid place-items-center animate-in fade-in duration-300",
      style: {
        background: "rgba(255, 255, 255, 0.005)",
        backdropFilter: "blur(1px) saturate(180%)",
        WebkitBackdropFilter: "blur(1px) saturate(180%)",
        border: "1px solid rgba(255, 255, 255, 0.01)",
        zIndex: 100
      }
    },
    React.createElement(QuantumLoader, { message: "SYNCING TERMINAL...", size: "lg" })
    )
    ),
    rightPanels,
    loadingError &&
    React.createElement("div", {
      className: "absolute inset-0 flex items-center justify-center animate-in fade-in duration-300",
      style: {
        background: "rgba(0, 0, 0, 0.4)",
        backdropFilter: "blur(40px) saturate(150%)",
        WebkitBackdropFilter: "blur(40px) saturate(150%)",
        border: "1px solid rgba(251, 191, 36, 0.1)",
        zIndex: 110
      }
    },
    React.createElement("div", { className: "text-center max-w-xs animate-in fade-in zoom-in duration-300" },
    React.createElement("i", { className: "fas fa-info-circle text-2xl text-accent/50 mb-3" }),
    React.createElement("h3", { className: "text-sm font-bold text-white mb-2 uppercase tracking-tight" }, "No Data Available"),
    React.createElement("div", { className: "bg-black/40 border border-white/5 rounded p-3 mb-4 space-y-2" },
    React.createElement("p", { className: "text-[10px] text-muted leading-relaxed" }, "The server could not retrieve data for ",
    React.createElement("span", { className: "text-accent" }, loadingError.symbol), " in ", React.createElement("span", { className: "text-white font-semibold" }, getPlatformDisplayName(loadingError.platform)), " mode."
    )
    ),
    React.createElement("button", {
      onClick: () => { setLoadingError(null); setHistoricalData(null); lastFetchedSymbolRef.current = null; },
      className: "mt-4 w-full py-2 bg-accent/90 hover:bg-accent text-black text-[10px] font-bold rounded transition-transform hover:scale-[1.02] active:scale-[0.98]" },
    React.createElement("i", { className: "fas fa-redo mr-2" }), "RETRY CONNECTION"
    )
    )
    )
    )
    )
    ));
});

const areEqual = (prevProps, nextProps) => {
  return prevProps.symbol === nextProps.symbol &&
         prevProps.tf === nextProps.tf &&
         prevProps.chartId === nextProps.chartId &&
         prevProps.isActive === nextProps.isActive &&
         prevProps.activeTool === nextProps.activeTool &&
         prevProps.refreshKey === nextProps.refreshKey &&
         prevProps.volume === nextProps.volume &&
         prevProps.chartType === nextProps.chartType &&
         prevProps.showAllOverlays === nextProps.showAllOverlays &&
         prevProps.chartSettings === nextProps.chartSettings &&
         prevProps.mt5Positions === nextProps.mt5Positions &&
         prevProps.mt5PendingOrders === nextProps.mt5PendingOrders;
};

window.ChartPane = React.memo(ChartPane, areEqual);