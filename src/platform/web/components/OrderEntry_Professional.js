const OrderEntry_Professional = (props) => {
  const {
    systemStatus,
    config,
    onOrder,
    symbol,
    tickData,
    mt5Positions,
    mt5PendingOrders = [],
    oneClick,
    setOneClick,
    indicators,
    onSymbolChange,
    availableAccounts = [],
    symbolMetadata,
    volume,
    onVolumeChange
  } = props;
  
  const accountBalance = props.accountBalance;

  const { useState, useEffect, useRef } = React;
  const lastSpreadRef = useRef("0.0");
  const NumInput = window.NumInput;
  const [activeTab, setActiveTab] = useState("trade");
  const [orderType, setOrderType] = useState("MKT");
  const [qty, setQty] = useState(() => volume || config?.volume || 1);
  useEffect(() => {
    if (volume !== undefined && volume !== qty) {
      setQty(volume);
    }
  }, [volume]);
  const [sl, setSl] = useState(() => {
    const saved = localStorage.getItem("orderEntry_sl");
    const parsed = parseFloat(saved);
    return !isNaN(parsed) ? parsed : 20;
  });
  const [tp, setTp] = useState(() => {
    const saved = localStorage.getItem("orderEntry_tp");
    const parsed = parseFloat(saved);
    return !isNaN(parsed) ? parsed : 40;
  });
  const [limitPrice, setLimitPrice] = useState(0);
  const [leverage, setLeverage] = window.useConfig(
    "leverage",
    10,
    "crypto"
  );
  const [selectedAccountId, setSelectedAccountId] = useState("");
  const manualAccountChange = useRef(false);
  const prevOrderType = useRef(orderType);
  useEffect(() => {
    if (
    orderType !== "MKT" &&
    prevOrderType.current === "MKT")
    {
      const price =
      tickData?.last ||
      systemStatus?.current_price ||
      0;
      if (price > 0 && (!limitPrice || limitPrice === 0)) {
        setLimitPrice(price);
      }
    }
    prevOrderType.current = orderType;
  }, [orderType, tickData, systemStatus, limitPrice]);
  const currentSymbolPlatform = window.detectPlatformType(symbol);
  useEffect(() => {
    if (availableAccounts.length === 0) return;
    if (manualAccountChange.current) {
      manualAccountChange.current = false;
      return;
    }
    const platformAccounts = availableAccounts.filter(
      (a) => a.platform === currentSymbolPlatform
    );
    const currentSelectedAccount = availableAccounts.find((a) => a.id === selectedAccountId);
    if (platformAccounts.length > 0) {
      if (!currentSelectedAccount || currentSelectedAccount.platform !== currentSymbolPlatform) {
        const master = platformAccounts.find((a) => a.is_master);
        const newId = master ? master.id : platformAccounts[0].id;
        if (newId !== selectedAccountId) {
          // console.log(`[ORDERENTRY] Auto-selecting account for ${currentSymbolPlatform}: ${newId}`);
          setSelectedAccountId(newId);
        }
      }
    } else if (!selectedAccountId) {
      setSelectedAccountId(availableAccounts[0].id);
    }
  }, [availableAccounts, currentSymbolPlatform]);
  useEffect(() => {
    if (!isNaN(sl)) {
      localStorage.setItem("orderEntry_sl", sl.toString());
    }
  }, [sl]);
  useEffect(() => {
    if (!isNaN(tp)) {
      localStorage.setItem("orderEntry_tp", tp.toString());
    }
  }, [tp]);
  const currentPlatform = window.detectPlatformType();
  const platformConfig = window.getPlatformConfig(currentPlatform);
  const qtyStep = symbolMetadata && symbolMetadata.volume_step ?
  symbolMetadata.volume_step :
  Math.pow(10, -platformConfig.volumeDecimals);
  const priceStep = symbolMetadata && symbolMetadata.tick_size ?
  symbolMetadata.tick_size :
  window.getSymbolPrecision ?
  window.getSymbolPrecision(symbol, currentPlatform).tick_size :
  currentPlatform === "mt5" || currentPlatform === "tradovate" ? 0.01 : 0.00001;
  const orderSizeRules = symbolMetadata?.order_size_rules || {};
  const minOrderSize = Number(orderSizeRules.min_amount || 0);
  const maxOrderSize = Number(orderSizeRules.max_amount || 0);
  const sizeStep = Number(orderSizeRules.step || qtyStep || 0);
  const contractSize = Number(orderSizeRules.contract_size || 1);
  const [atmEnabled, setAtmEnabled] = window.useConfig(
    "atm_enabled",
    false,
    "atm"
  );
  const [atmStrategy, setAtmStrategy] = window.useConfig(
    "atm_strategy",
    "conservative",
    "atm"
  );
  const [atmParams, setAtmParams] = window.useConfig(
    "atm_params",
    {
      entrySize: 1,
      scaleInLevels: 2,
      scaleInDistance: 50,
      scaleOutLevels: 3,
      profitTarget1: 50,
      profitTarget2: 100,
      profitTarget3: 150,
      trailingStop: 30,
      breakEvenDistance: 40,
      breakEvenOffset: 2,
      maxDrawdown: 100,
      riskPerTrade: 2
    },
    "atm"
  );
  const [atmStatus, setAtmStatus] = useState("idle");
  const [atmLog, setAtmLog] = useState([]);
  const atmIntervalRef = useRef(null);
  const getDefaultATMParams = (strategy) => {
    const defaults = {
      conservative: {
        entrySize: 1,
        scaleInLevels: 1,
        scaleInDistance: 50,
        scaleOutLevels: 2,
        initialStopLoss: 30,
        profitTarget1: 40,
        profitTarget2: 80,
        profitTarget3: 0,
        profitTarget4: 0,
        profitTarget5: 0,
        trailingStop: 40,
        breakEvenDistance: 50,
        breakEvenOffset: 2,
        maxDrawdown: 100,
        riskPerTrade: 2
      },
      aggressive: {
        entrySize: 2,
        scaleInLevels: 2,
        scaleInDistance: 30,
        scaleOutLevels: 4,
        initialStopLoss: 25,
        profitTarget1: 25,
        profitTarget2: 50,
        profitTarget3: 75,
        profitTarget4: 120,
        profitTarget5: 0,
        trailingStop: 20,
        breakEvenDistance: 30,
        breakEvenOffset: 1,
        maxDrawdown: 150,
        riskPerTrade: 5
      },
      scalper: {
        entrySize: 1,
        scaleInLevels: 1,
        scaleInDistance: 10,
        scaleOutLevels: 1,
        initialStopLoss: 10,
        profitTarget1: 15,
        profitTarget2: 0,
        profitTarget3: 0,
        profitTarget4: 0,
        profitTarget5: 0,
        trailingStop: 5,
        breakEvenDistance: 10,
        breakEvenOffset: 0,
        maxDrawdown: 50,
        riskPerTrade: 1
      },
      custom: atmParams || {}
    };
    return defaults[strategy] || defaults.conservative;
  };
  const addATMLog = (message) => {
    const timestamp = new Date().toLocaleTimeString();
    setAtmLog((prev) => [
    ...prev.slice(-9),
    `[${timestamp}] ${message}`]
    );
  };
  useEffect(() => {
    if (
    !atmEnabled ||
    !mt5Positions ||
    mt5Positions.length === 0)
    {
      if (atmIntervalRef.current) {
        clearInterval(atmIntervalRef.current);
        atmIntervalRef.current = null;
      }
      setAtmStatus("idle");
      return;
    }
    setAtmStatus("monitoring");
    atmIntervalRef.current = setInterval(() => {
      if (mt5Positions.length === 0) {
        setAtmStatus("idle");
        return;
      }
      const position = mt5Positions[0];
      const currentPrice = tickData?.last || 0;
      const entryPrice = position.entry_price || 0;
      if (currentPrice <= 0 || entryPrice <= 0) return;
      const distance = position.type === "BUY" ?
      currentPrice - entryPrice :
      entryPrice - currentPrice;
      const beDist = atmParams.breakEvenDistance || 0;
      const beOffset = atmParams.breakEvenOffset || 0;
      const currentSL = position.sl || 0;
      const isBESet = position.type === "BUY" ?
      currentSL >= entryPrice :
      currentSL <= entryPrice && currentSL > 0;
      if (beDist > 0 && distance >= beDist && !isBESet) {
        const targetSL = position.type === "BUY" ?
        entryPrice + beOffset :
        entryPrice - beOffset;
        addATMLog(`ATM: Triggering Break-Even at ${distance.toFixed(2)} pts. Moving SL to ${targetSL.toFixed(2)}`);
        onOrder(
          "MODIFY",
          position.volume,
          targetSL,
          position.tp,
          "MKT",
          0,
          position.ticket,
          selectedAccountId,
          currentSymbolPlatform
        );
      }
      const profitTargets = [
      atmParams.profitTarget1,
      atmParams.profitTarget2,
      atmParams.profitTarget3,
      atmParams.profitTarget4,
      atmParams.profitTarget5].
      filter((t) => t > 0);
      for (let i = 0; i < profitTargets.length; i++) {
        const target = profitTargets[i];
        if (target > 0 && distance >= target && position.volume > 0) {
          const totalLevels = atmParams.scaleOutLevels || 1;
          const scaleOutQty = Math.max(qtyStep, position.volume / (totalLevels - i));
          if (scaleOutQty > 0 && scaleOutQty <= position.volume) {
            setAtmStatus("scaling");
            addATMLog(`ATM: Target ${i + 1} hit (${distance.toFixed(2)} pts). Partial Close: ${scaleOutQty.toFixed(2)}`);
            onOrder(
              "CLOSE",
              scaleOutQty,
              0,
              0,
              "MKT",
              0,
              position.ticket,
              selectedAccountId,
              currentSymbolPlatform
            );
            break;
          }
        }
      }
      const trailDist = atmParams.trailingStop || 0;
      if (trailDist > 0 && distance > trailDist) {
        const newTrailSL = position.type === "BUY" ?
        currentPrice - trailDist :
        currentPrice + trailDist;
        const shouldMove = position.type === "BUY" ?
        newTrailSL > currentSL :
        currentSL === 0 || newTrailSL < currentSL;
        if (shouldMove) {
          addATMLog(`ATM: Trailing SL to ${newTrailSL.toFixed(2)}`);
          onOrder(
            "MODIFY",
            position.volume,
            newTrailSL,
            position.tp,
            "MKT",
            0,
            position.ticket,
            selectedAccountId,
            currentSymbolPlatform
          );
        }
      }
      const pnlValue = position.profit || 0;
      if (pnlValue <= -atmParams.maxDrawdown && position.volume > 0) {
        setAtmStatus("closing");
        addATMLog(`⚠️ ATM: Max drawdown reached: ${pnlValue.toFixed(2)}. Closing all.`);
        onOrder("CLOSE", position.volume, 0, 0, "MKT", 0, position.ticket, selectedAccountId, currentSymbolPlatform);
      }
    }, 1000);
    return () => {
      if (atmIntervalRef.current) {
        clearInterval(atmIntervalRef.current);
        atmIntervalRef.current = null;
      }
    };
  }, [atmEnabled, mt5Positions, tickData, atmParams, onOrder]);
  const { addNotification } = window.useNotification();
  const handleSetLeverage = async () => {
    try {
      const response = await fetch(`/api/accounts/${selectedAccountId}/leverage?platform=crypto`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          symbol,
          leverage: parseInt(leverage || 1)
        })
      });
      
      let data = {};
      try {
        data = await response.json();
      } catch (e) {
        data = { detail: await response.text() };
      }

      if (response.ok) {
        addNotification(
          "success",
          "Leverage Set",
          `Leverage updated to ${leverage || 1}x for ${window.cleanSymbol(symbol)}`
        );
      } else {
        addNotification(
          "error",
          "Leverage Failed",
          data.detail || data.error || "Error setting leverage"
        );
      }
    } catch (error) {
      addNotification(
        "error",
        "Connection Error",
        error.message
      );
    }
  };
  const toggleOneClick = () => {
    const newVal = !oneClick;
    setOneClick(newVal);
    localStorage.setItem("oneClickTrading", newVal);
    if (newVal)
    addNotification("info", "One-Click Trading", "Enabled");else
    addNotification(
      "info",
      "One-Click Trading",
      "Disabled"
    );
  };
  const handleOrderClick = (action) => {
    let finalPrice = limitPrice;
    if (orderType !== "MKT" && (!finalPrice || finalPrice === 0)) {
      finalPrice =
      tickData?.last ||
      systemStatus?.current_price ||
      0;
    }
    let finalSl = sl;
    let finalTp = tp;
    let finalQty = qty;
    if (atmEnabled) {
      finalQty = atmParams.entrySize || qty;
      finalSl = atmParams.initialStopLoss || sl;
      finalTp = atmParams.profitTarget1 || tp;
      // console.log(`[ATM-EXEC] Applying ATM Parameters: Qty=${finalQty}, SL=${finalSl}, TP=${finalTp}`);
    }
    onOrder(
      action,
      finalQty,
      finalSl,
      finalTp,
      orderType,
      finalPrice,
      0,
      selectedAccountId,
      currentSymbolPlatform
    );
  };
  const isAlgoActive = (() => {
    if (!systemStatus) return false;
    const hasSignalData =
    systemStatus.signal !== undefined ||
    systemStatus.ticker !== undefined;
    if (systemStatus.timestamp) {
      try {
        const statusTime = new Date(
          systemStatus.timestamp
        ).getTime();
        const ageSeconds = (Date.now() - statusTime) / 1000;
        if (ageSeconds > 15) return false;
      } catch (e) {}
    }
    return (
      hasSignalData ||
      systemStatus.status === "active" ||
      systemStatus.status === "running" ||
      systemStatus.trading_mode === "ALGO");
  })();
  const signal = isAlgoActive ?
  systemStatus?.signal || "HOLD" :
  "OFF";
  const signalColor = !isAlgoActive ?
  "bg-gradient-to-r from-gray-800 to-gray-700 border-gray-600" :
  signal === "BUY" ?
  "bg-gradient-to-r from-green-900 to-green-600 border-green-500" :
  signal === "SELL" ?
  "bg-gradient-to-r from-red-900 to-red-600 border-red-500" :
  "bg-gray-800 border-gray-600";
  const glow = !isAlgoActive ?
  "" :
  signal === "BUY" ?
  "shadow-[0_0_20px_rgba(22,163,74,0.3)]" :
  signal === "SELL" ?
  "shadow-[0_0_20px_rgba(220,38,38,0.3)]" :
  "";
  const historyView = React.useMemo(() => {
    const Panel = window.HistoryPanel;
    if (!Panel) return React.createElement("div", { className: "p-8 text-center text-white/20" }, "History Panel Loading...");
    
    const selectedAccount = availableAccounts.find(a => a.id === selectedAccountId);
    const balance = accountBalance !== undefined ? accountBalance : (selectedAccount ? selectedAccount.balance : 0);
    
    return (
      React.createElement("div", { className: "flex-1 flex flex-col min-h-0 overflow-hidden" },
      React.createElement("div", { className: "px-3 py-2 border-b border-white/5 flex justify-end shrink-0 bg-black/40" },
      React.createElement("button", {
        onClick: () => {
          const event = new CustomEvent("openHistoryModal", {
            detail: { symbol }
          });
          window.dispatchEvent(event);
        },
        className: "px-3 py-1 bg-accent/10 text-accent hover:bg-accent/20 rounded text-[10px] font-bold transition-all flex items-center gap-2 border border-accent/20" },
      React.createElement("i", { className: "fas fa-expand" }), "EXPAND VIEW"
      )
      ),
      React.createElement("div", { className: "flex-1 min-h-0 bg-black overflow-hidden" },
      React.createElement(Panel, { 
        activeSymbol: symbol,
        accountBalance: balance,
        platform: selectedAccount ? selectedAccount.platform : "mt5"
      })
      )
      ));
  }, [symbol, availableAccounts, selectedAccountId, accountBalance]);
  return (
    React.createElement("div", { className: "w-full h-full bg-[#0d0d0d] border-l border-white/5 flex flex-col z-20 text-white select-none overflow-x-hidden" },
    React.createElement("div", { className: "px-4 py-3 border-b border-white/5 bg-gradient-to-b from-white/[0.02] to-transparent shrink-0" },
    React.createElement("div", { className: "flex justify-between items-center" },
    React.createElement("div", { className: "flex flex-col" },
    React.createElement("div", { className: "flex items-center gap-2 mb-0.5" },
    React.createElement("span", { className: "text-[10px] font-bold text-accent uppercase tracking-widest opacity-80" }, "Terminal"
    ),
    React.createElement("span", { className: "w-1 h-1 rounded-full bg-white/20" }),
    React.createElement("span", { className: "text-[10px] font-medium text-muted uppercase tracking-wider" },
    activeTab
    )
    ),
    React.createElement("h3", { className: "text-sm font-black tracking-tight flex items-center gap-2" },
    window.cleanSymbol(symbol),
    React.createElement("span", { className: "px-1.5 py-0.5 rounded bg-accent/10 text-accent text-[8px] font-mono border border-accent/20" },
    currentPlatform.toUpperCase()
    )
    )
    ),
    React.createElement("div", { className: "flex flex-col items-end" },
    React.createElement("div", { className: "flex items-center gap-1.5 mb-0.5" },
    React.createElement("div", { className: "w-1.5 h-1.5 rounded-full bg-green-500 shadow-[0_0_8px_rgba(34,197,94,0.5)]" }),
    React.createElement("span", { className: "text-[9px] font-bold text-muted font-mono tracking-tighter" }, "CONNECTED"
    )
    ),
    React.createElement("span", { className: "text-[10px] font-mono text-white/40 leading-none" },
    window.formatPrice(
      tickData?.last ||
      systemStatus?.current_price ||
      0
    )
    )
    )
    ),
    React.createElement("div", { className: "flex bg-white/[0.03] rounded-lg p-1 mt-3 border border-white/5" },
    ["trade", "atm", "history"].map((t) =>
    React.createElement("button", {
      key: t,
      onClick: () => setActiveTab(t),
      className: `flex-1 py-1.5 px-2 text-[10px] font-bold uppercase tracking-wider rounded-md transition-all duration-200 ${activeTab === t ? "bg-accent/20 text-accent shadow-sm border border-accent/10" : "text-muted hover:text-white hover:bg-white/5"}` },
    t
    )
    )
    )
    ),
    activeTab === "history" ?
    historyView :
    activeTab === "atm" ?
    React.createElement("div", { className: "flex-1 flex flex-col overflow-hidden" },
    React.createElement("div", { className: "px-4 py-3 border-b border-white/5 bg-white/[0.01]" },
    React.createElement("div", { className: "flex items-center justify-between mb-3" },
    React.createElement("div", null,
    React.createElement("span", { className: "font-bold text-[11px] text-white tracking-wide block" }, "Automated Trade Management"
    ),
    React.createElement("span", { className: "text-[8px] text-muted font-mono uppercase" }, "Algo Execution Layer"
    )
    ),
    React.createElement("label", { className: "relative inline-flex items-center cursor-pointer" },
    React.createElement("input", {
      type: "checkbox",
      className: "sr-only peer",
      checked: atmEnabled,
      onChange: (e) =>
      setAtmEnabled(
        e.target.checked
      ) }
    ),
    React.createElement("div", { className: "w-9 h-5 bg-white/10 peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full after:content-[''] after:absolute after:top-[2.5px] after:left-[2.5px] after:bg-gray-500 after:rounded-full after:h-3.5 after:w-3.5 after:transition-all peer-checked:bg-green-500 peer-checked:after:bg-white" })
    )
    ),
    React.createElement("div", {
      className: `text-[10px] font-bold px-3 py-1.5 rounded-lg border flex items-center justify-between ${atmEnabled ? "bg-green-500/10 text-green-400 border-green-500/20" : "bg-white/5 text-muted border-white/5"}` },
    React.createElement("span", { className: "flex items-center gap-2" },
    React.createElement("div", {
      className: `w-1.5 h-1.5 rounded-full ${atmEnabled ? "bg-green-500 animate-pulse" : "bg-gray-500"}` }
    ), "ATM ENGINE"
    ),
    React.createElement("span", { className: "font-mono" },
    atmStatus.toUpperCase()
    )
    )
    ),
    React.createElement("div", { className: "px-4 py-3 border-b border-white/5" },
    React.createElement("label", { className: "block text-muted mb-2 text-[9px] font-bold uppercase tracking-widest opacity-60" }, "System Strategy"
    ),
    React.createElement("div", { className: "grid grid-cols-3 gap-1.5" },
    [
    "conservative",
    "aggressive",
    "scalper",
    "custom"].
    map((strat) =>
    React.createElement("button", {
      key: strat,
      onClick: () => {
        setAtmStrategy(strat);
        if (strat !== "custom") {
          setAtmParams(
            getDefaultATMParams(
              strat
            )
          );
        }
      },
      className: `py-2 rounded-lg text-[9px] font-black tracking-tight transition-all duration-200 border ${atmStrategy === strat ? "bg-accent/20 text-accent border-accent/30 shadow-[0_0_15px_rgba(var(--accent-rgb),0.1)]" : "bg-white/5 text-muted border-white/5 hover:bg-white/10 hover:text-white"}` },
    strat.toUpperCase()
    )
    )
    )
    ),
    React.createElement("div", { className: "px-4 py-3 border-b border-white/5 overflow-y-auto flex-1 no-scrollbar" },
    React.createElement("h4", { className: "text-muted font-bold mb-3 text-[9px] uppercase tracking-widest opacity-60" }, "Engine Parameters"
    ),
    React.createElement("div", { className: "space-y-3" },
    React.createElement("div", { className: "grid grid-cols-2 gap-3" },
    React.createElement("div", { className: "bg-white/[0.02] rounded-xl p-2.5 border border-white/5 group hover:border-white/10 transition-colors" },
    React.createElement("label", { className: "text-muted text-[8px] font-bold uppercase block mb-1.5 opacity-60" }, "Entry Size"
    ),
    React.createElement(window.NumInput, {
      value: atmParams.entrySize,
      onChange: (v) =>
      setAtmParams({
        ...atmParams,
        entrySize: v
      }),
      step: 0.1 }
    )
    ),
    React.createElement("div", { className: "bg-white/[0.02] rounded-xl p-2.5 border border-white/5 group hover:border-white/10 transition-colors" },
    React.createElement("label", { className: "text-muted text-[8px] font-bold uppercase block mb-1.5 opacity-60" }, "Initial Stop Loss"
    ),
    React.createElement(window.NumInput, {
      value: atmParams.initialStopLoss || 0,
      onChange: (v) =>
      setAtmParams({
        ...atmParams,
        initialStopLoss: v
      }),
      step: 5 }
    )
    ),
    React.createElement("div", { className: "bg-white/[0.02] rounded-xl p-2.5 border border-white/5 group hover:border-white/10 transition-colors" },
    React.createElement("label", { className: "text-muted text-[8px] font-bold uppercase block mb-1.5 opacity-60" }, "Scale Levels"
    ),
    React.createElement(window.NumInput, {
      value:
      atmParams.scaleInLevels,
      onChange: (v) =>
      setAtmParams({
        ...atmParams,
        scaleInLevels: v
      }),
      step: 1 }
    )
    )
    ),
    React.createElement("div", { className: "grid grid-cols-2 gap-3" },
    React.createElement("div", { className: "bg-white/[0.02] rounded-xl p-2.5 border border-white/5" },
    React.createElement("label", { className: "text-muted text-[8px] font-bold uppercase block mb-1.5 opacity-60" }, "In Dist (pts)"
    ),
    React.createElement(window.NumInput, {
      value:
      atmParams.scaleInDistance,
      onChange: (v) =>
      setAtmParams({
        ...atmParams,
        scaleInDistance: v
      }),
      step: 5 }
    )
    ),
    React.createElement("div", { className: "bg-white/[0.02] rounded-xl p-2.5 border border-white/5" },
    React.createElement("label", { className: "text-muted text-[8px] font-bold uppercase block mb-1.5 opacity-60" }, "Out Levels"
    ),
    React.createElement(window.NumInput, {
      value:
      atmParams.scaleOutLevels,
      onChange: (v) =>
      setAtmParams({
        ...atmParams,
        scaleOutLevels: v
      }),
      step: 1 }
    )
    )
    ),
    React.createElement("div", { className: "grid grid-cols-5 gap-1.5" },
    [
    "profitTarget1",
    "profitTarget2",
    "profitTarget3",
    "profitTarget4",
    "profitTarget5"].
    map((tpKey, i) =>
    React.createElement("div", {
      key: tpKey,
      className: "bg-green-500/[0.03] rounded-xl p-2 border border-green-500/10" },
    React.createElement("label", { className: "text-green-500/50 text-[8px] font-bold block mb-1.5 uppercase leading-none" }, "TP",
    i + 1
    ),
    React.createElement(window.NumInput, {
      value: atmParams[tpKey],
      onChange: (v) =>
      setAtmParams({
        ...atmParams,
        [tpKey]: v
      }),
      step: 5 }
    )
    )
    )
    ),
    React.createElement("div", { className: "grid grid-cols-2 gap-3" },
    React.createElement("div", { className: "bg-white/[0.02] rounded-xl p-2.5 border border-white/5" },
    React.createElement("label", { className: "text-muted text-[8px] font-bold uppercase block mb-1.5 opacity-60" }, "BE Dist (pts)"
    ),
    React.createElement(window.NumInput, {
      value:
      atmParams.breakEvenDistance,
      onChange: (v) =>
      setAtmParams({
        ...atmParams,
        breakEvenDistance: v
      }),
      step: 5 }
    )
    ),
    React.createElement("div", { className: "bg-white/[0.02] rounded-xl p-2.5 border border-white/5" },
    React.createElement("label", { className: "text-muted text-[8px] font-bold uppercase block mb-1.5 opacity-60" }, "BE Offset (pts)"
    ),
    React.createElement(window.NumInput, {
      value:
      atmParams.breakEvenOffset,
      onChange: (v) =>
      setAtmParams({
        ...atmParams,
        breakEvenOffset: v
      }),
      step: 1 }
    )
    )
    ),
    React.createElement("div", { className: "grid grid-cols-2 gap-3" },
    React.createElement("div", { className: "bg-blue-500/[0.03] rounded-xl p-2.5 border border-blue-500/10" },
    React.createElement("label", { className: "text-blue-500/50 text-[8px] font-bold block mb-1.5 uppercase" }, "Trailing"
    ),
    React.createElement(window.NumInput, {
      value:
      atmParams.trailingStop,
      onChange: (v) =>
      setAtmParams({
        ...atmParams,
        trailingStop: v
      }),
      step: 5 }
    )
    ),
    React.createElement("div", { className: "bg-red-500/[0.03] rounded-xl p-2.5 border border-red-500/10" },
    React.createElement("label", { className: "text-red-500/50 text-[8px] font-bold block mb-1.5 uppercase" }, "Max DD ($)"
    ),
    React.createElement(window.NumInput, {
      value:
      atmParams.maxDrawdown,
      onChange: (v) =>
      setAtmParams({
        ...atmParams,
        maxDrawdown: v
      }),
      step: 10 }
    )
    )
    )
    )
    ),
    React.createElement("div", { className: "px-4 py-3 bg-black/40 h-[120px] shrink-0" },
    React.createElement("h4", { className: "text-muted font-bold mb-2 text-[9px] uppercase tracking-widest opacity-60" }, "Engine Logs"
    ),
    React.createElement("div", { className: "space-y-1 overflow-y-auto h-[75px] no-scrollbar pr-2" },
    atmLog.length === 0 ?
    React.createElement("p", { className: "text-white/10 text-[9px] italic font-mono uppercase tracking-tighter" }, "System Ready for Events..."
    ) :
    atmLog.map((log, idx) =>
    React.createElement("div", {
      key: idx,
      className: "text-[9px] text-white/40 mb-1 font-mono hover:text-white/60 transition-colors" },
    React.createElement("span", { className: "text-accent underline decoration-accent/20 underline-offset-2" }, "LOG"
    ), " ",
    log
    )
    )
    )
    )
    ) :
    React.createElement(React.Fragment, null,
    React.createElement("div", { className: "px-4 py-4 bg-white/[0.01] border-b border-white/5" },
    React.createElement("div", { className: "flex justify-between items-end mb-3" },
    React.createElement("div", { className: "flex flex-col" },
    React.createElement("span", { className: "text-[8px] font-black text-muted uppercase tracking-widest mb-1 opacity-60" }, "Market Sentiment"
    ),
    React.createElement("div", { className: "flex items-center gap-2" },
    React.createElement("span", {
      className: `text-sm font-black tracking-tight ${!isAlgoActive ? "text-white/20" : signal === "BUY" ? "text-green-500" : signal === "SELL" ? "text-red-500" : "text-white/40"}` },
    !isAlgoActive ?
    "MANUAL" :
    signal === "HOLD" ?
    "NEUTRAL" :
    signal
    ),
    isAlgoActive &&
    React.createElement("span", { className: "text-[10px] font-mono text-white/40 font-bold" },
    (
    systemStatus?.confidence ||
    98.4).
    toFixed(1), "%"
    )
    )
    ),
    React.createElement("div", { className: "flex flex-col items-end" },
    React.createElement("span", { className: "text-[8px] font-mono text-muted uppercase mb-1 opacity-60" }, "Algorithm"
    ),
    React.createElement("span", { className: "text-[10px] font-bold text-white/60" },
    isAlgoActive ?
    systemStatus?.algorithm ===
    "FourierCycle" ?
    "FOURIER" :
    "QUANTUM AI" :
    "DISABLED"
    )
    )
    ),
    React.createElement("div", { className: "h-1.5 w-full bg-white/5 rounded-full overflow-hidden flex" },
    React.createElement("div", {
      className: `transition-all duration-1000 ${!isAlgoActive ? "w-[50%] bg-white/10" : signal === "BUY" ? "w-[85%] bg-green-500 shadow-[0_0_10px_rgba(34,197,94,0.5)]" : signal === "SELL" ? "w-[15%] bg-red-500 shadow-[0_0_10px_rgba(239,68,68,0.5)]" : "w-[50%] bg-white/20"}` }
    )
    ),
    React.createElement("div", { className: "flex justify-between items-center mt-4" },
    React.createElement("div", { className: "flex items-center gap-3" },
    React.createElement("span", { className: "text-[9px] font-black text-white/30 uppercase tracking-widest" }, "Execution Mode"
    )
    ),
    React.createElement("label", { className: "flex items-center gap-2 cursor-pointer group px-2 py-1 rounded-lg hover:bg-white/5 transition-colors" },
    React.createElement("span", {
      className: `text-[9px] font-bold tracking-widest transition-colors ${oneClick ? "text-accent" : "text-muted"}` },
    "ONE-CLICK"
    ),
    React.createElement("div", {
      className: `w-8 h-4 rounded-full p-0.5 transition-all duration-300 ${oneClick ? "bg-accent/40" : "bg-white/10"}`,
      onClick: toggleOneClick },
    React.createElement("div", {
      className: `w-3 h-3 bg-white rounded-full shadow-lg transition-transform duration-300 transform ${oneClick ? "translate-x-4" : "translate-x-0"}` }
    )
    )
    )
    )
    ),
    React.createElement("div", { className: "flex-1 flex flex-col p-4 gap-4 overflow-y-auto no-scrollbar" },
    availableAccounts.length > 0 &&
    React.createElement("div", { className: "space-y-1.5 " },
    React.createElement("label", { className: "text-[8px] font-black text-accent uppercase tracking-widest opacity-80 ml-1" }, "TRADING ACCOUNT"
    ),
    React.createElement("div", { className: "bg-white/[0.03] rounded-xl border border-white/10 focus-within:border-accent/40 transition-all flex items-center px-3" },
    React.createElement("i", { className: "fas fa-wallet text-[10px] text-accent/50 mr-2" }),
    React.createElement("select", {
      value: selectedAccountId,
      onChange: async (e) => {
        const newAccountId = e.target.value;
        manualAccountChange.current = true;
        setSelectedAccountId(newAccountId);
        const account = availableAccounts.find((a) => a.id === newAccountId);
        if (account) {
          const oldPlatform = localStorage.getItem("platform") || "mt5";
          const newPlatform = account.platform;
          if (newPlatform) {
            localStorage.setItem("platform", newPlatform);
            localStorage.setItem("broker_platform", newPlatform);
            window.lastManualPlatformSwitch = Date.now();
            // console.log(`[ORDERENTRY] Manual switch: ${oldPlatform} → ${newPlatform}`);
          }
          if (newPlatform && newPlatform !== oldPlatform) {
            window.dispatchEvent(new CustomEvent("frontend_data_reset"));
            fetch("/api/v2/feed/switch-platform", {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({ platform: newPlatform })
            }).catch((err) => console.error("Engine switch failed:", err));
            fetch("/api/config", {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({ platform: newPlatform })
            }).catch((err) => console.error("Config sync failed:", err));
          }
          try {
            const res = await fetch(`/api/accounts/${newAccountId}/connect?platform=${newPlatform}`, {
              method: "POST"
            });
            if (res.ok) {
              addNotification("success", "Account Connected", `Switched to ${account.name} (${newPlatform.toUpperCase()})`);
            }
          } catch (err) {
            console.error("Failed to connect account:", err);
          }
        }
      },
      className: "flex-1 bg-transparent text-[10px] font-bold text-white py-2.5 outline-none cursor-pointer appearance-none" },
    availableAccounts.
    filter((acc) => acc.platform !== 'nt8').
    map(
      (acc) =>
      React.createElement("option", {
        key: acc.id,
        value: acc.id,
        className: "bg-[#1a1a1a]" },
      acc.name, " (",
      acc.platform.toUpperCase(), ")"
      )
    )
    ),
    React.createElement("i", { className: "fas fa-chevron-down text-[8px] text-muted ml-2" })
    )
    ),
    React.createElement("div", { className: "grid grid-cols-3 gap-2" },
    React.createElement(window.NumInput, {
      label: "Quantity",
      value: qty,
      onChange: (v) => {
        setQty(v);
        if (onVolumeChange) onVolumeChange(v);
      },
      step: qtyStep,
      min: qtyStep,
      precision: currentSymbolPlatform === 'crypto' ? 8 : 2 }
    ),
    React.createElement(window.NumInput, {
      label: "Leverage",
      value: leverage,
      onChange: setLeverage,
      step: 1,
      min: 1,
      onConfirm: handleSetLeverage,
      options: [1, 2, 5, 10, 20, 50, 100] }
    ),
    React.createElement("div", { className: "flex flex-col bg-black border border-border rounded px-2 py-0.5 hover:bg-white/5 transition-all min-h-[22px]" },
    React.createElement("label", { className: "text-[7px] text-muted uppercase font-black leading-tight" }, "Execution"
    ),
    React.createElement("select", {
      value: orderType,
      onChange: (e) =>
      setOrderType(e.target.value),
      className: "w-full bg-transparent text-[9px] font-bold text-white outline-none cursor-pointer appearance-none leading-tight py-0.5" },
    React.createElement("option", {
      value: "MKT",
      className: "bg-[#1a1a1a]" },
    "MKT"
    ),
    React.createElement("option", {
      value: "LMT",
      className: "bg-[#1a1a1a]" },
    "LMT"
    ),
    React.createElement("option", {
      value: "STP",
      className: "bg-[#1a1a1a]" },
    "STP"
    )
    )
    )
    ),
    React.createElement("div", { className: "mt-1 px-1 text-[9px] text-muted/80 leading-tight" },
      minOrderSize > 0
        ? React.createElement(React.Fragment, null,
          React.createElement("span", { className: "font-bold text-white/70 uppercase tracking-wider" }, "Min size: "),
          React.createElement("span", { className: "font-mono" }, `${minOrderSize}`),
          sizeStep > 0 ? React.createElement(React.Fragment, null, " • ",
            React.createElement("span", { className: "font-bold text-white/70 uppercase tracking-wider" }, "Step: "),
            React.createElement("span", { className: "font-mono" }, `${sizeStep}`)
          ) : null,
          contractSize !== 1 ? React.createElement(React.Fragment, null, " • ",
            React.createElement("span", { className: "font-bold text-white/70 uppercase tracking-wider" }, "Contract: "),
            React.createElement("span", { className: "font-mono" }, `${contractSize}`)
          ) : null,
          maxOrderSize > 0 ? React.createElement(React.Fragment, null, " • ",
            React.createElement("span", { className: "font-bold text-white/70 uppercase tracking-wider" }, "Max: "),
            React.createElement("span", { className: "font-mono" }, `${maxOrderSize}`)
          ) : null
        )
        : React.createElement("span", null, "Size rules loaded from exchange when available.")
    ),
    React.createElement("div", { className: "grid grid-cols-2 gap-2 mt-1" },
    NumInput &&
    React.createElement(NumInput, {
      label: "Stop Loss",
      value: sl,
      onChange: setSl,
      step: priceStep * 10,
      placeholder: "NONE" }
    ),
    NumInput &&
    React.createElement(NumInput, {
      label: "Take Profit",
      value: tp,
      onChange: setTp,
      step: priceStep * 10,
      placeholder: "NONE" }
    )
    ),
    orderType !== "MKT" &&
    React.createElement("div", { className: "animate-in fade-in slide-in-from-top-2 duration-300 mt-1" },
    React.createElement(window.NumInput, {
      label: "Trigger Price",
      value: limitPrice,
      onChange: setLimitPrice,
      step: priceStep }
    )
    ),
    React.createElement("div", { className: "space-y-3 mt-2" },
    React.createElement("div", { className: "grid grid-cols-2 gap-3" },
    React.createElement("button", {
      onClick: () =>
      handleOrderClick("BUY"),
      className: "group relative flex flex-col items-center justify-center p-3 rounded-2xl bg-green-500/[0.08] hover:bg-green-500/20 border border-green-500/20 hover:border-green-500/40 transition-all active:scale-[0.97]" },
    React.createElement("span", { className: "text-[9px] font-black text-green-500/60 uppercase tracking-widest mb-1 group-hover:text-green-400 transition-colors" }, "Buy / Long"
    ),
    React.createElement("div", { className: "text-sm font-black text-white flex items-baseline gap-1" },
    React.createElement("span", { className: "opacity-40 text-[10px]" }, "ASK"
    ),
    window.formatPrice(
      tickData?.ask ||
      tickData?.last ||
      systemStatus?.current_price ||
      0
    )
    ),
    React.createElement("div", { className: "absolute top-1 right-2 opacity-0 group-hover:opacity-100 transition-opacity" },
    React.createElement("i", { className: "fas fa-caret-up text-green-500 text-[10px]" })
    )
    ),
    React.createElement("button", {
      onClick: () =>
      handleOrderClick("SELL"),
      className: "group relative flex flex-col items-center justify-center p-3 rounded-2xl bg-red-500/[0.08] hover:bg-red-500/20 border border-red-500/20 hover:border-red-500/40 transition-all active:scale-[0.97]" },
    React.createElement("span", { className: "text-[9px] font-black text-red-500/60 uppercase tracking-widest mb-1 group-hover:text-red-400 transition-colors" }, "Sell / Short"
    ),
    React.createElement("div", { className: "text-sm font-black text-white flex items-baseline gap-1" },
    React.createElement("span", { className: "opacity-40 text-[10px]" }, "BID"
    ),
    window.formatPrice(
      tickData?.bid ||
      tickData?.last ||
      systemStatus?.current_price ||
      0
    )
    ),
    React.createElement("div", { className: "absolute top-1 right-2 opacity-0 group-hover:opacity-100 transition-opacity" },
    React.createElement("i", { className: "fas fa-caret-down text-red-500 text-[10px]" })
    )
    )
    ),
    React.createElement("div", { className: "flex justify-center" },
    React.createElement("div", { className: "px-3 py-1 bg-white/[0.03] rounded-full border border-white/5 flex items-center gap-3" },
    React.createElement("span", { className: "text-[8px] font-bold text-muted uppercase tracking-tighter" }, "Spread"
    ),
    React.createElement("span", { className: "text-[10px] font-mono font-bold text-white/60" },
    (() => {
      const bid = tickData?.bid || tickData?.last || 0;
      const ask = tickData?.ask || tickData?.last || 0;
      if (bid > 0 && ask > 0 && bid !== ask) {
        const rawSpread = Math.abs(ask - bid);
        const prec = symbolMetadata?.digits || 5;
        lastSpreadRef.current = rawSpread.toFixed(prec);
      } else if (bid > 0) {
        lastSpreadRef.current = "0.0";
      }
      return lastSpreadRef.current;
    })()
    ),
    React.createElement("div", { className: "w-[1px] h-2 bg-white/10" }),
    React.createElement("span", { className: "text-[8px] font-bold text-muted uppercase tracking-tighter" }, "Liq"
    ),
    React.createElement("span", { className: "text-[10px] font-mono font-bold text-green-500/60" }, "HIGH"
    )
    )
    ),
    React.createElement("button", {
      onClick: (e) => {
        e.preventDefault();
        e.stopPropagation();
        onOrder(
          "FLAT",
          0,
          0,
          0,
          "MKT",
          0,
          0,
          selectedAccountId,
          currentSymbolPlatform
        );
      },
      className: "w-full py-2.5 bg-white/[0.02] hover:bg-red-500/10 text-white/40 hover:text-red-400 rounded-xl text-[10px] font-black uppercase tracking-[0.2em] border border-white/5 hover:border-red-500/20 transition-all flex justify-center items-center gap-2 group" },
    React.createElement("i", { className: "fas fa-hand-paper text-[10px] opacity-20 group-hover:opacity-100 transition-opacity" }), "Liquidate All"
    )
    ),
    React.createElement("div", { className: "mt-2 flex-1 flex flex-col min-h-0" },
    React.createElement("div", { className: "flex justify-between items-center mb-3 shrink-0 px-1" },
    React.createElement("div", { className: "flex flex-col" },
    React.createElement("span", { className: "text-[10px] font-black text-white uppercase tracking-widest leading-none" }, "Open Positions"
    ),
    React.createElement("span", { className: "text-[8px] text-muted font-mono uppercase mt-1" }, "Live Portfolio"
    )
    ),
    React.createElement("span", {
      className: `text-[9px] font-bold px-2 py-0.5 rounded-full border ${mt5Positions.length > 0 ? "bg-accent/10 text-accent border-accent/20" : "bg-white/5 text-muted border-white/5"}` },
    mt5Positions.length > 0 ?
    `${mt5Positions.length} ACTIVE` :
    "NO POSITIONS"
    )
    ),
    mt5Positions.length > 0 ?
    React.createElement("div", { className: "space-y-2.5 overflow-y-auto flex-1 pr-1 no-scrollbar" },
    mt5Positions.map(
      (pos, idx) =>
      React.createElement("div", {
        key:
        pos.ticket ||
        idx,
        className: "bg-white/[0.02] hover:bg-white/[0.04] rounded-xl p-3 border border-white/5 hover:border-white/10 transition-all cursor-pointer group relative overflow-hidden",
        onClick: () =>
        onSymbolChange?.(
          pos.symbol
        ) },
      React.createElement("div", {
        className: `absolute left-0 top-0 bottom-0 w-1 ${(pos.type === "BUY" || pos.type === "LONG") ? "bg-green-500/40" : "bg-red-500/40"}` }
      ),
      React.createElement("div", { className: "flex justify-between items-center" },
      React.createElement("div", { className: "flex flex-col" },
      React.createElement("div", { className: "flex items-center gap-2 mb-1" },
      React.createElement("span", { className: "text-white font-black text-[11px] tracking-tight" },
      window.cleanSymbol(pos.symbol || symbol)
      ),
      React.createElement("span", {
        className: `text-[8px] font-black px-1.5 py-0.5 rounded uppercase leading-none ${(pos.type === "BUY" || pos.type === "LONG") ? "bg-green-500/10 text-green-400" : "bg-red-500/10 text-red-400"}` },
      pos.type
      )
      ),
      React.createElement("div", { className: "flex items-center gap-2 text-[9px] font-mono text-muted" },
      React.createElement("span", { className: "text-white/40" },
      pos.volume,
      " ", "Lots"
      ),
      React.createElement("span", { className: "w-1 h-1 rounded-full bg-white/10" }),
      React.createElement("span", null, "@",
      window.formatPrice(pos.entry_price)
      )
      )
      ),
      React.createElement("div", { className: "flex items-center gap-3" },
      React.createElement("div", { className: "flex flex-col items-end" },
      (() => {
        const liveProfit = pos.profit !== undefined ? pos.profit : 0;
        return React.createElement(React.Fragment, null,
          React.createElement("span", {
            className: `text-[12px] font-black font-mono leading-none mb-1 ${liveProfit >= 0 ? "text-green-400" : "text-red-400"}` },
            liveProfit >= 0 ? "+" : "",
            liveProfit?.toFixed(2)
          ),
          React.createElement("div", { className: "flex items-center gap-1" },
            React.createElement("div", {
              className: `w-1 h-1 rounded-full ${liveProfit >= 0 ? "bg-green-500" : "bg-red-500"}` }
            ),
            React.createElement("span", { className: "text-[8px] text-muted font-bold uppercase tracking-tighter" }, "USD PnL")
          )
        );
      })(),
      ),
      React.createElement("button", {
        onClick: (
        e) =>
        {
          e.stopPropagation();
          onOrder(
            "CLOSE",
            pos.volume,
            0,
            0,
            "MKT",
            0,
            pos.ticket,
            selectedAccountId,
            currentSymbolPlatform
          );
        },
        className: "w-7 h-7 flex items-center justify-center bg-red-500/5 hover:bg-red-500 text-red-500 hover:text-white rounded-lg transition-all opacity-0 group-hover:opacity-100 border border-red-500/10",
        title: "Close Position" },
      React.createElement("i", { className: "fas fa-times text-[10px]" })
      )
      )
      )
      )
    )
    ) :
    React.createElement("div", { className: "flex-1 flex flex-col items-center justify-center opacity-20 py-8" },
    React.createElement("i", { className: "fas fa-layer-group text-2xl mb-3" }),
    React.createElement("span", { className: "text-[10px] font-black uppercase tracking-widest" }, "No Active Exposure"
    )
    )
    )
    )
    )
    ));
};
window.OrderEntry_Professional = OrderEntry_Professional;
