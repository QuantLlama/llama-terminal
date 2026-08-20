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
  const [showWorkspacesModal, setShowWorkspacesModal] = useState(false);
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
        setTickData({
          last: tickPayload.price,
          volume: tickPayload.volume,
          timestamp: tickPayload.timestamp,
          symbol: displaySymbol
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

        // Also dispatch as market_tick so the RAF tick loop (flushTicks) receives the
        // server's authoritative OHLC shape and can update currentCandle.high/low in
        // real time. Without this, the candle only updated its close (from price ticks)
        // but high/low never grew — the candle looked frozen even when price was moving.
        if (msg.close && msg.close > 0) {
          window.dispatchEvent(new CustomEvent('market_tick', {
            detail: {
              symbol: displaySymbol,
              price: msg.close,
              last:  msg.close,
              open:  msg.open  || 0,
              high:  msg.high  || 0,
              low:   msg.low   || 0,
              close: msg.close || 0,
              volume: msg.volume || 0,
              delta: msg.delta,
              timestamp: tsSec,
              side: "",
              eventType: "BAR_TICK",
              source: msg.source || "MT5"
            }
          }));
        }
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
    return () => {
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
  }, [sendWebSocketMessage]);
  const handleAlgoAction = useCallback((action, algo_id = null, params = {}) => {
    sendWebSocketMessage("algo_action", { action, algo_id, params });
  }, [sendWebSocketMessage]);

  const handleSaveWorkspace = async (name) => {
    const currentConfig = window.WorkspaceManager.getCurrentConfig();
    const config = {
      layout: layout,
      symbol: activeSymbol,
      tf: activeTimeframe,
      indicators: indicators,
      panelSizes: {
        left: leftPanelWidth,
        right: rightPanelWidth
      },
      chart_settings: currentConfig.chart_settings
    };
    
    window.dispatchEvent(new CustomEvent('save_status', { detail: 'saving' }));
    const success = await window.WorkspaceManager.saveWorkspace(name, config);
    if (success) {
      window.dispatchEvent(new CustomEvent('save_status', { detail: 'saved' }));
      window.dispatchEvent(new CustomEvent('notify', { 
        detail: { type: 'success', title: 'Éxito', message: `Espacio '${name}' guardado` } 
      }));
    } else {
      window.dispatchEvent(new CustomEvent('save_status', { detail: 'error' }));
    }
  };

  const handleLoadWorkspace = useCallback((name, data) => {
    if (data.symbol) setActiveSymbol(data.symbol);
    if (data.tf) setActiveTimeframe(data.tf);
    if (data.layout) setLayout(data.layout);
    if (data.indicators) {
      setIndicators(data.indicators);
      localStorage.setItem('indicatorSettings', JSON.stringify(data.indicators));
    }
    if (data.panelSizes) {
      if (data.panelSizes.left) setLeftPanelWidth(data.panelSizes.left);
      if (data.panelSizes.right) setRightPanelWidth(data.panelSizes.right);
    }
    if (data.chart_settings) {
      window.WorkspaceManager.applyConfig({ chart_settings: data.chart_settings });
    }
    window.dispatchEvent(new CustomEvent('notify', { 
      detail: { type: 'success', title: 'Cargado', message: `Espacio '${name}' aplicado` } 
    }));
  }, []);

  const { NotificationProvider, useNotification } = Notification;
  return (
    React.createElement(NotificationProvider, null,
    React.createElement("div", { className: "flex flex-col h-screen bg-bg text-text font-sans" },
    React.createElement(Header, {
      connectionStatus: wsConnected,
      systemStatus: systemStatus,
      accountData: accountInfo?.account || accountInfo,
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
      onSaveWorkspace: () => setShowWorkspacesModal(true),
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
      isCumulative: true,
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
      isCumulative: true,
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
    React.createElement(WorkspacesModal, { 
      isOpen: showWorkspacesModal, 
      onClose: () => setShowWorkspacesModal(false),
      onSave: handleSaveWorkspace,
      onLoad: handleLoadWorkspace,
      activeSymbol: activeSymbol
    }),
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
    )
    )
    ));
};
window.App = App;
