const App = () => {
  const { useState, useEffect, useRef, useMemo, useCallback } = React;
  const [activeSymbol, setActiveSymbol] = useState(() => {
    const stored = localStorage.getItem('activeSymbol');
    if (stored === 'MNQ=F' || stored === 'MNQH26') {
      localStorage.removeItem('activeSymbol');
      return 'EURUSD';
    }
    return stored || 'EURUSD';
  });
  const [activeTimeframe, setActiveTimeframe] = useState(localStorage.getItem('activeTimeframe') || '5m');
  const [platform, setPlatform] = useState(localStorage.getItem('platform') || 'mt5');
  const [liveData, setLiveData] = useState(null);
  const [historicalData, setHistoricalData] = useState([]);
  const [tickData, setTickData] = useState(null);
  const [systemStatus, setSystemStatus] = useState(null);
  const [accountInfo, setAccountInfo] = useState(null);
  const [notifications, setNotifications] = useState([]);
  const [activeTool, setActiveTool] = useState('cursor');
  const [showAllOverlays, setShowAllOverlays] = useState(true);
  const [currentView, setCurrentView] = useState('chart');
  const [layout, setLayout] = useState('single');
  const [showAboutModal, setShowAboutModal] = useState(false);
  const [showSymbolSearchModal, setShowSymbolSearchModal] = useState(false);
  const [showDashboardModal, setShowDashboardModal] = useState(false);
  const [showLiveDashboardModal, setShowLiveDashboardModal] = useState(false);
  const [showMappingEditor, setShowMappingEditor] = useState(false);
  const [showWizardModal, setShowWizardModal] = useState(false);
  const [wsConnected, setWsConnected] = useState(false);
  const [leftPanelWidth, setLeftPanelWidth] = useState(300);
  const [rightPanelWidth, setRightPanelWidth] = useState(300);
  const [fastTapeConfig, setFastTapeConfig] = useState({ minSize: 0, maxTrades: 500 });
  const [slowTapeConfig, setSlowTapeConfig] = useState({ minSize: 10, maxTrades: 500 });
  const [showFastTapeConfig, setShowFastTapeConfig] = useState(false);
  const [showSlowTapeConfig, setShowSlowTapeConfig] = useState(false);
  const [indicators, setIndicators] = useState(() => {
    try {
      return JSON.parse(localStorage.getItem('indicatorSettings')) || {
        caza_stop: { enabled: true, settings: {} },
        fourier: { enabled: true, settings: {} },
        big_trade: { enabled: true, settings: { bubbleScale: 1.0, opacity: 0.4, buyColor: '#10b981', sellColor: '#ef4444', textSize: 1.0 } },
        drawings: { enabled: true, settings: {} }
      };
    } catch {
      return {
        drawings: { enabled: true, settings: {} }
      };
    }
  });
  const globalBigTradesRef = useRef([]);
  const [globalQty, setGlobalQty] = useState(() => {
    const saved = localStorage.getItem('orderEntry_qty');
    return parseFloat(saved) || 1;
  });
  const updateGlobalQty = useCallback((newQty) => {
    setGlobalQty(newQty);
    localStorage.setItem('orderEntry_qty', newQty.toString());
  }, []);
  const updateIndicatorSettings = useCallback((key, updates) => {
    setIndicators((prev) => {
      const newSettings = {
        ...prev,
        [key]: { ...prev[key], ...updates }
      };
      localStorage.setItem('indicatorSettings', JSON.stringify(newSettings));
      return newSettings;
    });
  }, []);

  const [isLocked, setIsLocked] = useState(false);
  const [lockCountdown, setLockCountdown] = useState("");
  const [riskConfig, setRiskConfig] = useState({ maxDailyLoss: 500, maxContracts: 1, emotionalGuard: false, lockedUntil: null });

  useEffect(() => {
    const fetchConfig = async () => {
      try {
        const res = await fetch("/api/config");
        if (res.ok) {
          const data = await res.json();
          if (data.risk_max_daily_loss !== undefined) {
            const cfg = {
              maxDailyLoss: data.risk_max_daily_loss,
              maxContracts: data.risk_max_contracts,
              emotionalGuard: data.risk_emotional_guard,
              lockedUntil: data.risk_locked_until
            };
            setRiskConfig(cfg);
            // Initialize lock state from server
            if (cfg.lockedUntil && parseInt(cfg.lockedUntil) > Date.now()) {
              setIsLocked(true);
            }
          }
        }
      } catch (e) {
        console.error("Failed to fetch risk config:", e);
      }
    };
    fetchConfig();
    window.addEventListener("settings_updated", fetchConfig);
    return () => window.removeEventListener("settings_updated", fetchConfig);
  }, []);

  const getNextNYOpen = useCallback(() => {
    const now = new Date();
    // NY 09:30 AM EST
    // Determine if we are in DST
    const y = now.getUTCFullYear();
    const nthWeekday = (year, month, dayOfWeek, n) => {
      const d = new Date(Date.UTC(year, month, 1));
      let count = 0;
      while (d.getUTCMonth() === month) {
        if (d.getUTCDay() === dayOfWeek) {
          count++;
          if (count === n) return d.getTime();
        }
        d.setUTCDate(d.getUTCDate() + 1);
      }
      return d.getTime();
    };
    const start = nthWeekday(y, 2, 0, 2) + 7 * 3600 * 1000;
    const end = nthWeekday(y, 10, 0, 1) + 6 * 3600 * 1000;
    const isUsDst = now.getTime() >= start && now.getTime() < end;
    const nyOffset = isUsDst ? 4 : 5;

    // Create target: tomorrow at 09:30 AM NY time
    const target = new Date(now);
    target.setDate(target.getDate() + 1);
    target.setHours(9, 30, 0, 0);
    
    // Adjust target to UTC based on NY offset
    // Target is 09:30 NY time. UTC = 09:30 + offset
    const targetUtc = new Date(target.getTime() + (nyOffset * 3600 * 1000));
    
    // Correct for local timezone offset if needed? 
    // Actually simpler: 
    // const nyTime = new Date(now.toLocaleString("en-US", {timeZone: "America/New_York"}));
    return targetUtc.getTime();
  }, []);

  useEffect(() => {
    const checkRisk = async () => {
      if (!riskConfig.emotionalGuard) return;

      const realizedPnl = accountInfo?.account?.realized_today || 0;
      const manualLock = localStorage.getItem("platform_manually_locked") === "true";
      const lockedUntil = parseInt(riskConfig.lockedUntil || localStorage.getItem("platform_locked_until") || "0");

      if (lockedUntil > Date.now()) {
        if (!isLocked) setIsLocked(true);
        return;
      }

      if (realizedPnl <= -riskConfig.maxDailyLoss || manualLock) {
        const nextOpen = getNextNYOpen();
        
        // Persist to server
        try {
          await fetch("/api/config", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ risk_locked_until: nextOpen.toString() })
          });
        } catch (e) {
          console.error("Failed to persist lock to server:", e);
        }

        localStorage.setItem("platform_locked_until", nextOpen.toString());
        localStorage.removeItem("platform_manually_locked");
        setRiskConfig(prev => ({ ...prev, lockedUntil: nextOpen.toString() }));
        setIsLocked(true);
        window.dispatchEvent(new CustomEvent('notification', { 
          detail: { type: 'error', title: 'RISK LIMIT REACHED', message: 'Platform locked until next NY session.' } 
        }));
      }
    };

    const interval = setInterval(checkRisk, 5000);
    checkRisk();
    return () => clearInterval(interval);
  }, [accountInfo, getNextNYOpen, riskConfig, isLocked]);

  useEffect(() => {
    if (!isLocked) return;
    const updateCountdown = () => {
      const until = parseInt(riskConfig.lockedUntil || localStorage.getItem("platform_locked_until") || "0");
      const diff = until - Date.now();
      if (diff <= 0) {
        setIsLocked(false);
        localStorage.removeItem("platform_locked_until");
        return;
      }
      const hours = Math.floor(diff / 3600000);
      const mins = Math.floor((diff % 3600000) / 60000);
      const secs = Math.floor((diff % 60000) / 1000);
      setLockCountdown(`${hours}h ${mins}m ${secs}s`);
    };
    const timer = setInterval(updateCountdown, 1000);
    updateCountdown();
    return () => clearInterval(timer);
  }, [isLocked]);
  const ws = useRef(null);
  const feedWs = useRef(null);
  const lastTickUpdateRef = useRef(0);
  useEffect(() => {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    ws.current = new WebSocket(`${protocol}//${window.location.host}/ws`);
    ws.current.onopen = () => {
      
      setWsConnected(true);
    };
    ws.current.onclose = () => {
      
      setWsConnected(false);
    };
    ws.current.onerror = (error) => {}; // console.error("Legacy WebSocket error:", error);
    ws.current.onmessage = (event) => {
      const msg = JSON.parse(event.data);
      
      if (msg.type === "system_status") {
        setSystemStatus(msg.data || msg);
        // Also update account info if present in system_status
        const accData = msg.data?.account || msg.account;
        if (accData) {
          setAccountInfo(msg.data ? { ...msg.data, ...accData } : { ...msg, ...accData });
        }
      } else if (msg.type === "account_info") {
        const accData = msg.data || (msg.account ? msg : null);
        if (accData) setAccountInfo(accData);
      }
    };
    feedWs.current = new WebSocket(`${protocol}//${window.location.host}/api/v2/ws/feed`);
    feedWs.current.onopen = () => {
      // Signal that App.jsx feed WS is handling events (prevents index.html from dispatching duplicates)
      window.__appFeedActive = true;
      
      if (activeSymbol) {
        feedWs.current.send(JSON.stringify({
          action: "subscribe",
          symbols: [activeSymbol]
        }));
      }
    };
    feedWs.current.onclose = () => { window.__appFeedActive = false; }; 
    feedWs.current.onerror = (error) => {}; // console.error("Feed WebSocket error:", error);
    feedWs.current.onmessage = (event) => {
      const msg = JSON.parse(event.data);
      const eventType = msg.event_type || msg.type || "";
      const rawSymbol = msg.symbol || activeSymbol;
      const normalizedSymbol = window.getUniversalSymbol && rawSymbol ?
      window.getUniversalSymbol(rawSymbol, window.detectPlatformType(rawSymbol)) :
      rawSymbol ? rawSymbol.split(':')[0] : activeSymbol;

      if (eventType === "TICK" || eventType === "QUOTE") {
        const ts = msg.timestamp || Date.now() / 1000;
        const tsSec = ts > 1e10 ? ts / 1000 : ts;
        const tickPayload = {
          symbol: normalizedSymbol,
          price: msg.price || msg.last || 0,
          volume: msg.volume || 0,
          size: msg.last_size || 0,
          delta: msg.delta,
          timestamp: tsSec,
          side: msg.side || "",
          eventType: "TICK",
          // Live candle OHLC from server (for real-time candle shaping)
          open: msg.open || 0,
          high: msg.high || 0,
          low: msg.low || 0,
          close: msg.close || msg.last || 0
        };
        window.dispatchEvent(new CustomEvent('market_tick', { detail: tickPayload }));
        if (!window.lastMarketTicks) window.lastMarketTicks = {};
        window.lastMarketTicks[normalizedSymbol] = tickPayload;
        
        // Update tickData state on every tick (no throttle)
        const activeNorm = window.getUniversalSymbol ? window.getUniversalSymbol(activeSymbol, window.detectPlatformType(activeSymbol)) : activeSymbol;
        const incomingNorm = window.getUniversalSymbol ? window.getUniversalSymbol(rawSymbol, window.detectPlatformType(rawSymbol)) : normalizedSymbol;
        const displaySymbol = (activeNorm === incomingNorm) ? activeSymbol : rawSymbol;
        setTickData((prev) => {
          // Anti-Thrashing en la ingesta:
          // Si el precio y el volumen son idénticos, React no necesita re-renderizar
          if (prev && prev.last === tickPayload.price && prev.volume === tickPayload.volume) {
             return prev; 
          }
          return {
            last: tickPayload.price,
            volume: tickPayload.volume,
            timestamp: tickPayload.timestamp,
            symbol: displaySymbol
          };
        });
        
        // For MT5, TICK/QUOTE might be the only things we get for some symbols. If they have size > 0, 
        // we emit TAPE so order flow tape works. For MT5, msg.size is in last_size
        if (msg.source === "MT5" && (msg.last_size > 0)) {
          const tradePayload = {
            symbol: normalizedSymbol,
            price: tickPayload.price,
            size: msg.last_size || 0,
            volume: tickPayload.volume,
            timestamp: tsSec,
            side: tickPayload.side || (tickPayload.delta >= 0 ? "buy" : "sell"),
            eventType: "TAPE",
            source: msg.source || "MT5"
          };
          window.dispatchEvent(new CustomEvent('market_tick', { detail: tradePayload }));
        }

      } else if (eventType === "TRADE") {
        const ts = msg.timestamp || Date.now() / 1000;
        const tsSec = ts > 1e10 ? ts / 1000 : ts;
        
        // FIX: NEVER SKIP TRADE EVENTS for crypto!!
        // The tape relies on these for individual trades. ChartComponent also uses them for real incremental volume.
        const tradePayload = {
          symbol: rawSymbol || normalizedSymbol,
          price: msg.price || msg.last || 0,
          size: msg.size || msg.amount || msg.last_size || 0,
          volume: msg.volume || 0,
          timestamp: tsSec,
          side: msg.side || "",
          eventType: "TAPE",  // Map TRADE to TAPE for the frontend tape and charting
          source: msg.source || "UNKNOWN"
        };
        window.dispatchEvent(new CustomEvent('market_tick', { detail: tradePayload }));
      } else if (eventType === "BAR" || eventType === "OHLCV") {
        const ts = msg.timestamp || Date.now() / 1000;
        const tsSec = ts > 1e10 ? ts / 1000 : ts;
        
        // Normalize both for comparison
        const activeNorm = window.getUniversalSymbol ? window.getUniversalSymbol(activeSymbol, window.detectPlatformType(activeSymbol)) : activeSymbol;
        const incomingNorm = window.getUniversalSymbol ? window.getUniversalSymbol(rawSymbol, window.detectPlatformType(rawSymbol)) : normalizedSymbol;
        const displaySymbol = (activeNorm === incomingNorm) ? activeSymbol : rawSymbol;

        setLiveData({
          time: tsSec,
          Open: msg.open,
          High: msg.high,
          Low: msg.low,
          Close: msg.close,
          Volume: msg.volume,
          delta: msg.delta,
          symbol: displaySymbol
        });
      } else if (eventType === "BOOK" || eventType === "BOOK_UPDATE") {
        window.dispatchEvent(new CustomEvent('market_dom', {
          detail: {
            symbol: normalizedSymbol,
            bids: msg.bids || [],
            asks: msg.asks || [],
            timestamp: msg.timestamp
          }
        }));
      } else if (eventType === "LLAMA_UPDATE") {
        const btData = {
          symbol: msg.symbol,
          ...msg.params,
          timestamp: msg.timestamp,
          bt_type: 'real'
        };
        window.dispatchEvent(new CustomEvent('market_big_trade', { detail: btData }));
      }
    };

    const handlePlatformChange = (e) => {
      setPlatform(e.detail.newPlatform);
      localStorage.setItem('platform', e.detail.newPlatform);
    };
    window.addEventListener('platform_changed', handlePlatformChange);

    return () => {
      window.removeEventListener('platform_changed', handlePlatformChange);
      if (ws.current && ws.current.readyState === WebSocket.OPEN) ws.current.close();
      if (feedWs.current && feedWs.current.readyState === WebSocket.OPEN) feedWs.current.close();
    };
  }, []);
  const sendWebSocketMessage = useCallback((type, payload) => {
    if (ws.current && ws.current.readyState === WebSocket.OPEN) {
      ws.current.send(JSON.stringify({ type, payload }));
    } else {
      console.warn("WebSocket is not open. Message not sent:", { type, payload });
    }
  }, []);
  useEffect(() => {
    if (activeSymbol && activeTimeframe) {
      const fetchHistoricalData = async () => {
        try {
          // Get limit from settings
          let limit = 500;
          try {
            const storedLimits = JSON.parse(localStorage.getItem('chart_history_limits') || '{}');
            limit = storedLimits[activeTimeframe] || 3000;
          } catch (e) {
            limit = 3000;
          }

          const response = await fetch(`/api/history?symbol=${activeSymbol}&timeframe=${activeTimeframe}&limit=${limit}`);
          const data = await response.json();
          
          if (data && Array.isArray(data)) {
            setHistoricalData(data);
          }
        } catch (error) {
          console.error("Error fetching historical data:", error);
        }
      };
      fetchHistoricalData();
      if (feedWs.current && feedWs.current.readyState === WebSocket.OPEN) {
        feedWs.current.send(JSON.stringify({
          action: "subscribe",
          symbols: [activeSymbol]
        }));
        
      } else if (feedWs.current && feedWs.current.readyState === WebSocket.CONNECTING) {
        
      }
      localStorage.setItem('activeSymbol', activeSymbol);
      localStorage.setItem('activeTimeframe', activeTimeframe);
    }
  }, [activeSymbol, activeTimeframe]);
  useEffect(() => {
    if (wsConnected) {
      sendWebSocketMessage("request_system_status", {});
      sendWebSocketMessage("request_account_info", {});
    }
  }, [wsConnected, sendWebSocketMessage]);
  const handleOrder = useCallback((type, symbol, price, volume = 1, orderType = 'LIMIT', stopLoss = 0, takeProfit = 0) => {
    if (isLocked) {
      window.dispatchEvent(new CustomEvent('notification', { 
        detail: { type: 'error', title: 'PLATFORM LOCKED', message: 'Trading is disabled by Emotional Guard.' } 
      }));
      return;
    }

    if (volume > riskConfig.maxContracts) {
      window.dispatchEvent(new CustomEvent('notification', { 
        detail: { type: 'error', title: 'MAX CONTRACTS EXCEEDED', message: `Your limit is ${riskConfig.maxContracts} contract(s).` } 
      }));
      return;
    }

    const orderPayload = {
      symbol,
      type,
      price,
      volume,
      order_type: orderType,
      stop_loss: stopLoss,
      take_profit: takeProfit
    };
    sendWebSocketMessage("place_order", orderPayload);
  }, [sendWebSocketMessage, isLocked, riskConfig]);
  const handleAlgoAction = useCallback((action, algo_id = null, params = {}) => {
    if (isLocked && action === "start") {
      window.dispatchEvent(new CustomEvent('notification', { 
        detail: { type: 'error', title: 'PLATFORM LOCKED', message: 'Algo execution is disabled by Emotional Guard.' } 
      }));
      return;
    }
    sendWebSocketMessage("algo_action", { action, algo_id, params });
  }, [sendWebSocketMessage, isLocked]);
  const { NotificationProvider, useNotification } = Notification;
  return (
    React.createElement(NotificationProvider, null,
    React.createElement("div", { className: "flex flex-col h-screen bg-bg text-text font-sans" },
    React.createElement(Header, {
      connectionStatus: wsConnected,
      systemStatus: systemStatus,
      accountData: accountInfo?.account || accountInfo,
      platform: platform,
      realizedDailyPnl: accountInfo?.account?.realized_today || 0,
      activeSymbol: activeSymbol,
      activeTF: activeTimeframe,
      onSymbolChange: setActiveSymbol,
      onTFChange: setActiveTimeframe,
      onOpenSettings: () => {},
      onOpenSymbolSearch: () => setShowSymbolSearchModal(true),
      currentView: currentView,
      onViewChange: setCurrentView,
      showTape: true,
      toggleTape: () => {},
      showOrderEntry: true,
      toggleOrderEntry: () => {},
      onSaveWorkspace: () => {},
      layout: layout,
      onLayoutChange: setLayout }
    ),
    currentView === 'chart' ?
    React.createElement("div", { className: "flex flex-1 overflow-hidden" },
    React.createElement(ResizablePanel, {
      width: leftPanelWidth,
      onResize: setLeftPanelWidth,
      minWidth: 200,
      maxWidth: 500,
      side: "right" },
    React.createElement("div", { className: "flex flex-col h-full bg-panel border-r border-border shadow-lg" },
    React.createElement("div", { className: "relative flex-1 min-h-0" },
    React.createElement("div", { className: "absolute top-2 right-2 z-10" },
    React.createElement("button", {
      onClick: () => setShowFastTapeConfig(true),
      className: "p-1.5 text-xs text-muted hover:text-accent hover:bg-black/50 rounded transition-colors",
      title: "Configure Fast Tape" },
    React.createElement("i", { className: "fas fa-cog" })
    )
    ),
    React.createElement(TapePanel, {
      symbol: activeSymbol,
      lastPrice: tickData?.last,
      volume: tickData?.volume,
      timestamp: tickData?.timestamp,
      title: "Time & Sales (Fast)",
      minSize: fastTapeConfig.minSize,
      height: "h-full" }
    )
    ),
    React.createElement("div", { className: "relative flex-1 min-h-0 border-t border-border" },
    React.createElement("div", { className: "absolute top-2 right-2 z-10" },
    React.createElement("button", {
      onClick: () => setShowSlowTapeConfig(true),
      className: "p-1.5 text-xs text-muted hover:text-accent hover:bg-black/50 rounded transition-colors",
      title: "Configure Slow Tape" },
    React.createElement("i", { className: "fas fa-cog" })
    )
    ),
    React.createElement(TapePanel, {
      symbol: activeSymbol,
      lastPrice: tickData?.last,
      volume: tickData?.volume,
      timestamp: tickData?.timestamp,
      title: "Time & Sales (Slow)",
      minSize: slowTapeConfig.minSize,
      height: "h-full" }
    )
    ),
    React.createElement(VixCorrelationPanel, {
      activeSymbol: activeSymbol,
      currentPrice: tickData?.last || 0,
      activeTimeframe: activeTimeframe,
      globalBigTrades: globalBigTradesRef.current }
    )
    )
    ),
    React.createElement("div", { className: "flex-1 flex flex-col" },
    React.createElement(ChartComponent, {
      key: `${activeSymbol}-${activeTimeframe}-${platform}`,
      liveData: liveData,
      historicalData: historicalData,
      tickData: tickData,
      activeTool: activeTool,
      activeSymbol: activeSymbol,
      activeTimeframe: activeTimeframe,
      systemStatus: systemStatus,
      onOrder: handleOrder,
      volume: globalQty,
      showAllOverlays: showAllOverlays,
      setShowAllOverlays: setShowAllOverlays,
      indicators: indicators,
      isLocked: isLocked,
      onUpdateSettings: (newSettings) => updateIndicatorSettings('layout', newSettings),
      globalBigTradesRef: globalBigTradesRef }
    )
    ),
    React.createElement(ResizablePanel, {
      width: rightPanelWidth,
      onResize: setRightPanelWidth,
      minWidth: 200,
      maxWidth: 500,
      side: "left" },
    React.createElement("div", { className: "flex flex-col h-full bg-panel border-l border-border shadow-lg" },
    React.createElement(OrderEntry, {
      systemStatus: systemStatus,
      config: { volume: globalQty, stop_loss_points: 20, take_profit_points: 40 },
      onOrder: handleOrder,
      onVolumeChange: updateGlobalQty,
      symbol: activeSymbol,
      tickData: tickData,
      isLocked: isLocked,
      mt5Positions: [],
      oneClick: false,
      setOneClick: () => {} }
    ),
    React.createElement(OrderFlowStats, {
      symbol: activeSymbol,
      lastPrice: tickData?.last,
      volume: tickData?.volume }
    ),
    React.createElement(HistoryPanel, null)
    )
    )
    ) :
    currentView === 'algo' ?
    React.createElement("div", { className: "flex flex-1 overflow-hidden items-center justify-center" },
    React.createElement(AlgoPanel, {
      systemStatus: systemStatus,
      handleAlgoAction: handleAlgoAction,
      isLocked: isLocked,
      activeSymbol: activeSymbol }
    )
    ) :
    currentView === 'backtest' ?
    React.createElement(BacktestPanel, {
      activeSymbol: activeSymbol,
      systemStatus: systemStatus }
    ) :
    React.createElement(AlgoLab, { isOpen: currentView === 'editor' }),
    React.createElement(Footer, { systemStatus: systemStatus }),
    React.createElement(AboutModal, { isOpen: showAboutModal, onClose: () => setShowAboutModal(false) }),
    React.createElement(SymbolSearchModal, { isOpen: showSymbolSearchModal, onClose: () => setShowSymbolSearchModal(false), onSelect: setActiveSymbol, currentPlatform: "mt5" }),
    React.createElement(DashboardModal, { isOpen: showDashboardModal, onClose: () => setShowDashboardModal(false) }),
    React.createElement(LiveDashboardModal, { isOpen: showLiveDashboardModal, onClose: () => setShowLiveDashboardModal(false) }),
    React.createElement(MappingEditor, { isOpen: showMappingEditor, onClose: () => setShowMappingEditor(false) }),
    React.createElement(TapeConfigModal, {
      isOpen: showFastTapeConfig,
      onClose: () => setShowFastTapeConfig(false),
      config: fastTapeConfig,
      onSave: setFastTapeConfig,
      title: "Fast Tape Configuration" }
    ),
    React.createElement(TapeConfigModal, {
      isOpen: showSlowTapeConfig,
      onClose: () => setShowSlowTapeConfig(false),
      config: slowTapeConfig,
      onSave: setSlowTapeConfig,
      title: "Slow Tape Configuration" }
    ),
    React.createElement(WizardModal, {
      isOpen: showWizardModal,
      onClose: () => setShowWizardModal(false),
      title: "Quick Start Wizard",
      steps: [
      {
        label: "Welcome to Quantum Llama",
        render: (data, setData) =>
        React.createElement("div", { className: "text-center space-y-4" },
        React.createElement("p", { className: "text-muted" }, "This wizard will help you set up your trading terminal."),
        React.createElement("p", { className: "text-lg font-bold text-accent" }, "Let's get started!")
        )
      },
      {
        label: "Choose your Symbol",
        render: (data, setData) =>
        React.createElement("div", { className: "space-y-4" },
        React.createElement("p", { className: "text-muted" }, "What symbol do you want to trade?"),
        React.createElement("input", {
          type: "text",
          className: "input-dark w-full text-left",
          placeholder: "e.g. MNQ=F, EURUSD",
          value: data.symbol || '',
          onChange: (e) => setData('symbol', e.target.value) }
        )
        )
      },
      {
        label: "Select Timeframe",
        render: (data, setData) =>
        React.createElement("div", { className: "space-y-4" },
        React.createElement("p", { className: "text-muted" }, "Which timeframe is best for your strategy?"),
        React.createElement("select", {
          value: data.timeframe || '5m',
          onChange: (e) => setData('timeframe', e.target.value) },
        React.createElement("option", { value: "1m" }, "1 Minute"),
        React.createElement("option", { value: "5m" }, "5 Minutes"),
        React.createElement("option", { value: "10m" }, "10 Minutes"),
        React.createElement("option", { value: "15m" }, "15 Minutes"),
        React.createElement("option", { value: "1h" }, "1 Hour"),
        React.createElement("option", { value: "4h" }, "4 Hours"),
        React.createElement("option", { value: "1d" }, "1 Day")
        )
        )
      },
      {
        label: "Confirm Setup",
        render: (data, setData) =>
        React.createElement("div", { className: "space-y-4" },
        React.createElement("p", { className: "text-muted" }, "You are about to start trading with:"),
        React.createElement("p", { className: "text-xl font-bold text-white" }, data.symbol || 'N/A'),
        React.createElement("p", { className: "text-lg text-accent" }, data.timeframe || 'N/A'),
        React.createElement("p", { className: "text-sm text-gray-500" }, "Click 'FINISH & RUN' to apply settings.")
        )
      }],
      onComplete: (data) => {
        if (data.symbol) setActiveSymbol(data.symbol);
        if (data.timeframe) setActiveTimeframe(data.timeframe);
      } }
    ),
    isLocked && React.createElement("div", { className: "fixed bottom-20 left-1/2 -translate-x-1/2 z-[99999] pointer-events-none animate-in slide-in-from-bottom-10 duration-700" },
      React.createElement("div", { className: "px-6 py-4 bg-zinc-900/90 backdrop-blur-md border border-red-500/30 rounded-2xl shadow-[0_20px_50px_rgba(0,0,0,0.5)] flex items-center gap-6 pointer-events-auto" },
        React.createElement("div", { className: "w-10 h-10 bg-red-500/10 rounded-full flex items-center justify-center border border-red-500/20" },
          React.createElement("i", { className: "fas fa-shield-alt text-red-500" })
        ),
        React.createElement("div", { className: "text-left" },
          React.createElement("h2", { className: "text-xs font-black text-white uppercase tracking-widest leading-none mb-1" }, "Trading Locked"),
          React.createElement("p", { className: "text-[10px] text-zinc-500 font-bold uppercase tracking-tighter" }, "Risk limit reached. Analysis mode only.")
        ),
        React.createElement("div", { className: "h-8 w-px bg-white/10" }),
        React.createElement("div", { className: "text-center" },
          React.createElement("p", { className: "text-[8px] text-zinc-500 font-black uppercase tracking-widest mb-0.5" }, "Next NY Session"),
          React.createElement("p", { className: "text-sm font-mono font-black text-orange-500 tabular-nums" }, lockCountdown)
        )
      )
    )
    )
    ));
};
window.App = App;
