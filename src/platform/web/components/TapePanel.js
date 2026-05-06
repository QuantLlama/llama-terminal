const TapePanelResizer = ({ onResize }) => {
  const startX = React.useRef(0);
  const startWidth = React.useRef(0);
  const onMouseDown = (e) => {
    e.preventDefault();
    startX.current = e.pageX;
    startWidth.current = e.target.parentElement.offsetWidth;
    const onMove = (ev) => onResize(startWidth.current + (ev.pageX - startX.current));
    const onUp = () => {
      document.removeEventListener('mousemove', onMove);
      document.removeEventListener('mouseup', onUp);
    };
    document.addEventListener('mousemove', onMove);
    document.addEventListener('mouseup', onUp);
  };
  return (
    React.createElement("div", {
      onMouseDown: onMouseDown,
      style: {
        position: 'absolute', right: 0, top: 0, bottom: 0,
        width: 5, cursor: 'col-resize', zIndex: 10
      } }
    ));
};
const TapePanel = ({
  symbol,
  lastPrice,
  volume,
  timestamp,
  isCumulative = false,
  title = 'Time & Sales',
  height = 'h-48',
  configId = 'default_tape',
  onClose,
  tickSize = null
}) => {
  const { useState, useEffect, useRef, useMemo, useCallback } = React;
  const getPriceDecimals = useCallback((sym, tick) => {
    if (window.getSymbolPrecision) {
      return window.getSymbolPrecision(sym, null, lastPrice || 0).digits;
    }
    if (tick !== null && tick !== undefined && tick > 0) {
      const s = tick.toString();
      const dot = s.indexOf('.');
      return dot === -1 ? 0 : s.length - dot - 1;
    }
    if (!sym) return 2;
    const u = sym.toUpperCase();
    if (u.includes('JPY')) return 3;
    if (u.includes('BTC') || u.includes('XBT')) return 1;
    if (u.includes('ETH')) return 2;
    if (u.includes('DOGE') || u.includes('SHIB')) return 6;
    if (u.includes('SOL') || u.includes('ADA')) return 4;
    return 2;
  }, [lastPrice]);
  const priceDecimals = useMemo(
    () => getPriceDecimals(symbol, tickSize),
    [symbol, tickSize, getPriceDecimals]
  );
  const formatPrice = useCallback(
    (p) => p == null ? '—' : p.toFixed(priceDecimals),
    [priceDecimals]
  );
  const formatSize = useCallback((s) => {
    if (s == null || isNaN(s)) return '—';
    const n = Number(s);
    const nearInt = Math.abs(n - Math.round(n)) < 1e-6;
    if (nearInt) {
      return Math.round(n).toLocaleString(undefined, {
        minimumFractionDigits: 0,
        maximumFractionDigits: 0
      });
    }
    return n.toLocaleString(undefined, {
      minimumFractionDigits: 0,
      maximumFractionDigits: 2
    });
  }, []);
  const formatVolume = useCallback((v) => {
    if (v == null) return '—';
    const abs = Math.abs(v);
    const sign = v < 0 ? '-' : '';
    if (abs >= 1_000_000) return sign + (abs / 1_000_000).toFixed(2) + 'M';
    if (abs >= 1_000) return sign + (abs / 1_000).toFixed(1) + 'K';
    return v.toLocaleString(undefined, { minimumFractionDigits: 0, maximumFractionDigits: 2 });
  }, []);
  const formatTradeTime = useCallback((t) => {
    if (t == null) return '--:--:--';
    if (typeof t === 'string' && t.includes(':')) return t;
    const n = Number(t);
    if (!n || isNaN(n)) return '--:--:--';
    const d = new Date(n < 1e10 ? n * 1000 : n);
    const h = String(d.getHours()).padStart(2, '0');
    const m = String(d.getMinutes()).padStart(2, '0');
    const s = String(d.getSeconds()).padStart(2, '0');
    const ms = String(d.getMilliseconds()).padStart(3, '0');
    return `${h}:${m}:${s}.${ms}`;
  }, []);
  const getPlatform = () => {
    try {
      return typeof window.detectPlatformType === 'function' ?
      window.detectPlatformType() :
      'futures';
    } catch {return 'futures';}
  };
  const buildDefaults = () => {
    const p = getPlatform();
    const base = {
      minSize: p === 'crypto' ? 0.01 : 0,
      buyColor: '#10b981',
      sellColor: '#ef4444',
      neutralColor: '#64748b',
      whaleColor: '#f59e0b',
      showTime: true,
      showDelta: true,
      showTotal: true,
      showDeltaBar: true,
      totalMode: 'exchange',
      fontSize: '10px',
      rowHeight: '20px',
      maxRows: 200,
      whaleThreshold: p === 'crypto' ? 1.0 : 50,
      aggregationMs: 0,
      forceWindowMs: 30_000
    };
    if (configId === 'slow') return { ...base, aggregationMs: 300 };
    return base;
  };
  const [config, setConfig] = useState(() => {
    try {
      const raw = localStorage.getItem(`tape_config_${configId}`);
      const defaults = buildDefaults();
      if (raw) {
        const merged = { ...defaults, ...JSON.parse(raw) };
        if (configId === 'slow') {
          if (!merged.aggregationMs || merged.aggregationMs <= 0) merged.aggregationMs = 300;
          if (merged.minSize == null || Number.isNaN(merged.minSize)) merged.minSize = defaults.minSize;
        }
        return merged;
      }
    } catch {}
    return buildDefaults();
  });
  const [isConfigOpen, setIsConfigOpen] = useState(false);
  useEffect(() => {
    try {localStorage.setItem(`tape_config_${configId}`, JSON.stringify(config));} catch {}
  }, [config, configId]);
  const [colWidths, setColWidths] = useState(() => {
    try {
      const raw = localStorage.getItem(`tape_widths_${configId}`);
      if (raw) return JSON.parse(raw);
    } catch {}
    return { time: 52, price: 64, size: 54, delta: 56, total: 58 };
  });
  useEffect(() => {
    try {localStorage.setItem(`tape_widths_${configId}`, JSON.stringify(colWidths));} catch {}
  }, [colWidths, configId]);
  const handleColumnResize = useCallback((col, w) => {
    setColWidths((prev) => ({ ...prev, [col]: Math.max(28, w) }));
  }, []);
  const sessionBuyVol = useRef(0);
  const sessionSellVol = useRef(0);
  const sessionTotalVol = useRef(0);
  const rollingWindow = useRef([]);
  const tradeBuffer = useRef([]);
  const aggTimer = useRef(null);
  const statsTimer = useRef(null);
  const forceTimer = useRef(null);
  const [trades, setTrades] = useState([]);
  const [sessionStats, setSessionStats] = useState({ buy: 0, sell: 0, total: 0 });
  const [forceBaseline, setForceBaseline] = useState(1);
  const [rollingMomentum, setRollingMomentum] = useState({ buyPct: 50, deltaDir: 'neutral', intensity: 0 });
  const resetState = useCallback(() => {
    setTrades([]);
    tradeBuffer.current = [];
    sessionBuyVol.current = 0;
    sessionSellVol.current = 0;
    sessionTotalVol.current = 0;
    rollingWindow.current = [];
    setSessionStats({ buy: 0, sell: 0, total: 0 });
    setForceBaseline(1);
    if (aggTimer.current) {clearTimeout(aggTimer.current);aggTimer.current = null;}
    if (statsTimer.current) {clearInterval(statsTimer.current);statsTimer.current = null;}
    if (forceTimer.current) {clearInterval(forceTimer.current);forceTimer.current = null;}
  }, []);
  useEffect(() => {resetState();}, [symbol]);
  useEffect(() => {
    const h = () => resetState();
    window.addEventListener('frontend_data_reset', h);
    return () => window.removeEventListener('frontend_data_reset', h);
  }, [resetState]);
  const [marketClosed, setMarketClosed] = useState(false);
  const lastSeenTimestampRef = useRef(0);
  const lastSeenTimestampTimeRef = useRef(0);
  useEffect(() => {
    const STALE_MS = 60 * 1000;
    const checkMarket = () => {
      const ts = Number(timestamp);
      const now = Date.now();
      if (ts > 0 && ts !== lastSeenTimestampRef.current) {
        const tsMs = ts < 1e10 ? ts * 1000 : ts;
        if (now - tsMs < STALE_MS) {
          lastSeenTimestampRef.current = ts;
          lastSeenTimestampTimeRef.current = now;
          setMarketClosed(false);
          return;
        }
      }
      const wallAge = now - lastSeenTimestampTimeRef.current;
      if (lastSeenTimestampTimeRef.current === 0 || wallAge > STALE_MS) {
        if (!marketClosed) {
          setMarketClosed(true);
        }
      }
    };
    checkMarket();
    const id = setInterval(checkMarket, 10_000);
    return () => clearInterval(id);
  }, [timestamp, resetState, marketClosed]);
  const computeTapeMetrics = useCallback(() => {
    const now = Date.now();
    const windowLimit = Number(config.forceWindowMs) || 30000;
    rollingWindow.current = rollingWindow.current.filter(
      (e) => now - e.ts < Math.max(windowLimit, 5000)
    );
    const allSizes = rollingWindow.current.map((e) => e.size);
    if (allSizes.length === 0) {
      return { baseline: 1, momentum: { buyPct: 50, deltaDir: 'neutral', intensity: 0 } };
    }
    const sorted = [...allSizes].sort((a, b) => a - b);
    const p95Idx = Math.min(Math.floor(sorted.length * 0.95), sorted.length - 1);
    const baseline = sorted[p95Idx] || 1;
    const recent = rollingWindow.current.filter((e) => now - e.ts < 3000);
    let mBuy = 0,mSell = 0;
    recent.forEach((e) => {
      const sz = Number(e.size) || 0;
      if (e.side === 'buy') mBuy += sz;else
      if (e.side === 'sell') mSell += sz;
    });
    const mTotal = mBuy + mSell;
    const buyPct = mTotal === 0 ? 50 : mBuy / mTotal * 100;
    const deltaDir = buyPct > 55 ? 'buy' : buyPct < 45 ? 'sell' : 'neutral';
    const intensity = Math.min(mTotal / (baseline * 5), 1);
    return { baseline, momentum: { buyPct, deltaDir, intensity } };
  }, [config.forceWindowMs]);
  useEffect(() => {
    forceTimer.current = setInterval(() => {
      const m = computeTapeMetrics();
      setForceBaseline(m.baseline);
      setRollingMomentum(m.momentum);
    }, 100);
    return () => {if (forceTimer.current) clearInterval(forceTimer.current);};
  }, [computeTapeMetrics]);
  useEffect(() => {
    statsTimer.current = setInterval(() => {
      setSessionStats({
        buy: sessionBuyVol.current,
        sell: sessionSellVol.current,
        total: sessionTotalVol.current
      });
    }, 200);
    return () => {if (statsTimer.current) clearInterval(statsTimer.current);};
  }, []);
  const deltaBarMetrics = useMemo(() => {
    const buy = sessionStats.buy;
    const sell = sessionStats.sell;
    const total = buy + sell;
    if (total === 0) return { buyPct: 50, delta: 0, deltaDir: 'neutral' };
    const delta = buy - sell;
    const buyPct = buy / total * 100;
    const deltaDir = delta > 0 ? 'buy' : delta < 0 ? 'sell' : 'neutral';
    return { buyPct, delta, deltaDir };
  }, [sessionStats]);
  const configRef = useRef(config);
  useEffect(() => {configRef.current = config;}, [config]);
  const flushBuffer = useCallback(() => {
    if (tradeBuffer.current.length === 0) return;
    const cfg = configRef.current;
    const chrono = [...tradeBuffer.current].reverse();
    tradeBuffer.current = [];
    let processed;
    if (cfg.aggregationMs > 0) {
      const agg = [];
      chrono.forEach((trade) => {
        const last = agg[agg.length - 1];
        if (last && last.price === trade.price && last.side === trade.side) {
          last.size += trade.size;
          last.cumulativeTotal = trade.cumulativeTotal;
          last.totalVolume = trade.totalVolume;
          last.sessionDelta = trade.sessionDelta;
          last.time = trade.time;
          last.id = trade.id;
        } else {
          agg.push({ ...trade });
        }
      });
      processed = agg.reverse();
    } else {
      processed = chrono.reverse();
    }
    setTrades((prev) => [...processed, ...prev].slice(0, cfg.maxRows));
  }, []);
    const handleTrade = useCallback((trade) => {
    const cfg = configRef.current;
    
    // Support Natural Mode (raw MT5 flags)
    let side = trade.side;
    if (cfg.naturalMode && trade.flags) {
      const flags = Number(trade.flags);
      if (flags & 32) side = 'buy';
      else if (flags & 64) side = 'sell';
      else side = 'neutral';
    }

    const size = Number(trade.size) || 0;
    if (cfg.minSize > 0 && size < cfg.minSize) return;
    const now = Date.now();
    
    if (side === 'buy') sessionBuyVol.current += size;
    else if (side === 'sell') sessionSellVol.current += size;
    
    sessionTotalVol.current += size;
    rollingWindow.current.push({ size, ts: now, side: side });
    if (rollingWindow.current.length > 5000) {
      rollingWindow.current = rollingWindow.current.slice(-3000);
    }
    let displayTotal;
    if (cfg.totalMode === 'exchange' && trade.totalVolume !== undefined) {
      displayTotal = trade.totalVolume;
    } else if (cfg.totalMode === 'delta') {
      displayTotal = sessionBuyVol.current - sessionSellVol.current;
    } else {
      displayTotal = sessionTotalVol.current;
    }
    const enriched = {
      ...trade,
      side: side, // Overwrite with natural side if needed
      cumulativeTotal: displayTotal,
      sessionDelta: sessionBuyVol.current - sessionSellVol.current,
      _ts: now
    };
    if (cfg.aggregationMs > 0) {
      tradeBuffer.current.unshift(enriched);
      if (!aggTimer.current) {
        aggTimer.current = setTimeout(() => {
          flushBuffer();
          aggTimer.current = null;
        }, cfg.aggregationMs);
      }
    } else {
      setTrades((prev) => [enriched, ...prev].slice(0, cfg.maxRows));
    }
  }, [flushBuffer]);
  useEffect(() => {
    return () => {
      if (aggTimer.current) clearTimeout(aggTimer.current);
      if (statsTimer.current) clearInterval(statsTimer.current);
      if (forceTimer.current) clearInterval(forceTimer.current);
    };
  }, []);
  if (typeof window.useTradeStream === 'function') {
    const streamAgg = configId === 'slow' ? Math.max(100, config.aggregationMs || 300) : 0;
    window.useTradeStream(
      symbol,
      lastPrice,
      volume,
      timestamp,
      handleTrade,
      isCumulative,
      null,
      streamAgg,
      `tape_${configId}`
    );
  }
  const headerCell = (w, noBorder = false) => ({
    width: w, minWidth: w, maxWidth: w,
    position: 'relative', padding: '2px 6px',
    display: 'flex', alignItems: 'center', flexShrink: 0,
    fontSize: '9px', fontWeight: 700, letterSpacing: '0.08em',
    color: '#4b5563', textTransform: 'uppercase',
    borderRight: noBorder ? 'none' : '1px solid rgba(255,255,255,0.04)',
    userSelect: 'none', overflow: 'hidden'
  });
  const dataCell = (w, extra = {}) => ({
    width: w, minWidth: w, maxWidth: w,
    padding: '0 6px', display: 'flex', alignItems: 'center', flexShrink: 0,
    fontSize: config.fontSize,
    fontFamily: "'JetBrains Mono','Cascadia Code','Fira Code',monospace",
    fontVariantNumeric: 'tabular-nums', overflow: 'hidden',
    ...extra
  });
  return (
    React.createElement("div", {
      className: `flex flex-col ${height} overflow-hidden rounded-sm shadow-xl relative`,
      style: {
        background: '#080b0f',
        border: '1px solid rgba(255,255,255,0.07)',
        fontFamily: "'JetBrains Mono',monospace"
      } },
    React.createElement("div", { style: {
        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        padding: '5px 8px',
        background: 'rgba(0,0,0,0.5)',
        borderBottom: '1px solid rgba(255,255,255,0.07)',
        flexShrink: 0
      } },
    React.createElement("div", { style: { display: 'flex', flexDirection: 'column', minWidth: 0 } },
    React.createElement("span", { style: {
        fontSize: '10px', fontWeight: 900, color: '#e2e8f0',
        textTransform: 'uppercase', letterSpacing: '0.12em', lineHeight: 1
      } },
    title
    ),
    React.createElement("span", { style: {
        fontSize: '9px', color: '#38bdf8', fontWeight: 700,
        lineHeight: 1, marginTop: 2, letterSpacing: '0.05em'
      } },
    symbol
    )
    ),
    React.createElement("div", { style: { display: 'flex', gap: 7, alignItems: 'center', fontSize: '9px', fontFamily: 'monospace' } },
    React.createElement("span", { style: { color: config.buyColor, fontWeight: 700 } }, "B ", formatVolume(sessionStats.buy)),
    React.createElement("span", { style: { color: config.sellColor, fontWeight: 700 } }, "S ", formatVolume(sessionStats.sell)),
    React.createElement("span", { style: {
        color: deltaBarMetrics.deltaDir === 'buy' ? config.buyColor :
        deltaBarMetrics.deltaDir === 'sell' ? config.sellColor :
        config.neutralColor,
        fontWeight: 700
      } }, "\u0394 ",
    deltaBarMetrics.delta >= 0 ? '+' : '', formatVolume(deltaBarMetrics.delta)
    )
    ),
    React.createElement("div", { style: { display: 'flex', gap: 4 } },
    React.createElement("button", {
      onClick: () => setIsConfigOpen(true),
      style: { background: 'none', border: 'none', cursor: 'pointer', color: '#4b5563', padding: '2px 4px', transition: 'color 0.15s' },
      onMouseEnter: (e) => e.currentTarget.style.color = '#94a3b8',
      onMouseLeave: (e) => e.currentTarget.style.color = '#4b5563' },
    React.createElement("i", { className: "fas fa-cog", style: { fontSize: 10 } })
    ),
    onClose &&
    React.createElement("button", {
      onClick: onClose,
      style: { background: 'none', border: 'none', cursor: 'pointer', color: '#4b5563', padding: '2px 4px', transition: 'color 0.15s' },
      onMouseEnter: (e) => e.currentTarget.style.color = '#ef4444',
      onMouseLeave: (e) => e.currentTarget.style.color = '#4b5563' },
    React.createElement("i", { className: "fas fa-times", style: { fontSize: 10 } })
    )
    )
    ),
    config.showDeltaBar &&
    React.createElement("div", { style: {
        height: 6, display: 'flex', flexShrink: 0,
        background: '#06080a', position: 'relative', overflow: 'hidden'
      } },
    React.createElement("div", { style: {
        position: 'absolute', left: 0, top: 0, height: '100%',
        width: `${deltaBarMetrics.buyPct}%`,
        background: config.buyColor + '22',
        transition: 'width 0.5s ease'
      } }),
    React.createElement("div", { style: {
        position: 'absolute', right: 0, top: 0, height: '100%',
        width: `${100 - deltaBarMetrics.buyPct}%`,
        background: config.sellColor + '22',
        transition: 'width 0.5s ease'
      } }),
    React.createElement("div", { style: {
        width: `${rollingMomentum.buyPct}%`,
        background: rollingMomentum.deltaDir === 'buy' ?
        `linear-gradient(90deg, transparent, ${config.buyColor})` :
        config.buyColor + '11',
        transition: 'width 0.2s cubic-bezier(0.1, 0.7, 0.1, 1)',
        position: 'relative', zIndex: 2
      } },
    rollingMomentum.intensity > 0.4 &&
    React.createElement("div", { style: {
        position: 'absolute', inset: 0,
        background: 'white', opacity: 0.05,
        animation: 'momentumPulse 0.8s infinite alternate'
      } }),
    React.createElement("div", { style: {
        position: 'absolute', right: 0, top: 0, bottom: 0, width: 3,
        background: rollingMomentum.deltaDir === 'buy' ? config.buyColor :
        rollingMomentum.deltaDir === 'sell' ? config.sellColor :
        '#475569',
        boxShadow: rollingMomentum.deltaDir !== 'neutral' ?
        `0 0 10px ${rollingMomentum.deltaDir === 'buy' ? config.buyColor : config.sellColor}` :
        'none'
      } })
    ),
    React.createElement("div", { style: {
        flex: 1,
        background: rollingMomentum.deltaDir === 'sell' ?
        `linear-gradient(90deg, ${config.sellColor}, transparent)` :
        config.sellColor + '11',
        zIndex: 2
      } }),
    React.createElement("div", { style: {
        position: 'absolute', left: '50%', top: 0, bottom: 0,
        width: 1, background: 'rgba(255,255,255,0.1)', zIndex: 3
      } }),
    React.createElement("div", { style: {
        position: 'absolute', left: 0, right: 0, top: 0, bottom: 0,
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        pointerEvents: 'none', zIndex: 4
      } },
    React.createElement("span", { style: {
        fontSize: 7, fontFamily: 'monospace', fontWeight: 900,
        color: rollingMomentum.deltaDir !== 'neutral' ? '#fff' : 'rgba(255,255,255,0.4)',
        letterSpacing: '0.05em', textShadow: '0 0 2px rgba(0,0,0,1)'
      } },
    rollingMomentum.buyPct.toFixed(0), "% MOMENTUM"
    )
    )
    ),
    React.createElement("div", { style: {
        display: 'flex', background: 'rgba(0,0,0,0.3)',
        borderBottom: '1px solid rgba(255,255,255,0.06)',
        flexShrink: 0, userSelect: 'none'
      } },
    config.showTime && React.createElement("div", { style: headerCell(colWidths.time) }, "TIME", React.createElement(TapePanelResizer, { onResize: (w) => handleColumnResize('time', w) })),
    React.createElement("div", { style: headerCell(colWidths.price) }, "PRICE", React.createElement(TapePanelResizer, { onResize: (w) => handleColumnResize('price', w) })),
    React.createElement("div", { style: headerCell(colWidths.size) }, "SIZE", React.createElement(TapePanelResizer, { onResize: (w) => handleColumnResize('size', w) })),
    config.showDelta && React.createElement("div", { style: headerCell(colWidths.delta) }, "DELTA", React.createElement(TapePanelResizer, { onResize: (w) => handleColumnResize('delta', w) })),
    config.showTotal &&
    React.createElement("div", { style: headerCell(colWidths.total, true) },
    config.totalMode === 'exchange' ? 'VOL' :
    config.totalMode === 'delta' ? 'ΔVOL' :
    'SES',
    React.createElement(TapePanelResizer, { onResize: (w) => handleColumnResize('total', w) })
    )
    ),
    React.createElement("div", {
      style: { flex: 1, overflowY: 'auto', overflowX: 'hidden', background: '#080b0f' },
      className: "no-scrollbar" },
    trades.length === 0 &&
    React.createElement("div", { style: {
        padding: '16px 8px', textAlign: 'center',
        color: '#1e293b', fontSize: '10px',
        fontFamily: 'monospace', letterSpacing: '0.1em'
      } }, "WAITING FOR DATA..."
    ),
    trades.map((trade) => {
      const isBuy = trade.side === 'buy';
      const isSell = trade.side === 'sell';
      const isWhale = trade.size >= (config.whaleThreshold || 50);
      const priceColor = isBuy ? config.buyColor : isSell ? config.sellColor : config.neutralColor;
      const sizeRatio = trade.size / Math.max(forceBaseline, 1);
      const forcePct = Math.min(sizeRatio * 100, 100);
      const isSignificant = sizeRatio > 0.4;
      const isAggressive = sizeRatio > 0.85;
      const forceColor = isWhale ? config.whaleColor : priceColor;
      const barOpacity = isAggressive ? 0.35 : isSignificant ? 0.20 : 0.08;
      const borderColor = isWhale || isSignificant ? priceColor : `${priceColor}66`;
      const bgColor = isWhale ? 'rgba(217,119,6,0.08)' :
      isAggressive && isBuy ? 'rgba(5,150,105,0.06)' :
      isAggressive && isSell ? 'rgba(185,28,28,0.06)' :
      isBuy ? 'rgba(16,185,129,0.02)' :
      isSell ? 'rgba(239,68,68,0.02)' :
      'transparent';
      const tradeDelta = trade.sessionDelta ?? 0;
      return (
        React.createElement("div", {
          key: trade.id,
          style: {
            display: 'flex',
            height: config.rowHeight,
            borderLeft: `3px solid ${borderColor}`,
            background: bgColor,
            borderBottom: '1px solid rgba(255,255,255,0.02)',
            animation: isWhale ? 'tapeWhaleFlash 0.5s ease-out' : undefined
          } },
        config.showTime &&
        React.createElement("div", { style: dataCell(colWidths.time, { color: '#374151', fontSize: '9px' }) },
        formatTradeTime(trade.time)
        ),
        React.createElement("div", { style: dataCell(colWidths.price, { color: priceColor, fontWeight: 700 }) },
        formatPrice(trade.price)
        ),
        React.createElement("div", { style: { ...dataCell(colWidths.size), position: 'relative', overflow: 'hidden' } },
        React.createElement("div", { style: {
            position: 'absolute', left: 0, top: 1, bottom: 1,
            width: `${forcePct}%`,
            background: forceColor,
            opacity: barOpacity,
            borderRadius: '0 2px 2px 0',
            boxShadow: isAggressive ? `0 0 10px ${forceColor}44` : 'none'
          } }),
        React.createElement("span", { style: {
            position: 'relative', zIndex: 1,
            color: isWhale ? config.whaleColor :
            trade.size >= config.whaleThreshold / 2 ? '#e2e8f0' :
            '#9ca3af',
            fontWeight: isWhale ? 800 : 600
          } },
        formatSize(trade.size)
        )
        ),
        config.showDelta &&
        React.createElement("div", { style: dataCell(colWidths.delta, {
            color: tradeDelta > 0 ? config.buyColor :
            tradeDelta < 0 ? config.sellColor :
            config.neutralColor,
            fontWeight: 600, fontSize: '9px'
          }) },
        tradeDelta >= 0 ? '+' : '', formatVolume(tradeDelta)
        ),
        config.showTotal &&
        React.createElement("div", { style: dataCell(colWidths.total, { color: '#475569', fontWeight: 600, fontSize: '9px' }) },
        formatVolume(trade.cumulativeTotal)
        )
        ));
    })
    ),
    React.createElement("div", { style: {
        display: 'flex', justifyContent: 'space-between',
        padding: '2px 8px',
        background: 'rgba(0,0,0,0.4)',
        borderTop: '1px solid rgba(255,255,255,0.05)',
        flexShrink: 0, fontSize: '9px', color: '#374151', fontFamily: 'monospace'
      } },
    React.createElement("span", null,
    trades.length, " PRINTS",
    config.aggregationMs > 0 && ` · AGG ${config.aggregationMs}MS`,
    config.minSize > 0 && ` · MIN ${config.minSize}`,
    ` · P95 ${formatVolume(forceBaseline)}`
    ),
    React.createElement("span", { style: {
        color: deltaBarMetrics.deltaDir === 'buy' ? '#065f46' :
        deltaBarMetrics.deltaDir === 'sell' ? '#7f1d1d' :
        '#1e293b',
        fontWeight: 700
      } },
    deltaBarMetrics.buyPct.toFixed(1), "% BUY"
    )
    ),
    React.createElement("style", null, `
                @keyframes tapeWhaleFlash {
                    0%   { filter: brightness(2.5); }
                    40%  { filter: brightness(1.6); }
                    100% { filter: brightness(1);   }
                }
                @keyframes momentumPulse {
                    from { opacity: 0.1; }
                    to   { opacity: 0.3; }
                }
                .no-scrollbar::-webkit-scrollbar { display: none; }
                .no-scrollbar { -ms-overflow-style: none; scrollbar-width: none; }
            `),
    window.TapeConfigModal &&
    React.createElement(window.TapeConfigModal, {
      isOpen: isConfigOpen,
      onClose: () => setIsConfigOpen(false),
      config: config,
      onUpdate: setConfig,
      title: title }
    )
    ));
};
window.TapePanel = TapePanel;
