const DOMHistogramOverlay = ({
  container,
  chart,
  series,
  symbol,
  visible = false,
  config = {}
}) => {
  const { useEffect, useRef, useState } = React;
  const canvasRef = useRef(null);
  const [domData, setDomData] = useState(null);
  const pollingRef = useRef(null);
  const lastSymbolRef = useRef(symbol);
  const levelsUpdateTimer = useRef(0);
  const lastRenderTsRef = useRef(0);
  const settings = {
    levels: Math.max(500, config.levels || 2500),
    opacity: config.opacity !== undefined ? config.opacity : 0.85,
    bidColor: config.bidColor || '#10b981',
    askColor: config.askColor || '#ef5350',
    updateInterval: Math.max(100, config.updateInterval || 100),
    maxWidth: config.maxWidth || 500,
    barThickness: config.barThickness || 0.95,
    showLabels: config.showLabels !== false,
    renderStyle: config.renderStyle || 'bars'
  };
  const [requiredLevels, setRequiredLevels] = useState(settings.levels);
  const [isRateLimited, setIsRateLimited] = useState(false);
  useEffect(() => {
    if (symbol !== lastSymbolRef.current) {
      setDomData(null);
      setRequiredLevels(settings.levels);
      levelsUpdateTimer.current = 0;
      lastSymbolRef.current = symbol;
    }
  }, [symbol, settings.levels]);
  useEffect(() => {
    if (!visible || !symbol) return;
    let active = true;
    const ctrl = new AbortController();

    const handleUpdate = (e) => {
      const data = e.detail;
      if (!data || !active) return;
      const norm = (s) => window.getUniversalSymbol ? window.getUniversalSymbol(s) : s;
      if (norm(data.symbol) !== norm(symbol)) return;
      const now = Date.now();
      if (now - lastRenderTsRef.current < settings.updateInterval) return;
      lastRenderTsRef.current = now;
      if (data.bids && data.asks) setDomData(data);
    };

    window.addEventListener('market_dom', handleUpdate);

    const fetchData = async () => {
      try {
        const url = `/api/v2/feed/dom/${encodeURIComponent(symbol)}?levels=${requiredLevels}`;
        const res = await fetch(url, { signal: ctrl.signal });
        if (!res.ok) return;
        const data = await res.json();
        if (active && data.bids && data.asks) {
          setDomData(data);
          lastRenderTsRef.current = Date.now();
        }
      } catch { }
    };
    fetchData();

    return () => {
      active = false;
      window.removeEventListener('market_dom', handleUpdate);
      ctrl.abort();
    };
  }, [symbol, visible, requiredLevels, settings.updateInterval]);
  useEffect(() => {
    if (!visible || !domData || !canvasRef.current || !chart || !series) return;
    const canvas = canvasRef.current;
    const ctx = canvas.getContext('2d');
    const dpr = window.devicePixelRatio || 1;
    const draw = () => {
      const parent = canvas.parentNode || container;
      const rect = parent.getBoundingClientRect();
      const W = rect.width;
      const H = rect.height;
      if (canvas.width !== W * dpr || canvas.height !== H * dpr) {
        canvas.width = W * dpr;
        canvas.height = H * dpr;
        canvas.style.width = `${W}px`;
        canvas.style.height = `${H}px`;
      }
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.clearRect(0, 0, W, H);
      const bids = domData.bids || [];
      const asks = domData.asks || [];
      if (!bids.length && !asks.length) return;
      const bestBidPrice = bids.length ?
        bids.reduce((m, b) => b.price > m ? b.price : m, -Infinity) : null;
      const bestAskPrice = asks.length ?
        asks.reduce((m, a) => a.price < m ? a.price : m, Infinity) : null;
      const midpoint = domData.midpoint || (
        bestBidPrice !== null && bestAskPrice !== null ?
          (bestBidPrice + bestAskPrice) / 2 : null);
      const topPrice = series.coordinateToPrice(0);
      const bottomPrice = series.coordinateToPrice(H);
      if (topPrice === null || bottomPrice === null) return;
      const visibleMax = Math.max(topPrice, bottomPrice);
      const visibleMin = Math.min(topPrice, bottomPrice);
      const visibleRange = visibleMax - visibleMin;
      if (visibleRange <= 0) return;
      const refPrice = midpoint || visibleMin + visibleRange / 2;
      const tickSize = estimateTickSize({ bids, asks }, refPrice);
      const yRef = series.priceToCoordinate(refPrice);
      const yRefT = series.priceToCoordinate(refPrice + tickSize);
      const ppt = yRef !== null && yRefT !== null && yRef !== yRefT ?
        Math.abs(yRef - yRefT) :
        H / Math.max(1, visibleRange / tickSize);
      {
        const bidLow = bids.length ? Math.min(...bids.map((b) => b.price)) : Infinity;
        const askHigh = asks.length ? Math.max(...asks.map((a) => a.price)) : -Infinity;
        const buf30 = visibleRange * 0.3;
        if (bidLow > visibleMin - buf30 || askHigh < visibleMax + buf30) {
          const now = Date.now();
          if (now - levelsUpdateTimer.current > 800) {
            levelsUpdateTimer.current = now;
            const needed = Math.min(50000, Math.max(
              settings.levels,
              Math.ceil(visibleRange / tickSize * 5.5) // Increased depth request
            ));
            if (needed > requiredLevels) setRequiredLevels(needed);
          }
        }
      }
      let psWidth = 55;
      try {
        const ps = chart.priceScale('right');
        if (ps && typeof ps.width === 'function') {
          const pw = ps.width();
          if (pw > 20 && pw < 200) psWidth = pw;
        }
      } catch { }
      const chartAreaRight = W - psWidth;
      const maxBarW = Math.min(settings.maxWidth || 400, chartAreaRight - 10);

      const useStrategyA = ppt >= 2.0; 
      // Adaptive STRIP_H: Ensures smooth profile when zoomed out (no 4px blocks)
      const STRIP_H = useStrategyA ? Math.max(1, ppt * (settings.barThickness || 0.92)) : Math.max(1, Math.floor(ppt));

      const fmtVol = (v) => {
        if (!v || isNaN(v) || v <= 0) return null;
        if (v >= 1_000_000) return (v / 1_000_000).toFixed(1) + 'M';
        if (v >= 1_000) return (v / 1_000).toFixed(1) + 'K';
        return Number.isInteger(v) ? String(v) : v.toFixed(2);
      };

      const drawBar = (y, barH, color, vol, maxVol) => {
        if (!vol || isNaN(vol) || vol <= 0 || maxVol <= 0) return;
        const clipY = Math.floor(Math.max(0, y));
        const clipH = Math.max(1, Math.floor(Math.min(H, y + barH) - clipY));
        if (clipH < 1) return;

        // Solid block without gaps for a continuous histogram like ATAS
        let drawH = Math.ceil(clipH);

        // Limit maxWidth to prevent chart invasion
        const userMaxWidth = Math.min(W * 0.8, settings.maxWidth || 600); 

        // Moderate curve for better volume distinction while still showing small levels
        const norm = Math.pow(Math.min(1, vol / maxVol), 0.65); 

        let barWidth;
        let finalOpacity;

        if (settings.renderStyle === 'heatmap') {
          barWidth = userMaxWidth;
          const baseOpacity = settings.opacity !== undefined ? settings.opacity : 0.85;
          finalOpacity = Math.max(0.20, norm * baseOpacity);
        } else {
          barWidth = Math.max(12, norm * userMaxWidth);
          finalOpacity = settings.opacity !== undefined ? settings.opacity : 0.85;
        }

        const barX = Math.floor(chartAreaRight - barWidth);

        // Main Solid Bar
        ctx.globalAlpha = finalOpacity;
        ctx.fillStyle = color;
        ctx.fillRect(barX, clipY, Math.ceil(barWidth), drawH);

        // Labels on bars that are tall and wide enough
        if (settings.showLabels && drawH >= 5 && barWidth > 12) {
          const cy = clipY + drawH / 2;
          const fs = Math.min(11, Math.max(7, Math.floor(drawH) - 1));

          ctx.font = `600 ${fs}px Inter, system-ui, sans-serif`;
          ctx.textAlign = 'right';
          ctx.textBaseline = 'middle';

          const volStr = fmtVol(vol);
          if (volStr) {
            ctx.shadowColor = 'black';
            ctx.shadowBlur = 4;
            ctx.globalAlpha = 1.0;
            ctx.fillStyle = '#ffffff';
            ctx.fillText(volStr, chartAreaRight - 5, cy);
            ctx.shadowBlur = 0;
          }
        }
        ctx.globalAlpha = 1;
      };

      const midYraw = midpoint ? series.priceToCoordinate(midpoint) : null;
      const midY = midYraw === null ? H / 2 :
        midYraw < 0 ? 0 :
          midYraw > H ? H :
            midYraw;
      const askZoneBottom = Math.floor(midY);
      const bidZoneTop = Math.ceil(midY);

      if (useStrategyA) {
        const buf = visibleRange * 0.6;
        const vBids = bids.filter((b) => b.price >= visibleMin - buf && b.price <= visibleMax + buf);
        const vAsks = asks.filter((a) => a.price >= visibleMin - buf && a.price <= visibleMax + buf);
        const barH = STRIP_H;
        const bidMaxVol = percentileMax(vBids.map((b) => b.size), 0.70) || 1;
        const askMaxVol = percentileMax(vAsks.map((a) => a.size), 0.70) || 1;

        // Sum overlapping ticks exactly on their Y pixel
        const bidPixelSums = new Map();
        const askPixelSums = new Map();
        for (const b of vBids) {
          const y = series.priceToCoordinate(b.price);
          if (y === null) continue;
          const py = Math.floor(y / barH) * barH;
          bidPixelSums.set(py, (bidPixelSums.get(py) || 0) + b.size);
        }
        for (const a of vAsks) {
          const y = series.priceToCoordinate(a.price);
          if (y === null) continue;
          const py = Math.floor(y / barH) * barH;
          askPixelSums.set(py, (askPixelSums.get(py) || 0) + a.size);
        }
        for (const [y, vol] of bidPixelSums) {
          drawBar(y - barH / 2, barH, settings.bidColor, vol, bidMaxVol, false);
        }
        for (const [y, vol] of askPixelSums) {
          drawBar(y - barH / 2, barH, settings.askColor, vol, askMaxVol, true);
        }
      } else {
        const numStrips = Math.ceil(H / STRIP_H);
        const bidStrips = new Float64Array(numStrips);
        const askStrips = new Float64Array(numStrips);
        for (const b of bids) {
          const y = series.priceToCoordinate(b.price);
          if (y === null) continue;
          const s = Math.floor(y / STRIP_H);
          if (s < 0 || s >= numStrips) continue;
          bidStrips[s] += b.size;
        }
        for (const a of asks) {
          const y = series.priceToCoordinate(a.price);
          if (y === null) continue;
          const s = Math.floor(y / STRIP_H);
          if (s < 0 || s >= numStrips) continue;
          askStrips[s] += a.size;
        }

        const bidNorm = percentileMax(Array.from(bidStrips).filter((v) => v > 0), 0.70) || 1;
        const askNorm = percentileMax(Array.from(askStrips).filter((v) => v > 0), 0.70) || 1;

        const askStripEnd = Math.floor(askZoneBottom / STRIP_H);
        const bidStripStart = Math.ceil(bidZoneTop / STRIP_H);
        for (let s = 0; s <= askStripEnd && s < numStrips; s++) {
          if (askStrips[s] <= 0) continue;
          drawBar(s * STRIP_H, STRIP_H, settings.askColor, askStrips[s], askNorm);
        }
        for (let s = bidStripStart; s < numStrips; s++) {
          if (bidStrips[s] <= 0) continue;
          drawBar(s * STRIP_H, STRIP_H, settings.bidColor, bidStrips[s], bidNorm);
        }
      }
      if (midpoint) {
        const mY = series.priceToCoordinate(midpoint);
        if (mY !== null && mY >= 0 && mY <= H) {
          ctx.globalAlpha = 0.85;
          ctx.setLineDash([5, 3]);
          ctx.strokeStyle = 'rgba(255,255,255,0.9)';
          ctx.lineWidth = 1;
          ctx.beginPath();
          ctx.moveTo(chartAreaRight - 90, mY);
          ctx.lineTo(chartAreaRight, mY);
          ctx.stroke();
          ctx.setLineDash([]);
          ctx.globalAlpha = 1;
        }
      }
      if (isRateLimited) {
        ctx.globalAlpha = 1;
        ctx.fillStyle = 'rgba(239,68,68,0.15)';
        ctx.fillRect(chartAreaRight - 205, 10, 195, 26);
        ctx.fillStyle = '#ef4444';
        ctx.font = '600 11px Inter, sans-serif';
        ctx.textAlign = 'right';
        ctx.textBaseline = 'middle';
        ctx.fillText('RATE LIMIT (COOLDOWN)', chartAreaRight - 10, 23);
      }
      ctx.setTransform(1, 0, 0, 1, 0, 0);
    };
    let _isDrawing = false;
    let _needsRedraw = false;
    const onEventDraw = () => {
        if (_isDrawing) {
            _needsRedraw = true;
            return;
        }
        _isDrawing = true;
        try { draw(); } catch(e) {}
        requestAnimationFrame(() => {
            _isDrawing = false;
            if (_needsRedraw) {
                _needsRedraw = false;
                onEventDraw();
            }
        });
    };

    let _lastPriceCoord = null;
    let _lastTimeCoord = null;
    let _monitorRaf = null;
    const monitorScale = () => {
        if (series) {
            try {
                const pc = series.priceToCoordinate(0) || series.priceToCoordinate(100);
                const logicalRange = chart.timeScale().getVisibleLogicalRange();
                const tc = logicalRange ? logicalRange.from : null;
                if (pc !== _lastPriceCoord || tc !== _lastTimeCoord) {
                    _lastPriceCoord = pc;
                    _lastTimeCoord = tc;
                    onEventDraw();
                }
            } catch(e) {}
        }
        _monitorRaf = requestAnimationFrame(monitorScale);
    };
    _monitorRaf = requestAnimationFrame(monitorScale);

    chart.timeScale().subscribeVisibleTimeRangeChange(onEventDraw);
    chart.subscribeCrosshairMove(onEventDraw);
    
    // Initial draw
    onEventDraw();

    return () => {
      chart.timeScale().unsubscribeVisibleTimeRangeChange(onEventDraw);
      chart.unsubscribeCrosshairMove(onEventDraw);
      if (_monitorRaf) cancelAnimationFrame(_monitorRaf);
    };
  }, [domData, visible, chart, series, container, config, requiredLevels]);
  if (!visible) return null;
  return (
    React.createElement("canvas", {
      ref: canvasRef,
      className: "absolute inset-0 pointer-events-none z-10",
      style: { mixBlendMode: 'initial' }
    }
    ));
};
function estimateTickSize(domData, midprice) {
  const src = domData?.bids?.length >= 3 ? domData.bids :
    domData?.asks?.length >= 3 ? domData.asks :
      null;
  if (src && src.length >= 2) {
    const diffs = [];
    const sample = Math.min(40, src.length - 1);
    for (let i = 0; i < sample; i++) {
      const d = Math.abs(src[i + 1].price - src[i].price);
      if (d > 1e-10) diffs.push(d);
    }
    if (diffs.length > 0) {
      diffs.sort((a, b) => a - b);
      const t = diffs[Math.floor(diffs.length * 0.25)];
      if (t > 0) return t;
    }
  }
  const p = Math.abs(midprice) || 0;
  if (p > 100_000) return 1.0;
  if (p > 10_000) return 0.5;
  if (p > 1_000) return 0.25;
  if (p > 100) return 0.01;
  if (p > 10) return 0.001;
  if (p > 0.1) return 0.0001;
  return 0.000001;
}
function percentileMax(values, p = 0.995) {
  if (!values?.length) return 1;
  const sorted = [...values].filter((v) => v > 0).sort((a, b) => a - b);
  if (!sorted.length) return 0.0001;
  return sorted[Math.max(0, Math.floor(sorted.length * p) - 1)];
}
window.DOMHistogramOverlay = DOMHistogramOverlay;