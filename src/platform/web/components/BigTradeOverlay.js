const _normalizeBigTradeTime = (trade) => {
  if (!trade) return null;

  const normalizeNumber = (value) => {
    const numeric = Number(value);
    if (!Number.isFinite(numeric) || numeric <= 0) return null;
    return numeric > 1e11 ? Math.floor(numeric / 1000) : Math.floor(numeric);
  };

  const timestamp = normalizeNumber(trade.timestamp);
  if (timestamp !== null) return timestamp;

  const rawTime = trade.time;
  if (typeof rawTime === 'number') {
    return normalizeNumber(rawTime);
  }

  if (typeof rawTime === 'string') {
    const trimmed = rawTime.trim();
    if (/^\d{2}:\d{2}:\d{2}(?:\.\d{1,3})?$/.test(trimmed)) return null;
    const parsed = new Date(trimmed.includes('T') ? trimmed : trimmed.replace(' ', 'T')).getTime();
    if (Number.isFinite(parsed) && parsed > 0) return Math.floor(parsed / 1000);
  }

  return null;
};

const BigTradeOverlay = ({ chart, series, trades, settings, visible = true, tfSeconds = 0 }) => {
  const { useEffect, useRef } = React;
  const canvasRef = useRef(null);
  const chartRef = useRef(chart);
  const seriesRef = useRef(series);
  const tradesRef = useRef(trades);
  const settingsRef = useRef(settings);
  const visibleRef = useRef(visible);
  const tfSecondsRef = useRef(tfSeconds);
  const sortedTradesRef = useRef([]);
  const lastRectRef = useRef({ width: 0, height: 0 });
  // Referencia al scheduleRender del loop de renderizado (se asigna en el segundo useEffect)
  const scheduleRenderRef = useRef(null);
  useEffect(() => {
    chartRef.current = chart;
    seriesRef.current = series;
    tradesRef.current = trades;
    settingsRef.current = settings;
    visibleRef.current = visible;
    tfSecondsRef.current = tfSeconds;
    if (trades) {
      sortedTradesRef.current = [...trades].map(t => {
        return { ...t, _parsedTime: _normalizeBigTradeTime(t) };
      }).sort((a, b) => {
        const aType = a.bt_type === 'cumulative' || a.bt_type === 'agg' ? 1 : 0;
        const bType = b.bt_type === 'cumulative' || b.bt_type === 'agg' ? 1 : 0;
        return aType - bType;
      });
    } else {
      sortedTradesRef.current = [];
    }
    if (scheduleRenderRef.current) scheduleRenderRef.current();
  }, [chart, series, trades, settings, visible, tfSeconds]);
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    let rafId = null;

    const render = () => {
      rafId = null;
      if (!visibleRef.current || !chartRef.current || !seriesRef.current) {
        ctx.clearRect(0, 0, canvas.width, canvas.height);
        return;
      }
      const currentChart = chartRef.current;
      const currentSeries = seriesRef.current;
      const sortedTrades = sortedTradesRef.current;
      const currentSettings = settingsRef.current;
      const tfSecs = tfSecondsRef.current || 0;
      const dpr = window.devicePixelRatio || 1;
      const rect = canvas.getBoundingClientRect();
      if (rect.width === 0 || rect.height === 0) return;
      if (rect.width !== lastRectRef.current.width || rect.height !== lastRectRef.current.height || canvas.width !== rect.width * dpr) {
        lastRectRef.current = { width: rect.width, height: rect.height };
        canvas.width = rect.width * dpr;
        canvas.height = rect.height * dpr;
      }
      const currentRect = lastRectRef.current;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.clearRect(0, 0, currentRect.width, currentRect.height);
      const timeScale = currentChart.timeScale();
      let minTime = timeScale.coordinateToTime(-200);
      let maxTime = timeScale.coordinateToTime(rect.width + 200);
      if (minTime && typeof minTime === 'object') minTime = minTime.timestamp;
      if (maxTime && typeof maxTime === 'object') maxTime = maxTime.timestamp;
      if (minTime == null) minTime = 0;
      if (maxTime == null) maxTime = Infinity;

      sortedTrades.forEach((t) => {
        if (t._parsedTime === null) return;
        let vTime = t._parsedTime;

        // Alinear al centro de la vela usando el timeframe activo
        if (tfSecs > 0) {
          vTime = Math.floor(vTime / tfSecs) * tfSecs;
        }

        if (vTime < minTime || vTime > maxTime) return;

        const x = timeScale.timeToCoordinate(vTime);
        if (x === null || x < -100 || x > rect.width + 100) return;
        const y = currentSeries.priceToCoordinate(t.price);
        if (y !== null) {
          const mode = t.bt_type === 'cumulative' || t.bt_type === 'agg' ? 'cumulative' : 'real';
          const modeSettings = currentSettings?.[mode];
          if (!modeSettings || modeSettings.enabled === false) return;
          const threshold = modeSettings.threshold || 0;
          if (t.size < threshold) return;
          const scale = modeSettings.bubbleScale ?? (mode === 'cumulative' ? 1.2 : 1.0);
          const color = t.side === 'buy' ?
          modeSettings.buyColor || (mode === 'cumulative' ? '#3b82f6' : '#10b981') :
          modeSettings.sellColor || (mode === 'cumulative' ? '#f59e0b' : '#ef4444');
          const opacity = modeSettings.opacity ?? (mode === 'cumulative' ? 0.6 : 0.4);
          const showValue = modeSettings.showValue !== false;
          const textSize = modeSettings.textSize ?? 1.2;
          const vol = t.size || 1;
          const baseR = Math.max(6, Math.log10(vol + 1) * 8);
          const r = baseR * scale;
          const isAbs = t.isAbsorption;

          ctx.beginPath();
          if (isAbs) {
            ctx.moveTo(x, y - r * 1.3);
            ctx.lineTo(x + r * 1.3, y);
            ctx.lineTo(x, y + r * 1.3);
            ctx.lineTo(x - r * 1.3, y);
            ctx.closePath();
          } else {
            ctx.arc(x, y, r, 0, 2 * Math.PI);
          }

          ctx.fillStyle = color;
          ctx.globalAlpha = isAbs ? Math.min(1.0, opacity + 0.3) : opacity;
          ctx.fill();

          if (isAbs) {
            ctx.strokeStyle = 'rgba(255, 255, 255, 0.95)';
            ctx.lineWidth = 3;
            ctx.setLineDash([]);
            ctx.shadowColor = color;
            ctx.shadowBlur = 12;
          } else if (mode === 'cumulative') {
            ctx.strokeStyle = 'rgba(255, 255, 255, 0.7)';
            ctx.lineWidth = 2;
            ctx.setLineDash([2, 1]);
            ctx.shadowBlur = 0;
          } else {
            ctx.strokeStyle = 'rgba(255, 255, 255, 0.4)';
            ctx.lineWidth = 1;
            ctx.setLineDash([]);
            ctx.shadowBlur = 0;
          }
          ctx.stroke();
          ctx.setLineDash([]);
          ctx.shadowBlur = 0;
          if (showValue && r > 6) {
            ctx.globalAlpha = 1.0;
            ctx.fillStyle = 'white';
            const fontSize = Math.max(7, r * 0.5 * textSize);
            ctx.font = `bold ${fontSize}px Inter, sans-serif`;
            ctx.textAlign = 'center';
            ctx.textBaseline = 'middle';
            let label = t.size >= 1000 ? (t.size / 1000).toFixed(1) + 'k' : Math.floor(t.size).toString();
            if (t.size >= 10000) label = Math.floor(t.size / 1000) + 'k';
            if (t.size >= 1) {
              ctx.fillText(label, x, y);
            }
          }
          ctx.globalAlpha = 1.0;
        }
      });
    };

    // Renderizar solo cuando ocurre un evento real (sin loop continuo)

        let _isDrawing = false;
        let _needsRedraw = false;
        const scheduleRender = () => {
            if (_isDrawing) {
                _needsRedraw = true;
                return;
            }
            _isDrawing = true;
            try { render(); } catch(e) {}
            requestAnimationFrame(() => {
                _isDrawing = false;
                if (_needsRedraw) {
                    _needsRedraw = false;
                    scheduleRender();
                }
            });
        };

        const triggerRender = () => scheduleRender();
        let resizeObserver = null;
        if (typeof ResizeObserver !== 'undefined' && canvas.parentElement) {
            resizeObserver = new ResizeObserver(triggerRender);
            resizeObserver.observe(canvas.parentElement);
        }
        window.addEventListener('resize', triggerRender);
        window.addEventListener('focus', triggerRender);
        document.addEventListener('visibilitychange', triggerRender);

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
                        scheduleRender();
                    }
                } catch(e) {}
            }
            _monitorRaf = requestAnimationFrame(monitorScale);
        };
        _monitorRaf = requestAnimationFrame(monitorScale);


    scheduleRenderRef.current = scheduleRender;

    // Renderizado inicial
    scheduleRender();

    if (chartRef.current) {
      chartRef.current.timeScale().subscribeVisibleLogicalRangeChange(scheduleRender);
      chartRef.current.timeScale().subscribeVisibleTimeRangeChange(scheduleRender);
      chartRef.current.subscribeCrosshairMove(scheduleRender);
      try { currentSeries.priceScale().subscribeVisiblePriceRangeChange(scheduleRender); } catch(_) {}
    }

    return () => {
            if (_monitorRaf) cancelAnimationFrame(_monitorRaf);
      if (resizeObserver) resizeObserver.disconnect();
      window.removeEventListener('resize', triggerRender);
      window.removeEventListener('focus', triggerRender);
      document.removeEventListener('visibilitychange', triggerRender);
      if (chartRef.current) {
        chartRef.current.timeScale().unsubscribeVisibleLogicalRangeChange(scheduleRender);
        chartRef.current.timeScale().unsubscribeVisibleTimeRangeChange(scheduleRender);
        chartRef.current.unsubscribeCrosshairMove(scheduleRender);
        try { currentSeries.priceScale().unsubscribeVisiblePriceRangeChange(scheduleRender); } catch(_) {}
      }
      if (rafId !== null) cancelAnimationFrame(rafId);
    };
  }, []);
  return (
    React.createElement("canvas", {
      ref: canvasRef,
      className: "absolute inset-0 w-full h-full pointer-events-none",
      style: { zIndex: 10, display: visible ? 'block' : 'none' } }
    ));
};
window.BigTradeOverlay = BigTradeOverlay;
