import React from 'react';
const NumInput = ({ value, onChange, highlight = false, autoSelect = false }) => {
  const { useRef, useEffect } = React;
  const inputRef = useRef(null);
  useEffect(() => {
    if (autoSelect && inputRef.current) {
      inputRef.current.select();
    }
  }, [autoSelect]);
  return (
    React.createElement("input", {
      ref: inputRef,
      type: "number",
      value: value,
      onChange: (e) => onChange(parseFloat(e.target.value) || 0),
      onFocus: (e) => autoSelect && e.target.select(),
      className: `w-full px-2 py-1 bg-black border rounded text-white font-mono text-sm ${highlight ? 'border-accent' : 'border-border'} focus:border-accent outline-none` }
    ));
};
const OrderEntry = ({ systemStatus, config, onOrder, symbol, tickData, mt5Positions, oneClick, setOneClick, isLocked }) => {
  const { useState, useEffect, useRef, useMemo, useCallback } = React;
  const [orderType, setOrderType] = useState('MKT');
  const [action, setAction] = useState('BUY');
  const [volume, setVolume] = useState(config?.volume || 1);
  const [price, setPrice] = useState(0);
  const [sl, setSl] = useState(() => parseFloat(localStorage.getItem('orderEntry_sl') || '0'));
  const [tp, setTp] = useState(() => parseFloat(localStorage.getItem('orderEntry_tp') || '0'));
  const [pendingOrders, setPendingOrders] = useState([]);
  const [activeTab, setActiveTab] = useState('trade');
  const [atmEnabled, setAtmEnabled] = useState(() => localStorage.getItem('atm_enabled') === 'true');
  const [atmStrategy, setAtmStrategy] = useState(() => localStorage.getItem('atm_strategy') || 'conservative');
  const [atmParams, setAtmParams] = useState(() => {
    const saved = localStorage.getItem('atm_params');
    return saved ? JSON.parse(saved) : getDefaultATMParams('conservative');
  });
  const [atmStatus, setAtmStatus] = useState('idle');
  const [atmLog, setAtmLog] = useState([]);
  const priceRef = useRef(null);
  const atmIntervalRef = useRef(null);
  const getDefaultATMParams = (strategy) => {
    const defaults = {
      conservative: {
        entrySize: 1,
        scaleInLevels: 2,
        scaleInDistance: 50,
        scaleOutLevels: 3,
        profitTarget1: 50,
        profitTarget2: 100,
        profitTarget3: 150,
        trailingStop: 30,
        maxDrawdown: 100,
        riskPerTrade: 2
      },
      aggressive: {
        entrySize: 2,
        scaleInLevels: 3,
        scaleInDistance: 30,
        scaleOutLevels: 4,
        profitTarget1: 30,
        profitTarget2: 60,
        profitTarget3: 100,
        trailingStop: 20,
        maxDrawdown: 50,
        riskPerTrade: 5
      },
      custom: atmParams || {}
    };
    return defaults[strategy] || defaults.conservative;
  };
  useEffect(() => {
    localStorage.setItem('atm_enabled', atmEnabled.toString());
  }, [atmEnabled]);
  useEffect(() => {
    localStorage.setItem('atm_strategy', atmStrategy);
  }, [atmStrategy]);
  useEffect(() => {
    localStorage.setItem('atm_params', JSON.stringify(atmParams));
  }, [atmParams]);
  useEffect(() => {
    localStorage.setItem('orderEntry_sl', sl.toString());
  }, [sl]);
  useEffect(() => {
    localStorage.setItem('orderEntry_tp', tp.toString());
  }, [tp]);
  useEffect(() => {
    if (config) {
      setVolume(config.volume || 1);
    }
  }, [config]);
  useEffect(() => {
    if (systemStatus?.pending_orders) {
      setPendingOrders(systemStatus.pending_orders);
    }
  }, [systemStatus?.pending_orders]);
  useEffect(() => {
    if (tickData?.last) {
      setPrice(tickData.last);
    }
  }, [tickData?.last]);
  useEffect(() => {
    if (!atmEnabled || !mt5Positions || mt5Positions.length === 0) {
      if (atmIntervalRef.current) {
        clearInterval(atmIntervalRef.current);
        atmIntervalRef.current = null;
      }
      setAtmStatus('idle');
      return;
    }
    setAtmStatus('monitoring');
    atmIntervalRef.current = setInterval(() => {
      if (mt5Positions.length === 0) {
        setAtmStatus('idle');
        return;
      }
      const position = mt5Positions[0];
      const currentPrice = tickData?.last || 0;
      if (currentPrice <= 0) return;
      const pnl = position.type === 'BUY' ?
      (currentPrice - position.entry_price) * position.volume :
      (position.entry_price - currentPrice) * position.volume;
      const profitTargets = [atmParams.profitTarget1, atmParams.profitTarget2, atmParams.profitTarget3];
      for (let i = 0; i < profitTargets.length; i++) {
        if (pnl >= profitTargets[i] && position.volume > 0) {
          const scaleOutQty = Math.floor(position.volume / (atmParams.scaleOutLevels - i));
          if (scaleOutQty > 0) {
            setAtmStatus('scaling');
            addATMLog(`Scale-out: Closing ${scaleOutQty} contracts at profit ${pnl.toFixed(2)}`);
            onOrder('CLOSE', scaleOutQty, 0, 0, 'MKT', 0);
            break;
          }
        }
      }
      if (pnl <= -atmParams.maxDrawdown && position.volume > 0) {
        setAtmStatus('closing');
        addATMLog(`⚠️ Max drawdown reached: ${pnl.toFixed(2)}. Closing position.`);
        onOrder('CLOSE', position.volume, 0, 0, 'MKT', 0);
      }
    }, 1000);
    return () => {
      if (atmIntervalRef.current) {
        clearInterval(atmIntervalRef.current);
        atmIntervalRef.current = null;
      }
    };
  }, [atmEnabled, mt5Positions, tickData, atmParams, onOrder]);
  const addATMLog = (message) => {
    const timestamp = new Date().toLocaleTimeString();
    setAtmLog((prev) => [...prev.slice(-9), `[${timestamp}] ${message}`]);
  };
  const getPointValue = useCallback(() => {
    if (!symbol) return 1;
    if (window.activeSymbolMetadata && window.activeSymbolMetadata.tick_value) {
      return window.activeSymbolMetadata.tick_value;
    }
    const s = symbol.toUpperCase();
    const price = tickData?.last || 0;
    const platform = systemStatus?.platform || localStorage.getItem('platform');
    if (platform === 'futures' || platform === 'tradovate') {
      if (price > 5000) return 2;
      if (price > 2000) return 5;
      if (price > 50) return 10;
      return 1;
    }
    if (platform === 'crypto') return 1;
    if (s.length === 6 && (s.startsWith('EUR') || s.startsWith('GBP') || s.startsWith('USD'))) return 10;
    return 1;
  }, [symbol, tickData, systemStatus]);
  const handlePlaceOrder = useCallback(() => {
    if (orderType !== 'MKT' && !price) {
      alert('Please enter a price for Limit/Stop orders.');
      return;
    }
    const smartSL = sl > 0 ? sl : null;
    const smartTP = tp > 0 ? tp : null;
    onOrder(action, volume, smartSL, smartTP, orderType, price);
    if (orderType !== 'MKT' && priceRef.current) {
      priceRef.current.select();
    }
  }, [action, volume, price, sl, tp, orderType, onOrder]);
  const handleFlat = useCallback(() => {
    if (window.confirm(`Are you sure you want to FLAT ${symbol}? This will close all open positions and cancel all pending orders for this symbol.`)) {
      onOrder("FLAT", 0, 0, 0, "MKT", 0);
    }
  }, [symbol, onOrder]);
  const isConnected = systemStatus?.connected;
  const isTradingHours = systemStatus?.trading_hours;
  const hasOpenPositions = mt5Positions && mt5Positions.length > 0;
  const currentPosition = hasOpenPositions ? mt5Positions[0] : null;
  return (
    React.createElement("div", { className: "flex flex-col bg-panel h-full text-white font-mono text-xs" },
    React.createElement("div", { className: "flex justify-between items-center p-3 border-b border-border bg-black/50" },
    React.createElement("div", { className: "flex gap-2" },
    React.createElement("button", {
      onClick: () => setActiveTab('trade'),
      className: `px-3 py-1 rounded text-sm font-bold transition-colors ${activeTab === 'trade' ?
      'bg-accent text-black' :
      'bg-[#222] text-muted hover:bg-[#333]'}` },
    "TRADE"
    ),
    React.createElement("button", {
      onClick: () => setActiveTab('atm'),
      className: `px-3 py-1 rounded text-sm font-bold transition-colors ${activeTab === 'atm' ?
      'bg-accent text-black' :
      'bg-[#222] text-muted hover:bg-[#333]'}` },
    "ATM"
    )
    ),
    React.createElement("div", { className: "flex items-center gap-2" },
    React.createElement("span", { className: `text-[10px] px-2 py-0.5 rounded-full font-bold ${isTradingHours ? 'bg-green-500/20 text-green-400' : 'bg-red-500/20 text-red-400'}` },
    isTradingHours ? 'OPEN' : 'CLOSED'
    ),
    React.createElement("label", { className: "relative inline-flex items-center cursor-pointer" },
    React.createElement("input", {
      type: "checkbox",
      className: "sr-only peer",
      checked: oneClick,
      onChange: (e) => setOneClick(e.target.checked) }
    ),
    React.createElement("div", { className: "w-8 h-4 bg-gray-700 peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-gray-400 after:rounded-full after:h-3 after:w-3 after:transition-all peer-checked:bg-accent peer-checked:after:bg-white" }),
    React.createElement("span", { className: "ml-2 text-[10px] font-bold text-muted" }, "ONE-CLICK")
    )
    )
    ),
    activeTab === 'trade' &&
    React.createElement(React.Fragment, null,
    React.createElement("div", { className: "p-3 border-b border-border grid grid-cols-3 gap-2" },
    ['MKT', 'LIMIT', 'STOP'].map((type) =>
    React.createElement("button", {
      key: type,
      onClick: () => setOrderType(type),
      className: `py-2 rounded font-bold text-center transition-colors ${orderType === type ? 'bg-accent text-black' : 'bg-[#222] text-muted hover:bg-[#333]'}` },
    type
    )
    )
    ),
    orderType !== 'MKT' &&
    React.createElement("div", { className: "p-3 border-b border-border" },
    React.createElement("label", { className: "block text-muted mb-1" }, "Price"),
    React.createElement(NumInput, { value: price, onChange: setPrice, highlight: true, autoSelect: true })
    ),
    React.createElement("div", { className: "p-3 border-b border-border" },
    React.createElement("label", { className: "block text-muted mb-1" }, "Volume"),
    React.createElement(NumInput, { value: volume, onChange: setVolume })
    ),
    React.createElement("div", { className: "grid grid-cols-2 gap-2 p-3 border-b border-border" },
    React.createElement("div", null,
    React.createElement("label", { className: "block text-muted mb-1" }, "SL (pts)"),
    React.createElement(NumInput, { value: sl, onChange: setSl })
    ),
    React.createElement("div", null,
    React.createElement("label", { className: "block text-muted mb-1" }, "TP (pts)"),
    React.createElement(NumInput, { value: tp, onChange: setTp })
    )
    ),
    React.createElement("div", { className: "grid grid-cols-2 gap-2 p-2" },
    React.createElement("button", {
      onClick: () => {setAction('SELL');handlePlaceOrder();},
      disabled: !isConnected || isLocked,
      className: `order-btn text-white disabled:opacity-50 disabled:cursor-not-allowed ${isLocked ? 'bg-zinc-800' : 'bg-red-600 hover:bg-red-500'}` },
    isLocked ? React.createElement("i", { className: "fas fa-lock mr-2" }) : null,
    "SELL ",
    volume
    ),
    React.createElement("button", {
      onClick: () => {setAction('BUY');handlePlaceOrder();},
      disabled: !isConnected || isLocked,
      className: `order-btn text-white disabled:opacity-50 disabled:cursor-not-allowed ${isLocked ? 'bg-zinc-800' : 'bg-green-600 hover:bg-green-500'}` },
    isLocked ? React.createElement("i", { className: "fas fa-lock mr-2" }) : null,
    "BUY ",
    volume
    )
    ),
    hasOpenPositions &&
    React.createElement("div", { className: "p-3 border-t border-border" },
    React.createElement("button", {
      onClick: handleFlat,
      disabled: !isConnected,
      className: "order-btn bg-yellow-600 hover:bg-yellow-500 text-black disabled:opacity-50 disabled:cursor-not-allowed" },
    "FLAT ",
    symbol, " (", currentPosition.volume, ")"
    )
    ),
    React.createElement("div", { className: "flex-1 overflow-y-auto custom-scrollbar p-3 border-t border-border mt-auto" },
    React.createElement("h4", { className: "text-muted font-bold mb-2" }, "POSITIONS ", React.createElement("span", { className: "text-accent ml-1" }, mt5Positions.length)),
    mt5Positions.length === 0 && React.createElement("p", { className: "text-gray-600" }, "No open positions."),
    mt5Positions.map((pos) =>
    React.createElement("div", { key: pos.ticket, className: `flex justify-between items-center p-2 rounded mb-1 ${pos.type === 'BUY' ? 'bg-green-900/20' : 'bg-red-900/20'}` },
    React.createElement("div", null,
    React.createElement("span", { className: "font-bold" }, pos.type, " ", pos.volume, " ", pos.symbol),
    React.createElement("span", { className: "block text-gray-500" }, "@", pos.entry_price.toFixed(2))
    ),
    React.createElement("div", { className: "text-right" },
    React.createElement("span", { className: `font-bold ${pos.profit >= 0 ? 'text-green-400' : 'text-red-400'}` }, "$", pos.profit.toFixed(2)),
    React.createElement("button", { onClick: () => onOrder("CLOSE", pos.volume, 0, 0, "MKT", 0, pos.ticket), className: "ml-2 text-red-400 hover:text-red-300" },
    React.createElement("i", { className: "fas fa-times" })
    )
    )
    )
    ),
    React.createElement("h4", { className: "text-muted font-bold mt-4 mb-2" }, "PENDING ORDERS ", React.createElement("span", { className: "text-accent ml-1" }, pendingOrders.length)),
    pendingOrders.length === 0 && React.createElement("p", { className: "text-gray-600" }, "No pending orders."),
    pendingOrders.map((order) =>
    React.createElement("div", { key: order.ticket, className: `flex justify-between items-center p-2 rounded mb-1 ${order.type === 2 || order.type === 4 ? 'bg-green-900/20' : 'bg-red-900/20'}` },
    React.createElement("div", null,
    React.createElement("span", { className: "font-bold" }, order.type_str, " ", order.volume_current, " ", order.symbol),
    React.createElement("span", { className: "block text-gray-500" }, "@", order.price_open.toFixed(2))
    ),
    React.createElement("button", { onClick: () => onOrder("CANCEL", 0, 0, 0, "MKT", 0, order.ticket), className: "text-red-400 hover:text-red-300" },
    React.createElement("i", { className: "fas fa-times" })
    )
    )
    )
    )
    ),
    activeTab === 'atm' &&
    React.createElement("div", { className: "flex-1 flex flex-col overflow-hidden" },
    React.createElement("div", { className: "p-3 border-b border-border" },
    React.createElement("div", { className: "flex items-center justify-between mb-3" },
    React.createElement("span", { className: "font-bold text-sm" }, "Automated Trade Management"),
    React.createElement("label", { className: "relative inline-flex items-center cursor-pointer" },
    React.createElement("input", {
      type: "checkbox",
      className: "sr-only peer",
      checked: atmEnabled,
      onChange: (e) => setAtmEnabled(e.target.checked) }
    ),
    React.createElement("div", { className: "w-10 h-5 bg-gray-700 peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-gray-400 after:rounded-full after:h-4 after:w-4 after:transition-all peer-checked:bg-green-600 peer-checked:after:bg-white" })
    )
    ),
    React.createElement("div", { className: `text-[10px] px-2 py-1 rounded ${atmEnabled ? 'bg-green-500/20 text-green-400' : 'bg-gray-500/20 text-gray-400'}` }, "Status: ",
    atmStatus.toUpperCase()
    )
    ),
    React.createElement("div", { className: "p-3 border-b border-border" },
    React.createElement("label", { className: "block text-muted mb-2 text-[10px]" }, "Strategy"),
    React.createElement("div", { className: "grid grid-cols-3 gap-2" },
    ['conservative', 'aggressive', 'custom'].map((strat) =>
    React.createElement("button", {
      key: strat,
      onClick: () => {
        setAtmStrategy(strat);
        if (strat !== 'custom') {
          setAtmParams(getDefaultATMParams(strat));
        }
      },
      className: `py-1 rounded text-[10px] font-bold transition-colors ${atmStrategy === strat ?
      'bg-accent text-black' :
      'bg-[#222] text-muted hover:bg-[#333]'}` },
    strat.toUpperCase()
    )
    )
    )
    ),
    React.createElement("div", { className: "flex-1 overflow-y-auto custom-scrollbar p-3 border-b border-border" },
    React.createElement("h4", { className: "text-muted font-bold mb-2 text-[10px]" }, "PARAMETERS"),
    React.createElement("div", { className: "space-y-2" },
    React.createElement("div", { className: "grid grid-cols-2 gap-2" },
    React.createElement("div", null,
    React.createElement("label", { className: "text-muted text-[9px]" }, "Entry Size"),
    React.createElement(NumInput, {
      value: atmParams.entrySize,
      onChange: (v) => setAtmParams({ ...atmParams, entrySize: v }) }
    )
    ),
    React.createElement("div", null,
    React.createElement("label", { className: "text-muted text-[9px]" }, "Scale-In Levels"),
    React.createElement(NumInput, {
      value: atmParams.scaleInLevels,
      onChange: (v) => setAtmParams({ ...atmParams, scaleInLevels: v }) }
    )
    )
    ),
    React.createElement("div", { className: "grid grid-cols-2 gap-2" },
    React.createElement("div", null,
    React.createElement("label", { className: "text-muted text-[9px]" }, "Scale-In Distance (pts)"),
    React.createElement(NumInput, {
      value: atmParams.scaleInDistance,
      onChange: (v) => setAtmParams({ ...atmParams, scaleInDistance: v }) }
    )
    ),
    React.createElement("div", null,
    React.createElement("label", { className: "text-muted text-[9px]" }, "Scale-Out Levels"),
    React.createElement(NumInput, {
      value: atmParams.scaleOutLevels,
      onChange: (v) => setAtmParams({ ...atmParams, scaleOutLevels: v }) }
    )
    )
    ),
    React.createElement("div", { className: "grid grid-cols-3 gap-2" },
    React.createElement("div", null,
    React.createElement("label", { className: "text-muted text-[9px]" }, "TP1 (pts)"),
    React.createElement(NumInput, {
      value: atmParams.profitTarget1,
      onChange: (v) => setAtmParams({ ...atmParams, profitTarget1: v }) }
    )
    ),
    React.createElement("div", null,
    React.createElement("label", { className: "text-muted text-[9px]" }, "TP2 (pts)"),
    React.createElement(NumInput, {
      value: atmParams.profitTarget2,
      onChange: (v) => setAtmParams({ ...atmParams, profitTarget2: v }) }
    )
    ),
    React.createElement("div", null,
    React.createElement("label", { className: "text-muted text-[9px]" }, "TP3 (pts)"),
    React.createElement(NumInput, {
      value: atmParams.profitTarget3,
      onChange: (v) => setAtmParams({ ...atmParams, profitTarget3: v }) }
    )
    )
    ),
    React.createElement("div", { className: "grid grid-cols-2 gap-2" },
    React.createElement("div", null,
    React.createElement("label", { className: "text-muted text-[9px]" }, "Trailing Stop (pts)"),
    React.createElement(NumInput, {
      value: atmParams.trailingStop,
      onChange: (v) => setAtmParams({ ...atmParams, trailingStop: v }) }
    )
    ),
    React.createElement("div", null,
    React.createElement("label", { className: "text-muted text-[9px]" }, "Max Drawdown ($)"),
    React.createElement(NumInput, {
      value: atmParams.maxDrawdown,
      onChange: (v) => setAtmParams({ ...atmParams, maxDrawdown: v }) }
    )
    )
    )
    )
    ),
    React.createElement("div", { className: "flex-1 overflow-y-auto custom-scrollbar p-3 border-t border-border" },
    React.createElement("h4", { className: "text-muted font-bold mb-2 text-[10px]" }, "LOG"),
    atmLog.length === 0 ?
    React.createElement("p", { className: "text-gray-600 text-[9px]" }, "Waiting for ATM events...") :
    atmLog.map((log, idx) =>
    React.createElement("div", { key: idx, className: "text-[9px] text-gray-400 mb-1 font-mono" },
    log
    )
    )
    )
    )
    ));
};
export default OrderEntry;