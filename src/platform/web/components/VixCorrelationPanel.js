function _extends() {return _extends = Object.assign ? Object.assign.bind() : function (n) {for (var e = 1; e < arguments.length; e++) {var t = arguments[e];for (var r in t) ({}).hasOwnProperty.call(t, r) && (n[r] = t[r]);}return n;}, _extends.apply(null, arguments);}
const VixCorrelationPanel = ({ activeSymbol, currentPrice, currentPriceTime, activeTimeframe = '5m', tickData }) => {
  const { useState, useEffect, useRef, useMemo, useCallback } = React;
  const chartContainerRef = useRef();
  const chartRef = useRef();
  const symbolSeriesRef = useRef();
  const vixSeriesRef = useRef();
  const overlayCanvasRef = useRef();
  const lastVixTimeRef = useRef(0);
  const vixFetchingRef = useRef(false);
  const liveVixPriceRef = useRef(null);
  const initialPriceRef = useRef(null);
  const initialVixRef = useRef(null);
  const timeOffsetRef = useRef(0);
  const lastDataTimeRef = useRef(0);
  const lastUpdateLocalTimeRef = useRef(Date.now());
  const primaryPriceRef = useRef(null);
  const currentPriceRef = useRef(null);
  const primaryManualRef = useRef(false);
  const secondaryManualRef = useRef(false);
  const [pos, setPos] = useState({ x: 100, y: 100 });
  const [dragging, setDragging] = useState(false);
  const dragRef = useRef(null);
  const offsetRef = useRef({ x: 0, y: 0 });
  const initializedRef = useRef(false);
  const primaryHistoryRef = useRef([]);
  const secondaryHistoryRef = useRef([]);
  const [vixValue, setVixValue] = useState(0);
  const [symbolChange, setSymbolChange] = useState(0);
  const [vixChange, setVixChange] = useState(0);
  const [correlation, setCorrelation] = useState(0);
  const [isLoading, setIsLoading] = useState(true);
  const [vixSignal, setVixSignal] = useState(null);
  const [vixHeartbeat, setVixHeartbeat] = useState(false);
  const [isMaximized, setIsMaximized] = useState(false);
  const [chartType, setChartType] = useState('line');
  const [primarySymbol, setPrimarySymbol] = useState(() => {
    try {return localStorage.getItem('vix_panel_primary_symbol') || activeSymbol || '';}
    catch {return activeSymbol || '';}
  });
  const [secondarySymbol, setSecondarySymbol] = useState(() => {
    try {return localStorage.getItem('vix_panel_secondary_symbol') || 'VIX';}
    catch {return 'VIX';}
  });
  const normalizeSymbol = (sym) => {
    if (!sym) return '';
    if (window.getUniversalSymbol) return window.getUniversalSymbol(sym);
    let s = String(sym).
    replace(/^[A-Z]+:/i, '').
    replace(/:[A-Z]+$/i, ''). // also strip suffix if window.getUniversalSymbol is missing
    trim().
    toUpperCase();
    return s;
  };
  const resolvedPrimarySymbol = normalizeSymbol(primarySymbol || activeSymbol || '');
  const resolvedSecondarySymbol = normalizeSymbol(secondarySymbol || 'VIX');
  const getTimeframeSeconds = useCallback((tf) => {
    if (!tf) return 300;
    const value = parseInt(tf) || 5;
    if (tf.includes("M") && !tf.includes("m")) return value * 2592000;
    if (tf.toLowerCase().includes("mn") || tf.toLowerCase().includes("mo")) return value * 2592000;
    if (tf.toLowerCase().includes("w")) return value * 604800;
    if (tf.toLowerCase().includes("d")) return value * 86400;
    if (tf.toLowerCase().includes("h")) return value * 3600;
    if (tf.includes("m")) return value * 60;
    if (tf.toLowerCase().includes("s")) return value;
    return 300;
  }, []);
  const tfSeconds = useMemo(() => {
    const s = getTimeframeSeconds(activeTimeframe);
    return Number.isFinite(s) && s > 0 ? s : 60;
  }, [activeTimeframe, getTimeframeSeconds]);
  const isVixSymbol = useCallback((symbol) => {
    if (!symbol) return false;
    return symbol.replace('^', '').toUpperCase() === 'VIX';
  }, []);
  const secondaryIsVix = useMemo(() => isVixSymbol(resolvedSecondarySymbol), [resolvedSecondarySymbol, isVixSymbol]);
  const availableSymbols = useMemo(() => {
    const keys = Object.keys(tickData || {});
    const list = keys.length ? [...keys] : [];
    if (activeSymbol && !list.includes(activeSymbol)) list.push(activeSymbol);
    if (!list.includes('VIX')) list.push('VIX');
    return list.map(normalizeSymbol).sort();
  }, [tickData, activeSymbol]);
  const primaryTick = useMemo(() => {
    if (!tickData) return null;
    if (tickData[activeSymbol]) return tickData[activeSymbol];
    if (tickData[resolvedPrimarySymbol]) return tickData[resolvedPrimarySymbol];
    const matchKey = Object.keys(tickData).find((k) => normalizeSymbol(k) === resolvedPrimarySymbol);
    return matchKey ? tickData[matchKey] : null;
  }, [tickData, activeSymbol, resolvedPrimarySymbol]);
  const primaryPrice = Number.isFinite(primaryTick?.last) ? primaryTick.last : currentPrice;
  // Keep refs updated for polling callback access without reactive deps
  primaryPriceRef.current = primaryPrice;
  currentPriceRef.current = currentPrice;
  const FEAR_ZONES = [
  { max: 15, color: 'rgba(34,197,94,0.18)', label: 'Calm', textColor: '#22c55e' },
  { max: 25, color: 'rgba(234,179,8,0.18)', label: 'Caution', textColor: '#eab308' },
  { max: 35, color: 'rgba(249,115,22,0.18)', label: 'Fear', textColor: '#f97316' },
  { max: Infinity, color: 'rgba(239,68,68,0.22)', label: 'Panic', textColor: '#ef4444' }];
  const getVixZoneColor = (v) => {
    if (v < 15) return '#22c55e';
    if (v < 25) return '#eab308';
    if (v < 35) return '#f97316';
    return '#ef4444';
  };
  const calculateVixSignal = (currentVix, currentPrice, symMom, vixMom, corr, vixSpike) => {
    if (!currentVix || !currentPrice || isNaN(symMom) || isNaN(vixMom) || isNaN(corr)) return null;
    let signal = null, confidence = 0, reason = '';
    
    const isHighVol = currentVix >= 18;
    const isLowVol = currentVix <= 13.5;
    
    // 1. Fear Climax (Capitulation)
    if (isHighVol && vixMom > 0 && symMom < 0) {
      confidence = Math.min(98, Math.abs(vixMom) * 5 + Math.abs(symMom) * 3 + (vixSpike ? 20 : 0));
      if (confidence > 60) {
          signal = 'BUY';
          reason = `🚨 Capitulation Alert: VIX spiking to ${currentVix.toFixed(1)} (+${vixMom.toFixed(2)}%) against price drop (${symMom.toFixed(2)}%). High probability of a sharp reversal/bounce.`;
      }
    } 
    // 2. Complacency Peak (Exhaustion)
    else if (isLowVol && vixMom < 0 && symMom > 0 && Math.abs(vixMom) > 0.2) {
      confidence = Math.min(95, Math.abs(vixMom) * 4 + symMom * 2);
      if (confidence > 60) {
          signal = 'SELL';
          reason = `⚠️ Complacency Peak: VIX extremely low at ${currentVix.toFixed(1)} (-${Math.abs(vixMom).toFixed(2)}%) while price extends (+${symMom.toFixed(2)}%). Uptrend exhaustion likely.`;
      }
    } 
    // 3. Correlation Divergences
    else if (Math.abs(corr) > 0.4 && Math.abs(symMom) > 0.2 && Math.abs(vixMom) > 0.2) {
      confidence = Math.min(90, 50 + Math.abs(symMom) * 10 + Math.abs(vixMom) * 8);
      if (confidence > 60) {
        if (corr < -0.6) {
          // Normal negative correlation acting as support/resistance confirmation
          if (vixMom > 0 && symMom < 0) { 
              signal = 'BUY'; 
              reason = '📉 Negative Correlation: Rising VIX confirming local bottom formation.'; 
          } else if (vixMom < 0 && symMom > 0) { 
              signal = 'SELL'; 
              reason = '📈 Negative Correlation: Falling VIX confirming local top formation.'; 
          }
        } else if (corr > 0.5) {
          // Dangerous Positive Correlation (both rising or both falling)
          if (symMom > 0 && vixMom > 0) { 
              signal = 'SELL'; 
              reason = '🧨 Bearish Divergence: Price rising BUT VIX is also rising. Institutional hedging detected. High risk of dump.'; 
              confidence += 10;
          } else if (symMom < 0 && vixMom < 0) {
              signal = 'BUY';
              reason = '🛡️ Bullish Divergence: Price falling BUT VIX is also falling. Selling pressure lacks conviction. Potential trap.';
              confidence += 10;
          }
        }
      }
    } 
    // 4. Pure Volatility Spike
    else if (vixSpike && isHighVol) {
      confidence = 80; 
      signal = 'BUY';
      reason = `⚡ Volatility Shock: Sudden VIX spike to ${currentVix.toFixed(1)}. Market makers adjusting pricing, often precedes a violent bounce.`;
    }

    return signal && confidence >= 60 ? { type: signal, reason, confidence: Math.min(99, Math.round(confidence)) } : null;
  };
  const parseTime = (t) => {
    if (!t) return Math.floor(Date.now() / 1000);
    if (typeof t === 'number') {
      if (isNaN(t)) return Math.floor(Date.now() / 1000);
      return t > 10000000000 ? Math.floor(t / 1000) : t;
    }
    let s = String(t).replace(' ', 'T');
    if (!s.endsWith('Z') && !s.includes('+')) s += 'Z';
    const d = new Date(s);
    const ts = Math.floor(d.getTime() / 1000);
    return isNaN(ts) ? Math.floor(Date.now() / 1000) : ts;
  };
  const forwardFillVix = (lineDataSym, lineDataVix) => {
    if (!lineDataVix.length || !lineDataSym.length) return lineDataVix;
    const vixMap = new Map(lineDataVix.map((d) => [d.time, d.value]));
    const filled = [];
    let lastVal = lineDataVix[0].value;
    for (const sp of lineDataSym) {
      if (vixMap.has(sp.time)) lastVal = vixMap.get(sp.time);
      if (sp.time <= lineDataVix[lineDataVix.length - 1].time) {
        filled.push({ time: sp.time, value: lastVal });
      }
    }
    return filled;
  };
  useEffect(() => {
    if (!primaryManualRef.current && activeSymbol && activeSymbol !== primarySymbol) {
      setPrimarySymbol(activeSymbol);
    }
  }, [activeSymbol, primarySymbol]);

  useEffect(() => {
    if (!isMaximized) {
        initializedRef.current = false;
        return;
    }
    if (initializedRef.current) return;
    const defaultPos = {
      x: Math.max(24, (window.innerWidth - 900) / 2),
      y: Math.max(24, (window.innerHeight - 520) / 2)
    };
    setPos(defaultPos);
    initializedRef.current = true;
  }, [isMaximized]);

  const handleMouseDown = (e) => {
    if (!isMaximized) return;
    if (!e.target.closest('.drag-handle')) return;
    const targetTag = e.target.tagName.toLowerCase();
    if (targetTag === 'button' || targetTag === 'input' || targetTag === 'textarea' || e.target.closest('button')) {
      return;
    }
    e.preventDefault();
    setDragging(true);
    const rect = dragRef.current.getBoundingClientRect();
    offsetRef.current = { x: e.clientX - rect.left, y: e.clientY - rect.top };
  };

  useEffect(() => {
    if (!dragging) return;
    const move = (e) => {
      setPos({
        x: Math.max(0, e.clientX - offsetRef.current.x),
        y: Math.max(0, e.clientY - offsetRef.current.y)
      });
    };
    const stop = () => setDragging(false);
    window.addEventListener('mousemove', move, true);
    window.addEventListener('mouseup', stop, true);
    return () => {
      window.removeEventListener('mousemove', move, true);
      window.removeEventListener('mouseup', stop, true);
    };
  }, [dragging]);

  useEffect(() => {
    try {
      localStorage.setItem('vix_panel_primary_symbol', resolvedPrimarySymbol);
      localStorage.setItem('vix_panel_secondary_symbol', resolvedSecondarySymbol);
    } catch {}
  }, [resolvedPrimarySymbol, resolvedSecondarySymbol]);
  const drawSpectrumOverlay = useCallback((vixMin, vixMax) => {
    const canvas = overlayCanvasRef.current;
    const chart = chartRef.current;
    if (!canvas || !chart || chartType !== 'spectrum') return;
    const ctx = canvas.getContext('2d');
    const W = canvas.width;
    const H = canvas.height;
    ctx.clearRect(0, 0, W, H);
    const series = vixSeriesRef.current;
    if (!series) return;
    const zoneBreaks = [0, 15, 25, 35, vixMax + 5];
    const colors = [
    'rgba(34,197,94,0.13)',
    'rgba(234,179,8,0.13)',
    'rgba(249,115,22,0.13)',
    'rgba(239,68,68,0.17)'];
    const labels = ['CALM', 'CAUTION', 'FEAR', 'PANIC'];
    const lColors = ['#22c55e', '#eab308', '#f97316', '#ef4444'];
    for (let i = 0; i < 4; i++) {
      const priceHigh = zoneBreaks[i + 1];
      const priceLow = zoneBreaks[i];
      try {
        const yTop = series.priceToCoordinate(priceHigh);
        const yBot = series.priceToCoordinate(priceLow);
        if (yTop === null || yBot === null) continue;
        const top = Math.max(0, Math.min(H, Math.round(Math.min(yTop, yBot))));
        const bot = Math.max(0, Math.min(H, Math.round(Math.max(yTop, yBot))));
        const ht = Math.max(1, bot - top);
        ctx.fillStyle = colors[i];
        ctx.fillRect(0, top, W, ht);
        ctx.font = '9px ui-monospace, Consolas, monospace';
        ctx.fillStyle = lColors[i];
        ctx.textAlign = 'right';
        ctx.textBaseline = 'middle';
        ctx.globalAlpha = 0.7;
        ctx.fillText(labels[i], W - 4, top + ht / 2);
        ctx.globalAlpha = 1;
      } catch (_) {}
    }
  }, [chartType]);
  useEffect(() => {
    let isMounted = true;
    if (!chartContainerRef.current) return;
    const _cw = chartContainerRef.current.clientWidth;
    const _ch = chartContainerRef.current.clientHeight;
    const _safeW = Math.max(_cw, 200);
    const _safeH = isMaximized ? Math.max(_ch - 60, 80) : 140;
    const chart = LightweightCharts.createChart(chartContainerRef.current, {
      layout: {
        background: { type: 'solid', color: '#111111' },
        textColor: '#64748b'
      },
      grid: {
        vertLines: { visible: false },
        horzLines: { color: '#1a1a1a', style: 1 }
      },
      width: _safeW,
      height: _safeH,
      timeScale: {
        timeVisible: true, borderVisible: false, secondsVisible: false,
        rightOffset: 10, lockVisibleTimeRangeOnResize: true, minBarSpacing: 0.5
      },
      rightPriceScale: {
        visible: true, borderVisible: false,
        scaleMargins: { top: 0.05, bottom: 0.05 }
      },
      leftPriceScale: {
        visible: true, borderVisible: false,
        scaleMargins: { top: 0.1, bottom: 0.1 }
      },
      crosshair: {
        mode: LightweightCharts.CrosshairMode.Normal,
        horzLine: { visible: true, labelVisible: true, color: '#555', style: 2 },
        vertLine: { visible: true, labelVisible: true, color: '#555', style: 2 }
      },
      handleScroll: {
        mouseWheel: true, pressedMouseMove: true,
        horzTouchDrag: true, vertTouchDrag: true, kineticScroll: true
      },
      handleScale: {
        axisPressedMouseMove: true, axisRightMouseDown: true,
        mouseWheel: true, pinch: true
      },
      watermark: {
        visible: false
      }
    });
    const symbolSeries = chart.addLineSeries({
      color: '#22d3ee',
      lineWidth: 2,
      priceScaleId: 'right',
      lastValueVisible: true,
      priceLineVisible: true,
      crosshairMarkerVisible: true,
      crosshairMarkerRadius: 4
    });
    let vixSeries;
    if (chartType === 'area') {
      vixSeries = chart.addAreaSeries({
        lineColor: '#f97316',
        topColor: 'rgba(249,115,22,0.35)',
        bottomColor: 'rgba(249,115,22,0.02)',
        lineWidth: 2,
        priceScaleId: 'left',
        lastValueVisible: true,
        priceLineVisible: true,
        crosshairMarkerVisible: true,
        crosshairMarkerRadius: 4
      });
    } else if (chartType === 'spectrum') {
      vixSeries = chart.addHistogramSeries({
        priceScaleId: 'left',
        lastValueVisible: true,
        priceLineVisible: false,
        base: 0
      });
    } else {
      vixSeries = chart.addLineSeries({
        color: '#f97316',
        lineWidth: 2,
        priceScaleId: 'left',
        lastValueVisible: true,
        priceLineVisible: true,
        crosshairMarkerVisible: true,
        crosshairMarkerRadius: 4
      });
    }
    chartRef.current = chart;
    symbolSeriesRef.current = symbolSeries;
    vixSeriesRef.current = vixSeries;
    if (chartType === 'spectrum' && overlayCanvasRef.current) {
      const el = overlayCanvasRef.current;
      const dpr = window.devicePixelRatio || 1;
      el.width = chartContainerRef.current.clientWidth * dpr | 0;
      el.height = chartContainerRef.current.clientHeight * dpr | 0;
      el.style.width = `${chartContainerRef.current.clientWidth}px`;
      el.style.height = `${chartContainerRef.current.clientHeight}px`;
      const ctx2 = el.getContext('2d');
      ctx2.setTransform(dpr, 0, 0, dpr, 0, 0);
    }
    const loadData = async (retryCount = 0) => {
      try {
        if (!isMounted || !resolvedPrimarySymbol) return;
        const resSym = await fetch(
          `/api/history?symbol=${encodeURIComponent(resolvedPrimarySymbol)}&timeframe=${activeTimeframe}&limit=200`
        );
        if (!resSym.ok) throw new Error(`Symbol history: ${resSym.status}`);
        const dataSym = await resSym.json();
        if (!isMounted) return;
        let rawSecondary = [];
        if (secondaryIsVix) {
          try {
            const r = await fetch(`/api/vix?timeframe=${activeTimeframe}&limit=200`);
            if (r.ok) {
              const j = await r.json();
              if (Array.isArray(j)) rawSecondary = j.map((d) => ({ time: d.time, value: d.Close }));
            }
          } catch (_) {}
        } else {
          try {
            const r = await fetch(
              `/api/history?symbol=${encodeURIComponent(resolvedSecondarySymbol)}&timeframe=${activeTimeframe}&limit=200`
            );
            if (r.ok) {
              const j = await r.json();
              if (Array.isArray(j)) rawSecondary = j.map((d) => ({ time: d.time, value: d.Close }));
            }
          } catch (_) {}
        }
        if (!isMounted) return;
        if (rawSecondary.length === 0) {
          if (retryCount < 3 && isMounted) setTimeout(() => loadData(retryCount + 1), 2000);else
          setIsLoading(false);
          return;
        }
        const symAgg = {};
        if (Array.isArray(dataSym)) {
          dataSym.forEach((d) => {
            const pt = parseTime(d.time);
            const aligned = Math.floor(pt / tfSeconds) * tfSeconds;
            const val = Number(d.Close || d.value || 0);
            if (Number.isFinite(val)) symAgg[aligned] = val;
          });
        }
        const lineDataSym = Object.keys(symAgg).
        map((t) => parseInt(t)).
        sort((a, b) => a - b).
        filter((t) => !isNaN(t)).
        map((t) => {
          if (t > lastDataTimeRef.current) lastDataTimeRef.current = t;
          return { time: t, value: symAgg[t] };
        });
        lastUpdateLocalTimeRef.current = Date.now();
        let offset = 0;
        if (secondaryIsVix && lineDataSym.length > 0 && rawSecondary.length > 0) {
          const lastSymT = lineDataSym[lineDataSym.length - 1].time;
          const lastVixT = parseTime(rawSecondary[rawSecondary.length - 1].time);
          const rawOffset = lastSymT - lastVixT;
          // Aumentar el límite de desfase a 12 horas (43200s) para soportar más zonas horarias
          offset = Math.abs(rawOffset) > 30 && Math.abs(rawOffset) <= 43200 ? rawOffset : 0;
        }
        timeOffsetRef.current = offset;
        const vixAgg = {};
        rawSecondary.forEach((d) => {
          const rawVal = Number(d.value ?? d.Close);
          if (!Number.isFinite(rawVal) || rawVal <= 0 || rawVal >= 200) return;
          const adjustedTime = parseTime(d.time) + offset;
          const aligned = Math.floor(adjustedTime / tfSeconds) * tfSeconds;
          vixAgg[aligned] = rawVal;
        });
        let lineDataVix = Object.keys(vixAgg).
        map((t) => parseInt(t)).
        sort((a, b) => a - b).
        filter((t) => !isNaN(t)).
        map((t) => ({ time: t, value: vixAgg[t] }));
        // Removed forwardFillVix to prevent line deformity

        if (!isMounted) return;
        const finalLineDataSym = lineDataSym.filter((d) => Number.isFinite(d.time) && Number.isFinite(d.value));
        if (finalLineDataSym.length > 0) {
          try {symbolSeries.setData(finalLineDataSym);} catch (err) {console.error("LWC symbol error:", err);}
        }
        const finalLineDataVix = lineDataVix.filter((d) => Number.isFinite(d.time) && Number.isFinite(d.value));
        if (finalLineDataVix.length > 0) {
          if (chartType === 'spectrum') {
            const coloredVix = lineDataVix.map((d) => ({
              time: d.time,
              value: d.value,
              color: getVixZoneColor(d.value)
            })).filter((d) => Number.isFinite(d.time) && Number.isFinite(d.value));
            try {vixSeries.setData(coloredVix);} catch (err) {console.error("LWC vix error:", err);}
            const vixMin = Math.min(...lineDataVix.map((d) => d.value));
            const vixMax = Math.max(...lineDataVix.map((d) => d.value));
            setTimeout(() => drawSpectrumOverlay(vixMin, vixMax), 80);
          } else {
            try {vixSeries.setData(finalLineDataVix);} catch (err) {console.error("LWC vix error:", err);}
          }
        }
        if (lineDataSym.length > 0) {
          try {
            chart.timeScale().setVisibleRange({
              from: lineDataSym[0].time,
              to: lineDataSym[lineDataSym.length - 1].time + tfSeconds * 2
            });
          } catch (_) {chart.timeScale().fitContent();}
        }
        setIsLoading(false);
        primaryHistoryRef.current = lineDataSym;
        secondaryHistoryRef.current = lineDataVix;
        recalculateCorrelation();
      } catch (e) {
        if (retryCount < 3 && isMounted) setTimeout(() => loadData(retryCount + 1), 2000);else
        setIsLoading(false);
      }
    };

    const recalculateCorrelation = () => {
      const lineDataSym = primaryHistoryRef.current;
      const lineDataVix = secondaryHistoryRef.current;
      if (!lineDataSym.length || !lineDataVix.length) return;

      const SYM_W = Math.min(20, lineDataSym.length);
      const recentSym = lineDataSym.slice(-SYM_W);
      const lastSym = recentSym[recentSym.length - 1].value;
      const refSym = recentSym[0].value;
      setSymbolChange(refSym > 0 ? (lastSym - refSym) / refSym * 100 : 0);
      initialPriceRef.current = refSym;

      const VIX_W = Math.min(20, lineDataVix.length);
      const recentVix = lineDataVix.slice(-VIX_W);
      const lastVix = recentVix[recentVix.length - 1].value;
      const refVix = recentVix[0].value;
      if (!Number.isFinite(lastVix) || !Number.isFinite(refVix) || refVix <= 0) return;
      
      setVixChange((lastVix - refVix) / refVix * 100);
      setVixValue(lastVix);
      liveVixPriceRef.current = lastVix;
      initialVixRef.current = refVix;
      lastVixTimeRef.current = lineDataVix[lineDataVix.length - 1].time;

      const corrWindow = Math.min(40, lineDataSym.length, lineDataVix.length);
      const vixMap2 = new Map(lineDataVix.map((d) => [d.time, d.value]));
      const alignedS = [], alignedV = [];
      
      lineDataSym.slice(-corrWindow).forEach((sp) => {
        let best = null, bestDist = tfSeconds * 2;
        // Optimized lookup: try exact match first
        if (vixMap2.has(sp.time)) {
          best = vixMap2.get(sp.time);
        } else {
          for (const [vt, vv] of vixMap2) {
            const dist = Math.abs(vt - sp.time);
            if (dist < bestDist) { bestDist = dist; best = vv; }
          }
        }
        if (best !== null) { alignedS.push(sp.value); alignedV.push(best); }
      });

      const corrN = alignedS.length;
      if (corrN > 3) {
        const returnsS = [], returnsV = [];
        for (let i = 1; i < corrN; i++) {
          if (alignedS[i - 1] !== 0 && alignedV[i - 1] !== 0) {
            returnsS.push((alignedS[i] - alignedS[i - 1]) / alignedS[i - 1]);
            returnsV.push((alignedV[i] - alignedV[i - 1]) / alignedV[i - 1]);
          }
        }

        const n = returnsS.length;
        let finalCorr = 0;
        if (n > 2) {
          const meanX = returnsS.reduce((a, b) => a + b, 0) / n;
          const meanY = returnsV.reduce((a, b) => a + b, 0) / n;
          let num = 0, denX = 0, denY = 0;
          for (let i = 0; i < n; i++) {
            const dx = returnsS[i] - meanX, dy = returnsV[i] - meanY;
            num += dx * dy; denX += dx * dx; denY += dy * dy;
          }
          const denominator = Math.sqrt(denX) * Math.sqrt(denY);
          finalCorr = denominator === 0 ? 0 : num / denominator;
        }

        // Fallback to price correlation if returns correlation is 0 or not enough data
        if (finalCorr === 0) {
          const meanX = alignedS.reduce((a, b) => a + b, 0) / corrN;
          const meanY = alignedV.reduce((a, b) => a + b, 0) / corrN;
          let num = 0, denX = 0, denY = 0;
          for (let i = 0; i < corrN; i++) {
            const dx = alignedS[i] - meanX, dy = alignedV[i] - meanY;
            num += dx * dy; denX += dx * dx; denY += dy * dy;
          }
          const denominator = Math.sqrt(denX) * Math.sqrt(denY);
          finalCorr = denominator === 0 ? 0 : num / denominator;
        }
        
        setCorrelation(finalCorr);

        if (secondaryIsVix) {
          const MOM = 10;
          const symM = lineDataSym.slice(-MOM);
          const vixM = lineDataVix.slice(-MOM);
          const symMom = symM.length > 1 ? (symM[symM.length - 1].value - symM[0].value) / symM[0].value * 100 : 0;
          const vixMom = vixM.length > 1 ? (vixM[vixM.length - 1].value - vixM[0].value) / vixM[0].value * 100 : 0;
          const vixSpike = vixM.length > 1 && vixM[vixM.length - 1].value - vixM[vixM.length - 2].value > 2;
          setVixSignal(calculateVixSignal(lastVix, lastSym, symMom, vixMom, finalCorr, vixSpike));
        } else {
          setVixSignal(null);
        }
      }
    };
    setIsLoading(true);
    loadData();
    const failSafe = setTimeout(() => {if (isMounted) setIsLoading(false);}, 10000);
    const resizeObs = new ResizeObserver(() => {
      if (chartContainerRef.current) {
        chart.resize(
          chartContainerRef.current.clientWidth,
          chartContainerRef.current.clientHeight
        );
      }
    });
    resizeObs.observe(chartContainerRef.current);
    return () => {
      isMounted = false;
      resizeObs.disconnect();
      clearTimeout(failSafe);
      if (chartRef.current) {chartRef.current.remove();chartRef.current = null;}
      symbolSeriesRef.current = null;
      vixSeriesRef.current = null;
    };
  }, [resolvedPrimarySymbol, resolvedSecondarySymbol, activeTimeframe, secondaryIsVix, isMaximized, chartType]);
  useEffect(() => {
    if (!symbolSeriesRef.current) return;
    let primaryTime = primaryTick?.time ?? currentPriceTime;
    if (typeof primaryTime === 'number' && primaryTime > 10000000000) primaryTime = Math.floor(primaryTime / 1000);
    let roundedTime;
    if (primaryTime) {
      roundedTime = Math.floor(primaryTime / tfSeconds) * tfSeconds;
      if (lastDataTimeRef.current && roundedTime < lastDataTimeRef.current) roundedTime = lastDataTimeRef.current;
    } else if (lastDataTimeRef.current) {
      const elapsed = Math.floor((Date.now() - lastUpdateLocalTimeRef.current) / 1000);
      roundedTime = Math.floor((lastDataTimeRef.current + elapsed) / tfSeconds) * tfSeconds;
    } else {
      roundedTime = Math.floor(Date.now() / 1000 / tfSeconds) * tfSeconds;
    }
    if (Number.isFinite(primaryPrice) && Number.isFinite(roundedTime)) {
      try {
        symbolSeriesRef.current.update({ time: roundedTime, value: primaryPrice });
        const history = primaryHistoryRef.current;
        if (!history.length || history[history.length - 1].time !== roundedTime) {
          history.push({ time: roundedTime, value: primaryPrice });
          if (history.length > 500) history.shift();
        } else {
          history[history.length - 1].value = primaryPrice;
        }
        recalculateCorrelation();
      } catch (_) {}
    }
    if (Number.isFinite(roundedTime) && roundedTime > (lastDataTimeRef.current || 0)) {
      lastDataTimeRef.current = roundedTime;
    }
    if (vixSeriesRef.current) {
      const secondaryTick = tickData?.[resolvedSecondarySymbol] || tickData?.[secondarySymbol];
      const secondaryPrice = secondaryIsVix ? vixValue : secondaryTick?.last;
      const canUpdate = secondaryIsVix ?
      Number.isFinite(secondaryPrice) && secondaryPrice > 0 :
      Number.isFinite(secondaryPrice);
      if (canUpdate && Number.isFinite(roundedTime) && roundedTime >= (lastVixTimeRef.current || 0)) {
        const updatePayload = chartType === 'spectrum' ?
        { time: roundedTime, value: secondaryPrice, color: getVixZoneColor(secondaryPrice) } :
        { time: roundedTime, value: secondaryPrice };
        if (Number.isFinite(updatePayload.time) && Number.isFinite(updatePayload.value)) {
          try {
            vixSeriesRef.current.update(updatePayload);
            const history = secondaryHistoryRef.current;
            if (!history.length || history[history.length - 1].time !== updatePayload.time) {
              history.push({ time: updatePayload.time, value: updatePayload.value });
              if (history.length > 500) history.shift();
            } else {
              history[history.length - 1].value = updatePayload.value;
            }
          } catch (_) {}
          lastVixTimeRef.current = roundedTime;
        }
        if (!secondaryIsVix && initialVixRef.current > 0) {
          setVixChange((secondaryPrice - initialVixRef.current) / initialVixRef.current * 100);
          setVixValue(secondaryPrice);
        }
      }
    }
  }, [currentPrice, currentPriceTime, vixValue, resolvedPrimarySymbol, resolvedSecondarySymbol, tickData, secondaryIsVix, chartType]);
  useEffect(() => {
    if (!secondaryIsVix) return;
    const pollLive = async () => {
      if (!chartRef.current || vixFetchingRef.current) return;
      vixFetchingRef.current = true;
      try {
        const res = await fetch('/api/vix/live');
        if (!res.ok) return;
        const data = await res.json();
        const lv = data?.vix;
        if (!Number.isFinite(lv) || lv <= 0) return;
        liveVixPriceRef.current = lv;
        setVixValue(lv);
        setVixHeartbeat(h => !h);
        if (initialVixRef.current > 0) {
          setVixChange((lv - initialVixRef.current) / initialVixRef.current * 100);
        }
        // Update chart series directly — don't depend on React re-render
          if (vixSeriesRef.current) {
            const nowSec = Math.floor(Date.now() / 1000);
            const alignedNow = Math.floor(nowSec / tfSeconds) * tfSeconds;
            const safeTime = (lastVixTimeRef.current > 0 && alignedNow >= lastVixTimeRef.current) ?
            alignedNow :
            (lastVixTimeRef.current > 0 ? lastVixTimeRef.current : alignedNow);
            const payload = chartType === 'spectrum' ?
            { time: safeTime, value: lv, color: getVixZoneColor(lv) } :
            { time: safeTime, value: lv };
            try {
              vixSeriesRef.current.update(payload);
              const history = secondaryHistoryRef.current;
              if (!history.length || history[history.length - 1].time !== payload.time) {
                history.push({ time: payload.time, value: payload.value });
                if (history.length > 500) history.shift();
              } else {
                history[history.length - 1].value = payload.value;
              }
            } catch (_) {}
            lastVixTimeRef.current = safeTime;
            const pp = primaryPriceRef.current ?? currentPriceRef.current;
            if (symbolSeriesRef.current && Number.isFinite(pp)) {
              if (safeTime >= (lastDataTimeRef.current || 0)) {
                try {
                  symbolSeriesRef.current.update({ time: safeTime, value: pp });
                  const sHistory = primaryHistoryRef.current;
                  if (!sHistory.length || sHistory[sHistory.length - 1].time !== safeTime) {
                    sHistory.push({ time: safeTime, value: pp });
                    if (sHistory.length > 500) sHistory.shift();
                  } else {
                    sHistory[sHistory.length - 1].value = pp;
                  }
                } catch (_) {}
                lastDataTimeRef.current = safeTime;
              }
            }
            recalculateCorrelation();
          }
      } catch (_) {} finally
      {vixFetchingRef.current = false;}
    };
    pollLive();
    const iv = setInterval(pollLive, 1000);
    return () => clearInterval(iv);
  }, [secondaryIsVix, tfSeconds, chartType]);
  const ChartTypeToggle = () => {
    const types = [
    { key: 'line', icon: 'fa-chart-line', label: 'Line' },
    { key: 'area', icon: 'fa-chart-area', label: 'Area' },
    { key: 'spectrum', icon: 'fa-layer-group', label: 'Spectrum' }];
    return (
      React.createElement("div", { className: "flex items-center gap-1 bg-black/40 border border-white/10 rounded p-1 relative z-50" },
      types.map(({ key, icon, label }) =>
      React.createElement("button", {
        key: key,
        onClick: () => setChartType(key),
        title: label,
        className: `flex items-center gap-1.5 px-3 py-1.5 rounded cursor-pointer text-[10px] font-bold transition-all ${chartType === key ?
        'bg-cyan-500/20 text-cyan-400 border border-cyan-500/40' :
        'text-muted hover:text-white hover:bg-white/5'}` },
      React.createElement("i", { className: `fas ${icon} text-[11px]` }),
      React.createElement("span", { className: "hidden sm:inline" }, label)
      )
      )
      ));
  };
  const SpectrumLegend = () => chartType !== 'spectrum' ? null :
  React.createElement("div", { className: "flex items-center gap-2 px-1 mb-1" },
  [
  { label: '< 15 Calm', color: '#22c55e' },
  { label: '15-25 Caution', color: '#eab308' },
  { label: '25-35 Fear', color: '#f97316' },
  { label: '35+ Panic', color: '#ef4444' }].
  map((z) =>
  React.createElement("div", { key: z.label, className: "flex items-center gap-0.5" },
  React.createElement("div", { className: "w-1.5 h-1.5 rounded-sm", style: { backgroundColor: z.color } }),
  React.createElement("span", { className: "text-[8px]", style: { color: z.color } }, z.label)
  )
  )
  );
  const panelContent =
  React.createElement("div", { 
    ref: isMaximized ? dragRef : null,
    onMouseDown: handleMouseDown,
    style: isMaximized ? { position: 'absolute', left: `${pos.x}px`, top: `${pos.y}px`, width: '900px', height: '520px' } : undefined,
    className: `relative flex flex-col bg-panel border-t border-border p-2 shrink-0 transition-none ${isMaximized ?
    'z-[2000000] pointer-events-auto shadow-2xl rounded-lg border border-border bg-black/95' :
    'h-52 duration-300 transition-all'}` },
  React.createElement("style", null, `
    .tv-embed-widget-wrapper__footer,
    .tradingview-widget-copyright,
    a[href*="tradingview.com"],
    [class*="tv-watermark"],
    [class*="tv-logo"],
    div[class*="tv-logo"],
    div[class*="tradingview-logo"] {
        display: none !important;
        visibility: hidden !important;
        opacity: 0 !important;
        pointer-events: none !important;
        height: 0 !important;
        width: 0 !important;
        overflow: hidden !important;
    }
  `),
  isLoading &&
  React.createElement("div", { className: "absolute inset-0 bg-black/40 z-10 rounded grid place-items-center" },
  React.createElement("div", { className: "flex items-center justify-center gap-1" },
  React.createElement("span", { className: "text-[10px] text-cyan-400 animate-pulse flex items-center gap-1 whitespace-nowrap" },
  React.createElement("i", { className: "fas fa-circle-notch fa-spin text-xs" }), " Cargando..."
  )
  )
  ),
  React.createElement("div", { className: `flex justify-between items-start mb-1 ${isMaximized ? 'drag-handle cursor-move' : ''}` },
  React.createElement("div", { className: "flex items-center gap-2" },
  React.createElement("div", { className: "flex flex-col" },
  React.createElement("h3", { className: "text-[10px] font-bold text-muted uppercase tracking-wider flex items-center gap-1" },
  React.createElement("i", { className: "fas fa-chart-line text-cyan-400" }),
  resolvedPrimarySymbol || '---', " vs ", resolvedSecondarySymbol || '---'
  ),
  React.createElement("span", { className: "text-[9px] text-muted" }, "Correlaci\xF3n")
  ),
  isMaximized &&
  React.createElement("div", { className: "flex items-center gap-2 mt-1" },
  React.createElement("div", { className: "flex items-center gap-1" },
  React.createElement("span", { className: "text-[8px] text-muted" }, "A"),
  React.createElement("input", { value: resolvedPrimarySymbol,
    onChange: (e) => {primaryManualRef.current = true;setPrimarySymbol(e.target.value.toUpperCase());},
    className: "bg-black/40 border border-white/10 text-[9px] text-white px-2 py-0.5 rounded w-20",
    list: "vix_pair_symbols" }
  )
  ),
  React.createElement("div", { className: "flex items-center gap-1" },
  React.createElement("span", { className: "text-[8px] text-muted" }, "B"),
  React.createElement("input", { value: resolvedSecondarySymbol,
    onChange: (e) => {secondaryManualRef.current = true;setSecondarySymbol(e.target.value.toUpperCase());},
    className: "bg-black/40 border border-white/10 text-[9px] text-white px-2 py-0.5 rounded w-20",
    list: "vix_pair_symbols" }
  )
  ),
  React.createElement("datalist", { id: "vix_pair_symbols" },
  availableSymbols.map((s) => React.createElement("option", { key: s, value: s }))
  )
  ),
  React.createElement("button", { onClick: () => setIsMaximized(!isMaximized),
    className: "text-muted hover:text-white transition-colors",
    title: isMaximized ? 'Restore' : 'Maximize' },
  React.createElement("i", { className: `fas ${isMaximized ? 'fa-compress' : 'fa-expand'} text-xs` })
  )
  ),
  React.createElement("div", { className: "flex items-center gap-3" },
  isMaximized && React.createElement(ChartTypeToggle, null),
  React.createElement("div", { className: "flex flex-col items-end leading-none" },
  React.createElement("div", { className: "flex items-center gap-1" },
  React.createElement("div", { className: `w-2 h-2 rounded-full transition-opacity duration-500 shadow-[0_0_8px_rgba(0,0,0,0.5)] ${vixHeartbeat ? 'opacity-100 scale-110 shadow-[0_0_10px_currentcolor]' : 'opacity-40 scale-100'}`,
    style: { backgroundColor: chartType === 'spectrum' ? getVixZoneColor(vixValue) : '#f97316' } }),
  React.createElement("span", { className: "text-[10px] text-muted" }, resolvedSecondarySymbol || '---')
  ),
  React.createElement("span", { className: "text-[14px] font-bold",
    style: { color: chartType === 'spectrum' ? getVixZoneColor(vixValue) : '#fb923c' } },
  Number.isFinite(vixValue) ? vixValue.toFixed(2) : '---'
  ),
  React.createElement("span", { className: `text-[10px] font-mono ${vixChange >= 0 ? 'text-red-400' : 'text-green-400'}` },
  vixChange >= 0 ? '↑' : '↓', " ", Math.abs(vixChange).toFixed(2), "%"
  )
  ),
  React.createElement("div", { className: "flex flex-col items-end leading-none" },
  React.createElement("div", { className: "flex items-center gap-1" },
  React.createElement("div", { className: "w-2 h-2 rounded-full bg-cyan-400" }),
  React.createElement("span", { className: "text-[10px] text-muted" }, resolvedPrimarySymbol || '---')
  ),
  React.createElement("span", { className: "text-[14px] font-bold text-cyan-400" },
  Number.isFinite(primaryPrice) ? primaryPrice.toFixed(2) : '---'
  ),
  React.createElement("span", { className: `text-[10px] font-mono ${symbolChange >= 0 ? 'text-green-400' : 'text-red-400'}` },
  symbolChange >= 0 ? '↑' : '↓', " ", Math.abs(symbolChange).toFixed(2), "%"
  )
  ),
  React.createElement("div", { className: `px-2 py-1 rounded text-[10px] font-bold ${correlation < -0.5 ? 'bg-red-900/50 text-red-400' :
    correlation > 0.5 ? 'bg-green-900/50 text-green-400' :
    'bg-gray-800 text-gray-400'}` },
  "CORR: ",
  correlation.toFixed(2)
  )
  )
  ),
  secondaryIsVix && vixSignal &&
  React.createElement("div", { className: "mb-1" },
  typeof Tooltip !== 'undefined' ?
  React.createElement(Tooltip, { text: vixSignal.reason, position: "top" },
  React.createElement(SignalBadge, { signal: vixSignal })
  ) :
  React.createElement(SignalBadge, { signal: vixSignal, title: vixSignal.reason })
  ),
  React.createElement(SpectrumLegend, null),
  React.createElement("div", { className: "flex-1 relative" },
  React.createElement("div", { ref: chartContainerRef, className: "absolute inset-0" }),
  chartType === 'spectrum' &&
  React.createElement("canvas", {
    ref: overlayCanvasRef,
    className: "absolute inset-0 pointer-events-none",
    style: { mixBlendMode: 'screen' } }
  )
  )
  );
  return (
    React.createElement(React.Fragment, null,
    isMaximized ?
    window.ReactDOM.createPortal(
      React.createElement("div", { className: "fixed inset-0 z-[2000000] pointer-events-none" }, panelContent),
      document.getElementById('vix-portal-root') || document.body
    ) :
    panelContent
    ));
};
const SignalBadge = ({ signal, ...rest }) =>
React.createElement("div", _extends({
  className: `inline-flex items-center gap-1 px-2 py-1 rounded text-[10px] font-bold ${signal.type === 'BUY' ?
  'bg-gradient-to-r from-green-900 to-green-600 border border-green-500 text-green-200' :
  'bg-gradient-to-r from-red-900  to-red-600  border border-red-500  text-red-200'}` },
rest),
React.createElement("i", { className: `fas ${signal.type === 'BUY' ? 'fa-arrow-up' : 'fa-arrow-down'} text-xs` }),
signal.type, " (", signal.confidence, "%)"
);
window.VixCorrelationPanel = VixCorrelationPanel;