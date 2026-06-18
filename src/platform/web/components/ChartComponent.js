const { useState, useEffect, useRef, useMemo, useCallback } = React;
const PositionOverlay = window.PositionOverlay;
const BigTradeOverlay = window.BigTradeOverlay;
const UserDrawingOverlay = window.UserDrawingOverlay;
const CurrentPriceLineOverlay = window.CurrentPriceLineOverlay;
const FourierOverlay = window.FourierOverlay;
const DOMHistogramOverlay = window.DOMHistogramOverlay;
const DOMHeatmapOverlay = window.DOMHeatmapOverlay;
const getDefaultChartSettings = window.getDefaultChartSettings;
const ChartSettingsModal = window.ChartSettingsModal;
const OrderFlowOverlay = window.OrderFlowOverlay;
const LiquidityHeatmapOverlay = window.LiquidityHeatmapOverlay;
const PriceChangeIndicator = window.PriceChangeIndicator;

// Helper: ensure a color string is a valid hex (fallback to #000000)
const _ensureHex = (color, fallback = "#000000") => {
  if (!color || typeof color !== 'string') return fallback;
  const c = color.trim();
  if (/^#[0-9a-fA-F]{6}$/.test(c)) return c;
  if (/^#[0-9a-fA-F]{3}$/.test(c)) {
    return '#' + c[1] + c[1] + c[2] + c[2] + c[3] + c[3];
  }
  return fallback;
};

// Helper: convert hex color to rgba with given alpha
const _getRgba = (hex, alpha) => {
  const safeHex = _ensureHex(hex);
  const r = parseInt(safeHex.slice(1, 3), 16);
  const g = parseInt(safeHex.slice(3, 5), 16);
  const b = parseInt(safeHex.slice(5, 7), 16);
  return `rgba(${r}, ${g}, ${b}, ${alpha})`;
};

// Helper: get platform scale factors safely
const _getPlatformScales = (symbol) => {
  const cp = typeof detectPlatformType === 'function' ? detectPlatformType() : 'mt5';
  const isCr = cp === 'crypto' || (symbol && (symbol.includes('/') || symbol.includes(':') || symbol.includes('USDT') || symbol.includes('USDC')));
  const pc = typeof getPlatformConfig === 'function' ? getPlatformConfig(cp) : {};
  return {
    vScale: isCr ? 1.0 : (pc.volumeScale || 1.0),
    dScale: isCr ? 1.0 : (pc.deltaScale || 1.0),
    platform: cp,
    config: pc
  };
};

// Helper: compute cumulative delta OHLC (candles) and line data from bars
const _computeCumulativeDelta = (bars, dScale) => {
  let cumDelta = 0;
  const candles = [];
  const lineData = [];
  for (let i = 0; i < bars.length; i++) {
    const bar = bars[i];
    const prevCum = cumDelta;
    const scaledDelta = isFinite(bar.delta) ? bar.delta * (dScale || 1) : 0;
    cumDelta += scaledDelta;
    candles.push({
      time: bar.time,
      open: prevCum,
      high: Math.max(prevCum, cumDelta),
      low: Math.min(prevCum, cumDelta),
      close: cumDelta
    });
    lineData.push({ time: bar.time, value: cumDelta });
  }
  return { candles, lineData, lastCumDelta: cumDelta };
};

// Helper: show/hide delta sub-series based on display mode
const _applyDeltaSeriesVisibility = (mode, showDelta, deltaSeriesRef, deltaCumCandleSeriesRef, deltaCumLineSeriesRef) => {
  const isHist = mode === 'histogram' || mode === 'deltaBars' || !mode;
  const isCumCandle = mode === 'cumulativeCandles';
  const isCumLine = mode === 'cumulativeLine';
  if (deltaSeriesRef.current) deltaSeriesRef.current.applyOptions({ visible: showDelta && isHist });
  if (deltaCumCandleSeriesRef.current) deltaCumCandleSeriesRef.current.applyOptions({ visible: showDelta && isCumCandle });
  if (deltaCumLineSeriesRef.current) deltaCumLineSeriesRef.current.applyOptions({ visible: showDelta && isCumLine });
};

const ChartComponent = React.memo(({
  chartSettings,
  liveData,
  historicalData,
  tickData,
  activeTool,
  activeSymbol,
  activeTimeframe,
  systemStatus,
  onOrder,
  showAllOverlays = true,
  indicators,
  globalBigTradesRef,
  mt5Positions = [],
  mt5PendingOrders = [],
  setLastCandleTime,
  marketStatus,
  chartType: propChartType,
  chartId,
  onToolFinish,
  showVolume,
  showDelta,
  onLlamaActiveChange,
  symbolMetadata,
  volume,
  onUpdateSettings,
  platform
}) => {
  const chartContainerRef = useRef();
  const chartRef = useRef();
  const candleSeriesRef = useRef();
  const areaSeriesRef = useRef();
  const lineSeriesRef = useRef();
  const barSeriesRef = useRef();
  const volumeSeriesRef = useRef();
  const deltaSeriesRef = useRef();
  const deltaCumCandleSeriesRef = useRef(null);
  const deltaCumLineSeriesRef = useRef(null);
  const vpEngineRef = useRef(null);
  const vpRendererRef = useRef(null);
  const allBarsRef = useRef([]);
  const cazaStopLinesRef = useRef([]);
  const cazaStopSeriesRef = useRef([]);
  const lastActivePaneRef = useRef('main');
  const mousePosRef = useRef({ time: null, price: null, point: null });
  const isUpdatingDataRef = useRef(false);
  const activeHoverPaneRef = useRef(null);
  const interactionTimeoutRef = useRef(null);
  const lastSyncRangeRef = useRef(null);
  const lastSyncTimeoutRef = useRef(null);
  const lastVPUpdateTimeRef = useRef(0);
  const lastOFUpdateTimeRef = useRef(0);
  const fpRendererRef = useRef(null);
  const footprintContainerRef = useRef(null);
  const visualCloseRef = useRef(null);
  const visualTimeRef = useRef(null);
  const activeSymbolRef = useRef(activeSymbol);
  const symbolMetadataRef = useRef(symbolMetadata);
  const restoredRangeRef = useRef(null);

  // Persistence: Save range (Logical + Time-based)
  const saveLogicalRange = useCallback((range, totalBars = 0) => {
    if (!range || !chartId || !chartRef.current) return;
    const timeRange = chartRef.current.timeScale().getVisibleRange();
    const data = { ...range, totalBars, timeRange };

    // 1. Timeframe-specific key (Legacy & Exact)
    const tfKey = `chart_range_${chartId}_${activeSymbol}_${activeTimeframe}`;
    localStorage.setItem(tfKey, JSON.stringify(data));
    
    // 2. Global Symbol-specific key (For new timeframes or sessions)
    const globalKey = `chart_range_global_${chartId}_${activeSymbol}`;
    localStorage.setItem(globalKey, JSON.stringify(data));
  }, [chartId, activeSymbol, activeTimeframe]);

  // Persistence: Load range
  useEffect(() => {
    if (!chartId) return;
    const tfKey = `chart_range_${chartId}_${activeSymbol}_${activeTimeframe}`;
    const globalKey = `chart_range_global_${chartId}_${activeSymbol}`;
    
    const savedTf = localStorage.getItem(tfKey);
    const savedGlobal = localStorage.getItem(globalKey);
    
    if (savedTf) {
      try { restoredRangeRef.current = JSON.parse(savedTf); } catch (e) { restoredRangeRef.current = null; }
    } else if (savedGlobal) {
      try { restoredRangeRef.current = JSON.parse(savedGlobal); } catch (e) { restoredRangeRef.current = null; }
    } else {
      restoredRangeRef.current = null;
    }
  }, [chartId, activeSymbol, activeTimeframe, historicalData]);

  // Helper to adjust restored range based on "Stick-to-Right" logic
  const getAdjustedRange = useCallback((savedRange, newTotalBars) => {
    if (!savedRange || isNaN(newTotalBars) || newTotalBars <= 0) return null;
    
    // Prefer TimeRange if available for cross-timeframe consistency
    // Note: Applying setVisibleRange(timeRange) is handled in the effect after logical range fails or as preference
    
    const savedTotal = savedRange.totalBars || 0;
    // If the user was at the "Right Edge", stay at the right edge
    const isAtRightEdge = savedTotal > 10 && savedRange.to >= (savedTotal - 5);
    
    if (isAtRightEdge) {
      const zoomLevel = savedRange.to - savedRange.from;
      return {
        from: newTotalBars - zoomLevel + (savedRange.to - savedTotal),
        to: newTotalBars + (savedRange.to - savedTotal)
      };
    }
    return { from: savedRange.from, to: savedRange.to };
  }, []);
  useEffect(() => {
    activeSymbolRef.current = activeSymbol;
    symbolMetadataRef.current = symbolMetadata;
  }, [activeSymbol, symbolMetadata]);
  const [footprintMode, setFootprintMode] = useState(
    () => chartSettings?.footprint?.mode || 'off'
  );
  useEffect(() => {
    const handleFpChange = (e) => {
      if (e.detail?.chartId === chartId) {
        setFootprintMode(e.detail.mode);
      }
    };
    const handleFpSettingsChange = (e) => {
      if (e.detail?.chartId === chartId && fpRendererRef.current) {
        const { settings } = e.detail;
        if (settings.fontSize !== undefined) fpRendererRef.current.setFontSize(settings.fontSize);
        if (settings.showWicks !== undefined) fpRendererRef.current.setShowWicks(settings.showWicks);
        if (settings.showPOC !== undefined) fpRendererRef.current.setShowPOC(settings.showPOC);
        if (settings.wickThickness !== undefined) fpRendererRef.current.setWickThickness(settings.wickThickness);
        if (settings.buyColor !== undefined || settings.sellColor !== undefined || settings.pocColor !== undefined ||
          settings.bodyBullColor !== undefined || settings.bodyBullOpacity !== undefined ||
          settings.bodyBearColor !== undefined || settings.bodyBearOpacity !== undefined ||
          settings.syncWithChartColors !== undefined) {
          
          const buildBodyColor = (hex, opacityPct) => {
            const m = /^#?([a-f\d]{2})([a-f\d]{2})([a-f\d]{2})$/i.exec(hex);
            if (!m) return hex;
            const a = ((opacityPct ?? 55) / 100).toFixed(2);
            return `rgba(${parseInt(m[1], 16)},${parseInt(m[2], 16)},${parseInt(m[3], 16)},${a})`;
          };

          const fp = chartSettings?.footprint || {};
          const isSync = settings.syncWithChartColors !== undefined ? settings.syncWithChartColors : (fp.syncWithChartColors ?? true);
          
          fpRendererRef.current.setColors({
            buy: settings.buyColor || fp.buyColor || "#10b981",
            sell: settings.sellColor || fp.sellColor || "#ef4444",
            poc: settings.pocColor || fp.pocColor || "#ffeb3b",
            bodyBull: buildBodyColor(
              isSync ? globalAppearance.upColor : (settings.bodyBullColor ?? fp.bodyBullColor ?? '#00dc6e'),
              settings.bodyBullOpacity ?? fp.bodyBullOpacity ?? 55
            ),
            bodyBear: buildBodyColor(
              isSync ? globalAppearance.downColor : (settings.bodyBearColor ?? fp.bodyBearColor ?? '#e6284b'),
              settings.bodyBearOpacity ?? fp.bodyBearOpacity ?? 55
            )
          });
        }
      }
    };
    window.addEventListener('footprint_mode_change', handleFpChange);
    window.addEventListener('footprint_settings_change', handleFpSettingsChange);
    return () => {
      window.removeEventListener('footprint_mode_change', handleFpChange);
      window.removeEventListener('footprint_settings_change', handleFpSettingsChange);
    };
  }, [chartId, chartSettings?.footprint, globalAppearance]);
  useEffect(() => {
    if (chartSettings?.footprint?.mode) {
      setFootprintMode(chartSettings.footprint.mode);
    }
  }, [chartSettings?.footprint?.mode]);
  const [footprintData, setFootprintData] = useState(null);
  const [hoverData, setHoverData] = useState({ volume: null, delta: null });
  const footprintFetchingRef = useRef(false);
  const [globalAppearance, setGlobalAppearance] = useState(
    () => ({
      backgroundColor: "#000000",
      upColor: "#26a69a",
      downColor: "#ef5350",
      borderUpColor: "#4b5563",
      borderDownColor: "#4b5563",
      borderVisible: true,
      ...(chartSettings?.appearance || {})
    })
  );
  useEffect(() => {
    if (chartSettings?.appearance) {
      setGlobalAppearance((prev) => ({
        ...prev,
        ...chartSettings.appearance
      }));
    }
  }, [chartSettings?.appearance]);
  const settingsRef = useRef({
    ...chartSettings,
    appearance: {
      backgroundColor: "#000000",
      upColor: "#26a69a",
      downColor: "#ef5350",
      borderUpColor: "#4b5563",
      borderDownColor: "#4b5563",
      borderVisible: true,
      ...(chartSettings?.appearance || {})
    }
  });
  useEffect(() => {
    settingsRef.current = {
      ...chartSettings,
      appearance: {
        ...globalAppearance,
        ...(chartSettings?.appearance || {})
      }
    };
  }, [chartSettings, globalAppearance]);
  const bgColor = chartSettings?.appearance?.backgroundColor || "#000000";
  const showGrid = chartSettings?.layout?.showGrid ?? true;
  const [isChartReady, setIsChartReady] = useState(false);
  const dataUpdateInMinuteRef = useRef(false);
  const [isVisible, setIsVisible] = useState(false);
  const [localLastCandleTime, setLocalLastCandleTime] = useState(null);
  const chartType = chartSettings?.chartType || propChartType || "candle";
  const normalizedVpConfig = useMemo(() => {
    const defaults = window.getDefaultChartSettings ? window.getDefaultChartSettings().indicators.volumeProfile : {};
    return {
      ...defaults,
      ...(chartSettings?.indicators?.volumeProfile || {}),
      params: {
        rangeMode: "visible",
        ...(defaults.params || {}),
        ...(chartSettings?.indicators?.volumeProfile?.params || {})
      }
    };
  }, [chartSettings?.indicators?.volumeProfile]);
  const normalizedDomConfig = useMemo(() => {
    const defaults = window.getDefaultChartSettings ? window.getDefaultChartSettings().dom : {};
    return {
      ...defaults,
      ...(chartSettings?.dom || {})
    };
  }, [chartSettings?.dom]);

  const normalizedBookmapConfig = useMemo(() => {
    const defaults = window.getDefaultChartSettings ? window.getDefaultChartSettings().bookmap : {};
    return {
      ...defaults,
      ...(chartSettings?.bookmap || {})
    };
  }, [chartSettings?.bookmap]);

  const isBookmapActive = showAllOverlays && chartSettings?.overlays?.showBookmap;
  useEffect(() => {
    if (
      !isChartReady ||
      !candleSeriesRef.current ||
      !activeSymbol) {
      return;
    }
    try {
      if (activeSymbol !== prevSymbolRef.current) {
        if (candleSeriesRef.current) {
          candleSeriesRef.current.setMarkers([]);
          cazaStopLinesRef.current.forEach((line) => {
            try {
              candleSeriesRef.current.removePriceLine(line);
            } catch (e) { }
          });
          cazaStopLinesRef.current = [];
        }
      }
      if (
        candleSeriesRef.current &&
        candleSeriesRef.current.setMarkers) {
        candleSeriesRef.current.setMarkers([]);
      }
    } catch (e) {
      console.error("[CAZASTOP] Cleanup error:", e);
    }
    if (!indicators) {
      return;
    }
    const isCazaStopEnabled =
      chartSettings?.indicators?.cazastop?.enabled ||
      indicators["caza_stop"]?.enabled;
    const isImbalanceEnabled =
      chartSettings?.indicators?.imbalance?.enabled ||
      indicators["imbalance_impulse"]?.enabled;
    if (!isCazaStopEnabled && !isImbalanceEnabled) {
      return;
    }
    let isFetching = false;
    let fetchTimeout = null;
    const fetchIndicators = async () => {
      if (isFetching) {
        return;
      }
      isFetching = true;
      const platform = typeof detectPlatformType === "function" ?
        detectPlatformType() :
        window.detectPlatformType ? window.detectPlatformType() : localStorage.getItem("broker_platform") || localStorage.getItem("platform") || "futures";
      try {
        const csP = chartSettings?.indicators?.cazastop?.params || {};
        const imbP = chartSettings?.indicators?.imbalance?.params || {};
        const indicatorParams = new URLSearchParams({
          ...(csP.swing_bars !== undefined && { cs_swing_bars: csP.swing_bars }),
          ...(csP.lookback !== undefined && { cs_lookback: csP.lookback }),
          ...(csP.dist_ticks !== undefined && { cs_dist_ticks: csP.dist_ticks }),
          ...(csP.buffer_ticks !== undefined && { cs_buffer_ticks: csP.buffer_ticks }),
          ...(csP.vida_max !== undefined && { cs_vida_max: csP.vida_max }),
          ...(csP.lookback_tp !== undefined && { cs_lookback_tp: csP.lookback_tp }),
          ...(csP.ticks_tp !== undefined && { cs_ticks_tp: csP.ticks_tp }),
          ...(csP.mostrar_tp !== undefined && { cs_mostrar_tp: csP.mostrar_tp }),
          ...(csP.analisis_vol !== undefined && { cs_analisis_vol: csP.analisis_vol }),
          ...(csP.dibujar_safe !== undefined && { cs_dibujar_safe: csP.dibujar_safe }),
          ...(imbP.delta_threshold !== undefined && { imb_delta_threshold: imbP.delta_threshold }),
          ...(imbP.volume_multiplier !== undefined && { imb_volume_multiplier: imbP.volume_multiplier }),
          ...(imbP.min_body_ratio !== undefined && { imb_min_body_ratio: imbP.min_body_ratio }),
          ...(imbP.min_bars_between !== undefined && { imb_min_bars_between: imbP.min_bars_between }),
          ...(imbP.structure_lookback !== undefined && { imb_structure_lookback: imbP.structure_lookback }),
          ...(imbP.atr_multiplier !== undefined && { imb_atr_multiplier: imbP.atr_multiplier }),
          ...(imbP.use_structure !== undefined && { imb_use_structure: imbP.use_structure }),
          ...(imbP.use_volume_filter !== undefined && { imb_use_volume_filter: imbP.use_volume_filter })
        }).toString();
        // Get limit from settings
        let fetchLimit = 2000;
        try {
          const storedLimits = JSON.parse(localStorage.getItem('chart_history_limits') || '{}');
          fetchLimit = storedLimits[activeTimeframe] || 3000;
        } catch (e) {
          fetchLimit = 3000;
        }

        const url = `/api/indicators/calculate?symbol=${activeSymbol}&timeframe=${activeTimeframe}&limit=${fetchLimit}&platform=${encodeURIComponent(platform)}${indicatorParams ? '&' + indicatorParams : ''}`;
        let res = null;
        for (let i = 0; i < 3; i++) {
          try {
            res = await fetch(url);
            if (res.ok) break;
          } catch (e) { }
          if (i < 2) await new Promise((r) => setTimeout(r, 1000));
        }
        if (!res || !res.ok) {
          isFetching = false;
          return;
        }
        if (
          !isChartReady ||
          !candleSeriesRef.current ||
          !activeSymbol) {
          return;
        }
        const data = await res.json();
        if (!candleSeriesRef.current || !isChartReady) {
          return;
        }
        if (data.error || !data.indicators) {
          if (candleSeriesRef.current) {
            candleSeriesRef.current.setMarkers([]);
            cazaStopLinesRef.current.forEach((line) => {
              try {
                candleSeriesRef.current.removePriceLine(line);
              } catch (e) { }
            });
            cazaStopLinesRef.current = [];
          }
          return;
        }
        const cazaStopData = data.indicators.caza_stop;
        if (isCazaStopEnabled && cazaStopData?.zones) {
          cazaStopLinesRef.current.forEach((line) => {
            try {
              if (candleSeriesRef.current) {
                candleSeriesRef.current.removePriceLine(line);
              }
            } catch (e) { }
          });
          cazaStopLinesRef.current = [];
          const csSettings = chartSettings?.indicators?.cazastop;
          const lineWidth = csSettings?.lineWidth ?? 3;
          const colorTop = csSettings?.colorTop || "#ef4444";
          const colorBottom = csSettings?.colorBottom || "#ef4444";
          const colorPoc = csSettings?.colorPoc || "#3b82f6";
          const lineStyle = csSettings?.lineStyle ?? 0;
          const showZones = csSettings?.showZones !== false;
          const pocOnly = csSettings?.pocOnly === true;
          const recentZones = cazaStopData.zones.slice(-10);
          if (candleSeriesRef.current) {
            if (!pocOnly && showZones) {
              recentZones.forEach((zone, idx) => {
                const topLine = candleSeriesRef.current.createPriceLine({
                  price: zone.level_top,
                  color: colorTop,
                  lineWidth: lineWidth,
                  lineStyle: lineStyle,
                  axisLabelVisible: true,
                  title: `STOP ZONA ${idx + 1}`
                });
                cazaStopLinesRef.current.push(topLine);
                const bottomLine = candleSeriesRef.current.createPriceLine({
                  price: zone.level_bottom,
                  color: colorBottom,
                  lineWidth: lineWidth,
                  lineStyle: lineStyle,
                  axisLabelVisible: false,
                  title: ""
                });
                cazaStopLinesRef.current.push(bottomLine);
              });
            }
            if (cazaStopData.tp_zone && showZones) {
              const tp = cazaStopData.tp_zone;
              const pocLine = candleSeriesRef.current.createPriceLine({
                price: tp.poc,
                color: colorPoc,
                lineWidth: lineWidth,
                lineStyle: lineStyle,
                axisLabelVisible: true,
                title: "POC VOLUMEN"
              });
              cazaStopLinesRef.current.push(pocLine);
            }
          }
        }
        const imbalanceData = data.indicators.imbalance_impulse;
        if (isImbalanceEnabled && imbalanceData && imbalanceData.signals) {
          const imbSettings = chartSettings?.indicators?.imbalance;
          const buyColor = imbSettings?.buyColor || "#22c55e";
          const sellColor = imbSettings?.sellColor || "#ef4444";
          const signalSize = imbSettings?.signalSize ?? 1;
          const markers = imbalanceData.signals.map(
            (sig) => ({
              time: sig.time,
              position: sig.position,
              color: sig.type === "BUY" ? buyColor : sellColor,
              shape: sig.shape,
              text: sig.text,
              size: signalSize
            })
          );
          if (candleSeriesRef.current) {
            candleSeriesRef.current.setMarkers(markers);
          }
        } else {
          if (candleSeriesRef.current) {
            candleSeriesRef.current.setMarkers([]);
          }
        }
      } catch (e) {
        console.error("[CAZASTOP] Error:", e);
      } finally {
        isFetching = false;
      }
    };
    fetchIndicators();
    const handleConfigChange = () => {
      if (fetchTimeout) clearTimeout(fetchTimeout);
      fetchTimeout = setTimeout(() => {
        fetchIndicators();
      }, 500);
    };
    window.addEventListener("cazastop_config_changed", handleConfigChange);
    return () => {
      if (fetchTimeout) clearTimeout(fetchTimeout);
      window.removeEventListener("cazastop_config_changed", handleConfigChange);
    };
  }, [isChartReady, indicators, chartSettings, activeSymbol, activeTimeframe]);
  const orderFlowSeriesRef = useRef({ vwap: null });
  const [ofDataState, setOfDataState] = useState([]);
  const orderFlowBaselineRef = useRef({ cumDelta: 0, vwap: 0, time: 0 });
  const orderFlowInitialized = useRef(false);
  useEffect(() => {
    let isMounted = true;
    let isFetching = false;
    let fetchTimeout = null;
    const fetchOrderFlow = async () => {
      const platform = typeof detectPlatformType === "function" ?
        detectPlatformType() :
        window.detectPlatformType ? window.detectPlatformType() : localStorage.getItem("broker_platform") || localStorage.getItem("platform") || "futures";
      if (platform === "crypto" && (activeSymbol.startsWith("MNQ") || activeSymbol === "MNQ=F")) {
        return;
      }
      const ofConfig = chartSettings?.indicators?.orderflow || getDefaultChartSettings().indicators.orderflow;
      if (!ofConfig.enabled) {
        cleanupOrderFlowSeries();
        setOfDataState([]);
        orderFlowInitialized.current = false;
        return;
      }
      if (isFetching || !chartRef.current || !isMounted) return;
      isFetching = true;
      try {
        // Get limit from settings
        let fetchLimit = ofConfig.limit || 2000;
        try {
          const storedLimits = JSON.parse(localStorage.getItem('chart_history_limits') || '{}');
          const tfLimit = storedLimits[activeTimeframe] || 3000;
          // Respect the tighter of the two: indicator-specific limit or general history limit
          fetchLimit = Math.min(fetchLimit, tfLimit);
        } catch (e) { 
          fetchLimit = Math.min(fetchLimit, 3000);
        }

        const url = `/api/indicators/calculate?symbol=${activeSymbol}&timeframe=${activeTimeframe}&limit=${fetchLimit}&platform=${encodeURIComponent(platform)}`;
        let res = null;
        for (let i = 0; i < 3; i++) {
          try {
            res = await fetch(url);
            if (res.ok) break;
          } catch (e) { }
          if (i < 2) await new Promise((r) => setTimeout(r, 1000));
        }
        if (!res || !res.ok) {
          isFetching = false;
          return;
        }
        if (!isMounted || !candleSeriesRef.current) return;
        const data = await res.json();
        if (!isMounted || !chartRef.current || !candleSeriesRef.current) return;
        if (data.indicators && data.indicators.order_flow && data.indicators.order_flow.data) {
          const ofData = data.indicators.order_flow.data;
          if (ofConfig.showVwap) {
            if (!orderFlowSeriesRef.current.vwap && chartRef.current) {
              orderFlowSeriesRef.current.vwap = chartRef.current.addLineSeries({
                color: ofConfig.vwapColor || "#fbbf24",
                lineWidth: ofConfig.vwapWidth || 2,
                crosshairMarkerVisible: false,
                lastValueVisible: false,
                priceLineVisible: false,
                title: "VWAP"
              });
            }
            if (ofConfig.showVwapBands) {
              ["u1", "l1", "u2", "l2"].forEach((key) => {
                if (!orderFlowSeriesRef.current[`vwap_${key}`] && chartRef.current) {
                  const isBand2 = key.includes("2");
                  orderFlowSeriesRef.current[`vwap_${key}`] = chartRef.current.addLineSeries({
                    color: isBand2 ? ofConfig.band2Color || "rgba(251, 191, 36, 0.2)" : ofConfig.band1Color || "rgba(251, 191, 36, 0.4)",
                    lineWidth: ofConfig.bandWidth || 1,
                    crosshairMarkerVisible: false,
                    lastValueVisible: false,
                    priceLineVisible: false,
                    lineStyle: 2,
                    title: `VWAP ${key.toUpperCase()}`
                  });
                }
              });
            } else {
              ["u1", "l1", "u2", "l2"].forEach((key) => {
                if (orderFlowSeriesRef.current[`vwap_${key}`]) {
                  chartRef.current.removeSeries(orderFlowSeriesRef.current[`vwap_${key}`]);
                  orderFlowSeriesRef.current[`vwap_${key}`] = null;
                }
              });
            }
            if (orderFlowSeriesRef.current.vwap) {
              const vwapData = ofData.filter((d) => d.vwap !== null).map((d) => ({ time: d.time, value: d.vwap }));
              orderFlowSeriesRef.current.vwap.setData(vwapData);
              orderFlowSeriesRef.current.vwap.applyOptions({
                color: ofConfig.vwapColor || "#fbbf24",
                lineWidth: ofConfig.vwapWidth || 2
              });
            }
            if (ofConfig.showVwapBands) {
              ["u1", "l1", "u2", "l2"].forEach((key) => {
                if (orderFlowSeriesRef.current[`vwap_${key}`]) {
                  const bandData = ofData.filter((d) => d[`vwap_${key}`] !== null).map((d) => ({ time: d.time, value: d[`vwap_${key}`] }));
                  orderFlowSeriesRef.current[`vwap_${key}`].setData(bandData);
                  const isBand2 = key.includes("2");
                  orderFlowSeriesRef.current[`vwap_${key}`].applyOptions({
                    color: isBand2 ? ofConfig.band2Color || "rgba(251, 191, 36, 0.2)" : ofConfig.band1Color || "rgba(251, 191, 36, 0.4)",
                    lineWidth: ofConfig.bandWidth || 1
                  });
                }
              });
            }
          } else {
            cleanupOrderFlowSeries();
          }
          if (ofConfig.showCumDelta) {
            const deltaData = ofData
              .filter((d) => d.cumulative_delta !== null)
              .map((d) => ({ time: d.time, value: d.cumulative_delta }))
              .sort((a, b) => a.time - b.time);
            if (deltaData.length > 0) {
              setOfDataState(deltaData);
              if (deltaData.length >= 2) {
                orderFlowBaselineRef.current.cumDelta = deltaData[deltaData.length - 2].value;
                orderFlowBaselineRef.current.time = deltaData[deltaData.length - 2].time;
              }
              orderFlowInitialized.current = true;
            }
          } else {
            setOfDataState([]);
          }
        }
      } catch (e) {
        console.error("[ORDERFLOW] Error:", e);
      } finally {
        if (isMounted) isFetching = false;
      }
    };
    const cleanupOrderFlowSeries = () => {
      if (!chartRef.current) return;
      if (orderFlowSeriesRef.current.vwap) {
        try { chartRef.current.removeSeries(orderFlowSeriesRef.current.vwap); } catch (e) { }
        orderFlowSeriesRef.current.vwap = null;
      }
      ["u1", "l1", "u2", "l2"].forEach((key) => {
        if (orderFlowSeriesRef.current[`vwap_${key}`]) {
          try { chartRef.current.removeSeries(orderFlowSeriesRef.current[`vwap_${key}`]); } catch (e) { }
          orderFlowSeriesRef.current[`vwap_${key}`] = null;
        }
      });
      orderFlowInitialized.current = false;
    };
    fetchOrderFlow();
    const handleUpdate = () => {
      if (fetchTimeout) clearTimeout(fetchTimeout);
      fetchTimeout = setTimeout(() => {
        if (isMounted) fetchOrderFlow();
      }, 500);
    };
    window.addEventListener("orderflow_update", handleUpdate);
    window.addEventListener("storage", handleUpdate);
    return () => {
      isMounted = false;
      if (fetchTimeout) clearTimeout(fetchTimeout);
      window.removeEventListener("orderflow_update", handleUpdate);
      window.removeEventListener("storage", handleUpdate);
      cleanupOrderFlowSeries();
    };
  }, [activeSymbol, activeTimeframe, isChartReady, localLastCandleTime, chartSettings]);

  // ── Liquidity Heatmap: dedicated state and fetch ──
  const [liquidityHeatmapData, setLiquidityHeatmapData] = useState([]);
  useEffect(() => {
    let isMounted = true;
    let isFetching = false;
    let fetchTimeout = null;
    const fetchLiquidityHeatmap = async () => {
      const lhConfig = chartSettings?.indicators?.liquidity_heatmap || getDefaultChartSettings().indicators.liquidity_heatmap;
      if (!lhConfig.enabled) {
        setLiquidityHeatmapData([]);
        return;
      }
      if (isFetching || !chartRef.current || !isMounted) return;
      isFetching = true;
      try {
        const platform = typeof detectPlatformType === "function"
          ? detectPlatformType()
          : window.detectPlatformType ? window.detectPlatformType() : localStorage.getItem("broker_platform") || localStorage.getItem("platform") || "futures";
        let fetchLimit = 2000;
        try {
          const storedLimits = JSON.parse(localStorage.getItem('chart_history_limits') || '{}');
          fetchLimit = Math.min(fetchLimit, storedLimits[activeTimeframe] || 3000);
        } catch (e) {
          fetchLimit = 2000;
        }
        const url = `/api/indicators/calculate?symbol=${activeSymbol}&timeframe=${activeTimeframe}&limit=${fetchLimit}&platform=${encodeURIComponent(platform)}`;
        let res = null;
        for (let i = 0; i < 3; i++) {
          try {
            res = await fetch(url);
            if (res.ok) break;
          } catch (e) { }
          if (i < 2) await new Promise((r) => setTimeout(r, 1000));
        }
        if (!res || !res.ok || !isMounted) { isFetching = false; return; }
        const data = await res.json();
        if (!isMounted) return;
        if (data.indicators && data.indicators.liquidity_heatmap && data.indicators.liquidity_heatmap.data) {
          setLiquidityHeatmapData(data.indicators.liquidity_heatmap.data);
        } else {
          setLiquidityHeatmapData([]);
        }
      } catch (e) {
        console.error("[LIQUIDITY_HEATMAP] Error:", e);
      } finally {
        if (isMounted) isFetching = false;
      }
    };
    fetchLiquidityHeatmap();
    const handleUpdate = () => {
      if (fetchTimeout) clearTimeout(fetchTimeout);
      fetchTimeout = setTimeout(() => {
        if (isMounted) fetchLiquidityHeatmap();
      }, 500);
    };
    window.addEventListener("cazastop_config_changed", handleUpdate);
    
    return () => {
      isMounted = false;
      if (fetchTimeout) clearTimeout(fetchTimeout);
      window.removeEventListener("cazastop_config_changed", handleUpdate);
    };
  }, [activeSymbol, activeTimeframe, isChartReady, chartSettings]);

  const [llamaParams, setLlamaParams] = useState({ big: null, inbalance: null, caza: null });
  useEffect(() => {
    const handleLlama = (e) => {
      if (e.detail.symbol === activeSymbol) {
        const lType = e.detail.llamaType || 'big';
        setLlamaParams((prev) => ({ ...prev, [lType]: e.detail.params }));
      }
    };
    window.addEventListener('llama_update', handleLlama);
    const handleLegacy = (e) => {
      if (e.detail.symbol === activeSymbol) {
        setLlamaParams((prev) => ({ ...prev, big: e.detail.params || e.detail.llamaParams }));
      }
    };
    window.addEventListener('big_llama_update', handleLegacy);
    return () => {
      window.removeEventListener('llama_update', handleLlama);
      window.removeEventListener('big_llama_update', handleLegacy);
    };
  }, [activeSymbol]);
  const isBigLlamaActive = chartSettings?.indicators?.bigTrades?.bigLlama;
  const isInbalanceLlamaActive = chartSettings?.indicators?.imbalance?.llama;
  const isCazaLlamaActive = chartSettings?.indicators?.cazastop?.llama;
  const [bigTrades, setBigTrades] = useState(() => {
    if (globalBigTradesRef?.current && globalBigTradesRef.current[activeSymbol]) {
      return globalBigTradesRef.current[activeSymbol];
    }
    return [];
  });
  const hasProcessedHistoricalRef = useRef({});
  useEffect(() => {
    if (globalBigTradesRef?.current) {
      globalBigTradesRef.current[activeSymbol] = bigTrades;
    }
  }, [bigTrades, activeSymbol]);
  const [liveAggregatedTrades, setLiveAggregatedTrades] = useState([]);
  const [liveRealTrades, setLiveRealTrades] = useState([]);
  const handleNewRealTrade = useCallback((trade) => {
    setLiveRealTrades((prev) => [trade, ...prev].slice(0, 100));
  }, []);
  const bigTradeWindow = useMemo(() => {
    if (isBigLlamaActive && llamaParams.big?.window) return llamaParams.big.window;
    return chartSettings?.indicators?.bigTrades?.cumulative?.window || 1000;
  }, [chartSettings?.indicators?.bigTrades, isBigLlamaActive, llamaParams.big]);
  const cumAccumulatorRef = useRef({ totalSize: 0, startTime: 0, lastPrice: 0, buys: 0, sells: 0, minPrice: 0, maxPrice: 0 });
  const cumTimeoutRef = useRef(null);
  const cumPrevVolRef = useRef(null);
  const cumPrevTimeRef = useRef(null);
  const cumPrevPriceRef = useRef(null);
  const cumEmittedRef = useRef(false);
  useEffect(() => {
    const handleTickForAccumulator = (e) => {
      const { symbol: tickSymbol, price, volume, timestamp, side: tickSide } = e.detail;
      if (tickSymbol !== activeSymbol) return;
      const px = Number(price);
      const vol = Number(volume);
      const time = Number(timestamp);
      if (!px || vol === undefined) return;
      const now = Date.now();
      const acc = cumAccumulatorRef.current;
      let size = 0;
      if (cumPrevVolRef.current === null) {
        size = 0;
      } else if (vol < cumPrevVolRef.current) {
        size = vol;
      } else {
        size = vol - cumPrevVolRef.current;
      }
      if (size <= 0 && px === cumPrevPriceRef.current && time === cumPrevTimeRef.current) return;
      let side = tickSide;
      if (!side && cumPrevPriceRef.current) {
        if (px > cumPrevPriceRef.current) side = 'buy';
        else if (px < cumPrevPriceRef.current) side = 'sell';
      }
      if (now - acc.startTime > bigTradeWindow) {
        cumEmittedRef.current = false;
        cumAccumulatorRef.current = { totalSize: size, startTime: now, lastPrice: px, buys: side === 'buy' || !side ? size : 0, sells: side === 'sell' ? size : 0, minPrice: px, maxPrice: px };
      } else {
        acc.totalSize += size;
        acc.lastPrice = px;
        if (side === 'buy' || !side) acc.buys += size;
        else acc.sells += size;
        acc.minPrice = acc.minPrice ? Math.min(acc.minPrice, px) : px;
        acc.maxPrice = acc.maxPrice ? Math.max(acc.maxPrice, px) : px;
      }
      cumPrevVolRef.current = vol;
      cumPrevPriceRef.current = px;
      cumPrevTimeRef.current = time;
      
      const baseCumThreshold = settingsRef.current?.indicators?.bigTrades?.cumulative?.threshold || 500;
      const cumThreshold = isBigLlamaActive && llamaParams.big?.minVol ? llamaParams.big.minVol : baseCumThreshold;
      const baseAbsFactor = settingsRef.current?.indicators?.bigTrades?.cumulative?.absorptionFactor || 2.0;
      const absFactor = isBigLlamaActive && llamaParams.big?.absorptionFactor ? llamaParams.big.absorptionFactor : baseAbsFactor;
      
      const acc2 = cumAccumulatorRef.current;
      if (acc2.totalSize >= cumThreshold && !cumEmittedRef.current) {
        cumEmittedRef.current = true;
        const dominantSide = acc2.buys >= acc2.sells ? 'buy' : 'sell';
        const maxDist = acc2.lastPrice * (absFactor / 10000.0);
        const isAbsorption = (acc2.maxPrice - acc2.minPrice) <= maxDist;
        
        const trade = {
          id: acc2.startTime + Math.random(),
          time: new Date().toLocaleTimeString('en-US', { hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit' }),
          price: acc2.lastPrice,
          size: acc2.totalSize,
          side: dominantSide,
          timestamp: Date.now(),
          totalVolume: acc2.totalSize,
          bt_type: 'cumulative',
          isAbsorption: isAbsorption
        };
        setLiveAggregatedTrades((prev) => [trade, ...prev].slice(0, 100));
      }
      if (cumTimeoutRef.current) clearTimeout(cumTimeoutRef.current);
      cumTimeoutRef.current = setTimeout(() => {
        const a = cumAccumulatorRef.current;
        if (a.totalSize > 0 && !cumEmittedRef.current) {
          const dominantSide = a.buys >= a.sells ? 'buy' : 'sell';
          const maxDist2 = a.lastPrice * ((isBigLlamaActive && llamaParams.big?.absorptionFactor ? llamaParams.big.absorptionFactor : (settingsRef.current?.indicators?.bigTrades?.cumulative?.absorptionFactor || 2.0)) / 10000.0);
          const isAbsorption2 = (a.maxPrice - a.minPrice) <= maxDist2;
          
          const trade = {
            id: a.startTime + Math.random(),
            time: new Date().toLocaleTimeString('en-US', { hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit' }),
            price: a.lastPrice,
            size: a.totalSize,
            side: dominantSide,
            timestamp: Date.now(),
            totalVolume: a.totalSize,
            bt_type: 'cumulative',
            isAbsorption: isAbsorption2
          };
          setLiveAggregatedTrades((prev) => [trade, ...prev].slice(0, 100));
        }
        cumEmittedRef.current = false;
      }, bigTradeWindow + 100);
    };
    window.addEventListener('market_tick', handleTickForAccumulator);
    return () => window.removeEventListener('market_tick', handleTickForAccumulator);
  }, [activeSymbol, bigTradeWindow]);
  useEffect(() => {
    cumAccumulatorRef.current = { totalSize: 0, startTime: 0, lastPrice: 0, buys: 0, sells: 0 };
    cumPrevVolRef.current = null;
    cumPrevTimeRef.current = null;
    if (cumTimeoutRef.current) clearTimeout(cumTimeoutRef.current);
  }, [activeSymbol]);
  useTradeStream(
    activeSymbol,
    tickData?.last,
    tickData?.volume,
    tickData?.time_msc || Date.now(),
    handleNewRealTrade,
    false,
    tickData?.side,
    0,
    `chart_${chartId}`
  );
  const [overlaySettings, setOverlaySettings] = useState({
    minVol: 100,
    buyColor: "#10b981",
    sellColor: "#ef4444",
    opacity: 0.4
  });
  const [volumeColor, setVolumeColor] = useState("#26a69a");
  const [deltaColor, setDeltaColor] = useState("#3b82f6");
  const [showWatermark, setShowWatermark] = useState(
    chartSettings?.layout?.showWatermark ??
    (localStorage.getItem("chart_show_watermark") ?? "true") === "true"
  );
  useEffect(() => {
    if (onLlamaActiveChange) {
      onLlamaActiveChange(isBigLlamaActive);
    }
  }, [isBigLlamaActive, onLlamaActiveChange]);
  const [volPanelTop, setVolPanelTop] = useState(() => {
    if (chartSettings?.layout?.volumeHeight !== undefined) {
      const vh = chartSettings.layout.volumeHeight / 100;
      const dh = (chartSettings.layout.deltaHeight || 15) / 100;
      return 1 - vh - (showDelta ? dh : 0);
    }
    const saved = localStorage.getItem(`chart_${chartId}_vol_top`);
    return saved !== null ? parseFloat(saved) : 0.70;
  });
  const [deltaPanelTop, setDeltaPanelTop] = useState(() => {
    if (chartSettings?.layout?.deltaHeight !== undefined) {
      return 1 - chartSettings.layout.deltaHeight / 100;
    }
    const saved = localStorage.getItem(`chart_${chartId}_delta_top`);
    return saved !== null ? parseFloat(saved) : 0.85;
  });
  const [isLeftAxisVisible, setIsLeftAxisVisible] = useState(false);
  const [chartMenu, setChartMenu] = useState(null);
  const prevSymbolRef = useRef(activeSymbol);
  const prevTimeframeRef = useRef(activeTimeframe);
  const lastBarTimeRef = useRef(0);
  const lastFinalVolRef = useRef(0);
  const lastFinalDeltaRef = useRef(0);
  const lastLerpTimeRef = useRef(0);
  const isInitializedRef = useRef(false);
  const [volumeOpacity, setVolumeOpacity] = useState(0.8);
  const [deltaOpacity, setDeltaOpacity] = useState(0.8);
  const loadSettings = () => {
    const currentPlatform = detectPlatformType();
    const platformConfig = getPlatformConfig(currentPlatform);
    const btPrefix = `bt_${activeSymbol}_`;
    const savedMinVol = localStorage.getItem(btPrefix + "min_vol");
    const minVol = savedMinVol ? parseInt(savedMinVol) : platformConfig.bigTradeMinSize;
    const buyColor = localStorage.getItem(btPrefix + "buy_color") || "#10b981";
    const sellColor = localStorage.getItem(btPrefix + "sell_color") || "#ef4444";
    const opacity = parseFloat(localStorage.getItem(btPrefix + "opacity") || "0.4");
    const savedBubbleScale = localStorage.getItem(btPrefix + "bubble_scale");
    const bubbleScale = savedBubbleScale ? parseFloat(savedBubbleScale) : platformConfig.bigTradeScale;
    const textSize = parseFloat(localStorage.getItem(btPrefix + "text_size") || "1.0");
    setOverlaySettings({ minVol, buyColor, sellColor, opacity, bubbleScale, textSize });
    if (chartSettings?.indicators?.bigTrades) {
      const bt = chartSettings.indicators.bigTrades;
      setOverlaySettings((prev) => ({
        ...prev,
        minVol: bt.minVolume ?? prev.minVol,
        buyColor: bt.buyColor ?? prev.buyColor,
        sellColor: bt.sellColor ?? prev.sellColor,
        opacity: bt.opacity ?? prev.opacity,
        bubbleScale: bt.bubbleScale ?? prev.bubbleScale,
        textSize: bt.textSize ?? prev.textSize
      }));
    }
    const volColor = localStorage.getItem(`vol_color_${activeSymbol}`) || "#26a69a";
    const delColor = localStorage.getItem(`del_color_${activeSymbol}`) || "#3b82f6";
    setVolumeColor(volColor);
    setDeltaColor(delColor);
    if (chartSettings) {
      if (chartSettings.filters) {
        const { minVol, volumeColor, deltaColor, volumeOpacity: vOp, deltaOpacity: dOp } = chartSettings.filters;
        if (minVol !== undefined && minVol !== null) setOverlaySettings((prev) => ({ ...prev, minVol }));
        if (volumeColor) setVolumeColor(volumeColor);
        if (deltaColor) setDeltaColor(deltaColor);
        if (vOp !== undefined) setVolumeOpacity(vOp);
        if (dOp !== undefined) setDeltaOpacity(dOp);
      }
    }
  };
  const [currentPlatform, setCurrentPlatformState] = React.useState(() => detectPlatformType());
  useEffect(() => {
    const onPlatformReset = () => {
      const newPlatform = detectPlatformType();
      setCurrentPlatformState(newPlatform);
      try {
        if (candleSeriesRef.current) candleSeriesRef.current.setData([]);
        if (areaSeriesRef.current) areaSeriesRef.current.setData([]);
        if (volumeSeriesRef.current) volumeSeriesRef.current.setData([]);
        if (deltaSeriesRef.current) deltaSeriesRef.current.setData([]);
        if (chartRef.current) chartRef.current.timeScale().fitContent();
      } catch (e) { }
      if (fpRendererRef.current) fpRendererRef.current.setEnabled(false);
      setFootprintData(null);
      setFootprintMode('off');
    };
    window.addEventListener('frontend_data_reset', onPlatformReset);
    return () => window.removeEventListener('frontend_data_reset', onPlatformReset);
  }, []);
  useEffect(() => {
    loadSettings();
  }, [activeSymbol, currentPlatform]);
  useEffect(() => {
    if (chartSettings) {
      if (chartSettings.filters) {
        const { minVol, volumeColor, deltaColor, volumeOpacity: vOp, deltaOpacity: dOp } = chartSettings.filters;
        if (minVol !== undefined && minVol !== null) setOverlaySettings((prev) => ({ ...prev, minVol }));
        if (volumeColor) setVolumeColor(volumeColor);
        if (deltaColor) setDeltaColor(deltaColor);
        if (vOp !== undefined) setVolumeOpacity(vOp);
        if (dOp !== undefined) setDeltaOpacity(dOp);
      }
      if (chartSettings.indicators?.bigTrades) {
        const bt = chartSettings.indicators.bigTrades;
        setOverlaySettings((prev) => ({
          ...prev,
          minVol: bt.minVolume ?? prev.minVol,
          buyColor: bt.buyColor ?? prev.buyColor,
          sellColor: bt.sellColor ?? prev.sellColor,
          opacity: bt.opacity ?? prev.opacity,
          bubbleScale: bt.bubbleScale ?? prev.bubbleScale,
          textSize: bt.textSize ?? prev.textSize
        }));
      }
      if (chartSettings.layout) {
        const { volumeHeight: vh, deltaHeight: dh } = chartSettings.layout;
        if (vh !== undefined || dh !== undefined) {
          const finalVh = (vh !== undefined ? vh : 15) / 100;
          const finalDh = (dh !== undefined ? dh : 15) / 100;
          const dTop = 1 - finalDh;
          const vTop = showDelta ? (dTop - finalVh) : (1 - finalVh);
          setDeltaPanelTop(dTop);
          setVolPanelTop(vTop);
        }
      }
      const appearance = { ...globalAppearance, ...(chartSettings?.appearance || {}) };
      if (chartRef.current) {
        chartRef.current.applyOptions({
          layout: { background: { type: 'solid', color: appearance.backgroundColor || "#0e1118" } }
        });
        if (candleSeriesRef.current) {
          candleSeriesRef.current.applyOptions({
            upColor: appearance.upColor,
            downColor: appearance.downColor,
            borderUpColor: appearance.borderUpColor,
            borderDownColor: appearance.borderDownColor,
            wickUpColor: appearance.borderUpColor,
            wickDownColor: appearance.borderDownColor,
            borderVisible: appearance.borderVisible !== false
          });
        }
      }
    }
  }, [chartSettings, globalAppearance]);
  useEffect(() => {
    localStorage.setItem(`show_volume_${activeSymbol}`, JSON.stringify(showVolume));
  }, [showVolume, activeSymbol]);
  useEffect(() => {
    localStorage.setItem(`show_delta_${activeSymbol}`, JSON.stringify(showDelta));
  }, [showDelta, activeSymbol]);
  useEffect(() => {
    const handleUpdate = (e) => {
      if (e.detail && e.detail.symbol === activeSymbol) loadSettings();
    };
    window.addEventListener("settings_updated", handleUpdate);
    return () => window.removeEventListener("settings_updated", handleUpdate);
  }, [activeSymbol]);
  useEffect(() => {
    if (chartRef.current) {
      if (volumeSeriesRef.current) volumeSeriesRef.current.applyOptions({ color: volumeColor });
      if (deltaSeriesRef.current) deltaSeriesRef.current.applyOptions({ color: deltaColor });
    }
  }, [volumeColor, deltaColor, volumeOpacity, deltaOpacity]);
  useEffect(() => {
    if (isBigLlamaActive && llamaParams.big) {
      setOverlaySettings((prev) => ({ ...prev, minVol: llamaParams.big.minVol || prev.minVol }));
    }
  }, [llamaParams.big, isBigLlamaActive]);
  useEffect(() => {
    if (!chartContainerRef.current) return;
    const currentPlatform = detectPlatformType();
    const platformConfig = getPlatformConfig(currentPlatform);
    const showGrid = chartSettings?.layout?.showGrid ?? (localStorage.getItem("chart_show_grid") ?? "true") === "true";
    const chart = LightweightCharts.createChart(chartContainerRef.current, {
      layout: {
        background: {
          type: 'solid',
          color: (showAllOverlays && chartSettings?.overlays?.showBookmap) ? "transparent" : (settingsRef.current?.appearance?.backgroundColor || localStorage.getItem("global_chart_bg_color") || "#000000")
        },
        textColor: "#94a3b8",
        fontSize: 11,
        fontFamily: "'JetBrains Mono', 'Cascadia Code', monospace"
      },
      watermark: { visible: false },
      grid: {
        vertLines: { color: "#1a1a1a", style: 0, visible: showGrid },
        horzLines: { color: "#1a1a1a", style: 0, visible: showGrid }
      },
      width: chartContainerRef.current.clientWidth,
      height: chartContainerRef.current.clientHeight,
      timeScale: {
        visible: false,
        timeVisible: true,
        secondsVisible: true,
        borderColor: "rgba(255,255,255,0.08)",
        rightOffset: 12,
        barSpacing: 6,
        minBarSpacing: 0.5,
        fixLeftEdge: false,
        fixRightEdge: false,
        lockVisibleTimeRangeOnResize: true,
        shiftVisibleRangeOnNewBar: false,
        tickMarkFormatter: (time, tickMarkType, locale) => {
          const date = new Date(time * 1000);
          const day = date.getDate().toString().padStart(2, '0');
          const months = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"];
          const month = months[date.getMonth()];
          const year = date.getFullYear().toString().slice(-2);
          if (tickMarkType === 0) return String(date.getFullYear());
          if (tickMarkType === 1) return month + " '" + year;
          if (tickMarkType === 2) return day + " " + month;
          const hh = String(date.getHours()).padStart(2, '0');
          const mm = String(date.getMinutes()).padStart(2, '0');
          return hh + ":" + mm;
        }
      },
      rightPriceScale: {
        borderColor: "rgba(255, 255, 255, 0.12)",
        scaleMargins: { top: 0.1, bottom: 0.1 },
        mode: 1,
        autoScale: true,
        alignLabels: false,
        visible: true,
        drawTicks: true,
        borderVisible: true,
        minimumWidth: 75,
        entireTextOnly: true
      },
      leftPriceScale: {
        borderColor: "transparent",
        scaleMargins: { top: 0.2, bottom: 0.2 },
        autoScale: true,
        visible: false,
        minimumWidth: 0
      },
      crosshair: {
        mode: LightweightCharts.CrosshairMode.Magnet,
        vertLine: { visible: true, labelVisible: true, style: 2, width: 1, color: "rgba(148, 163, 184, 0.5)" },
        horzLine: { visible: true, labelVisible: true }
      },
      handleScroll: { mouseWheel: true, pressedMouseMove: true, horzTouchDrag: true, vertTouchDrag: false },
      handleScale: {
        axisPressedMouseMove: { time: true, price: true },
        mouseWheel: true, pinch: true, axisDoubleClickReset: true, wheelSpeed: 1
      },
      kineticScroll: { touch: true, mouse: false },
      localization: {
        priceFormatter: (price) => {
          if (window.getSymbolPrecision) {
            const precision = window.getSymbolPrecision(activeSymbolRef.current, detectPlatformType(), price);
            return price.toFixed(precision.digits);
          }
          return price.toFixed(symbolMetadataRef.current?.digits || 5);
        },
        timeFormatter: (time) => {
          const date = new Date(time * 1000);
          return date.toLocaleTimeString("en-US", { hour12: false, hour: "2-digit", minute: "2-digit" });
        }
      }
    });
    const candleSeries = chart.addCandlestickSeries({
      upColor: chartSettings?.appearance?.upColor || localStorage.getItem("global_candle_up_color") || "#00d084",
      downColor: chartSettings?.appearance?.downColor || localStorage.getItem("global_candle_down_color") || "#ff4757",
      borderVisible: chartSettings?.appearance?.borderVisible !== false && localStorage.getItem("global_candle_border_visible") !== "false",
      borderUpColor: chartSettings?.appearance?.borderUpColor || localStorage.getItem("global_candle_border_color") || "#00b874",
      borderDownColor: chartSettings?.appearance?.borderDownColor || localStorage.getItem("global_candle_border_color") || "#e83945",
      wickUpColor: chartSettings?.appearance?.borderUpColor || localStorage.getItem("global_candle_border_color") || "#00b874",
      wickDownColor: chartSettings?.appearance?.borderDownColor || localStorage.getItem("global_candle_border_color") || "#e83945",
      wickVisible: true,
      lastValueVisible: true,
      priceLineVisible: false,
      priceLineWidth: 1,
      priceLineColor: "rgba(255, 255, 255, 0.28)",
      priceLineStyle: LightweightCharts.LineStyle.Solid,
      priceFormat: {
        type: "price",
        precision: window.getSymbolPrecision ? window.getSymbolPrecision(activeSymbolRef.current, detectPlatformType()).digits : symbolMetadataRef.current?.digits || platformConfig.priceDecimals,
        minMove: window.getSymbolPrecision ? window.getSymbolPrecision(activeSymbolRef.current, detectPlatformType()).tick_size : symbolMetadataRef.current?.tick_size || (platformConfig.priceDecimals === 4 ? 0.0001 : 0.01)
      },
      baseLineVisible: false,
      crosshairMarkerVisible: true,
      crosshairMarkerRadius: 3,
      crosshairMarkerBorderColor: "#ffffff",
      crosshairMarkerBackgroundColor: "#000000",
      visible: chartType === "candle"
    });
    candleSeries._symbol = getUniversalSymbol(activeSymbol, platformConfig.platform);
    candleSeries._originalSymbol = activeSymbol;
    const refreshSeriesPrecision = (price) => {
      if (!window.getSymbolPrecision || !candleSeriesRef.current) return;
      const p = window.getSymbolPrecision(activeSymbolRef.current, detectPlatformType(), price);
      const currentOptions = candleSeriesRef.current.options();
      if (currentOptions.priceFormat.precision !== p.digits) {
        candleSeriesRef.current.applyOptions({
          priceFormat: { type: "price", precision: p.digits, minMove: p.tick_size }
        });
        if (areaSeriesRef.current) {
          areaSeriesRef.current.applyOptions({
            priceFormat: { type: "price", precision: p.digits, minMove: p.tick_size }
          });
        }
      }
    };
    window._refreshChartPrecision = refreshSeriesPrecision;
    const areaSeries = chart.addAreaSeries({
      topColor: "rgba(38, 166, 154, 0.4)",
      bottomColor: "rgba(38, 166, 154, 0.0)",
      lineColor: "rgba(38, 166, 154, 1)",
      lineWidth: 2,
      priceLineVisible: false,
      lastValueVisible: true,
      priceFormat: {
        type: "price",
        precision: window.getSymbolPrecision ? window.getSymbolPrecision(activeSymbolRef.current, detectPlatformType()).digits : symbolMetadataRef.current?.digits || platformConfig.priceDecimals,
        minMove: window.getSymbolPrecision ? window.getSymbolPrecision(activeSymbolRef.current, detectPlatformType()).tick_size : symbolMetadataRef.current?.tick_size || (platformConfig.priceDecimals === 4 ? 0.0001 : 0.01)
      },
      visible: chartType === "area"
    });
    areaSeries._symbol = getUniversalSymbol(activeSymbol, platformConfig.platform);
    areaSeries._originalSymbol = activeSymbol;

    const lineSeries = chart.addLineSeries({
      color: chartSettings?.appearance?.upColor || localStorage.getItem("global_candle_up_color") || "#26a69a",
      lineWidth: 2,
      priceLineVisible: false,
      lastValueVisible: true,
      priceFormat: {
        type: "price",
        precision: window.getSymbolPrecision ? window.getSymbolPrecision(activeSymbolRef.current, detectPlatformType()).digits : symbolMetadataRef.current?.digits || platformConfig.priceDecimals,
        minMove: window.getSymbolPrecision ? window.getSymbolPrecision(activeSymbolRef.current, detectPlatformType()).tick_size : symbolMetadataRef.current?.tick_size || (platformConfig.priceDecimals === 4 ? 0.0001 : 0.01)
      },
      visible: chartType === "line"
    });
    lineSeries._symbol = getUniversalSymbol(activeSymbol, platformConfig.platform);
    lineSeries._originalSymbol = activeSymbol;

    const barSeries = chart.addBarSeries({
      upColor: chartSettings?.appearance?.upColor || localStorage.getItem("global_candle_up_color") || "#26a69a",
      downColor: chartSettings?.appearance?.downColor || localStorage.getItem("global_candle_down_color") || "#ef5350",
      openVisible: true,
      thinBars: false,
      priceLineVisible: false,
      lastValueVisible: true,
      priceFormat: {
        type: "price",
        precision: window.getSymbolPrecision ? window.getSymbolPrecision(activeSymbolRef.current, detectPlatformType()).digits : symbolMetadataRef.current?.digits || platformConfig.priceDecimals,
        minMove: window.getSymbolPrecision ? window.getSymbolPrecision(activeSymbolRef.current, detectPlatformType()).tick_size : symbolMetadataRef.current?.tick_size || (platformConfig.priceDecimals === 4 ? 0.0001 : 0.01)
      },
      visible: chartType === "bar"
    });
    barSeries._symbol = getUniversalSymbol(activeSymbol, platformConfig.platform);
    barSeries._originalSymbol = activeSymbol;

    chartRef.current = chart;
    candleSeriesRef.current = candleSeries;
    areaSeriesRef.current = areaSeries;
    lineSeriesRef.current = lineSeries;
    barSeriesRef.current = barSeries;

    // Unified Volume Series
    const vSeries = chart.addHistogramSeries({
      color: typeof volumeColor === 'string' ? volumeColor : "#26a69a",
      priceFormat: { type: "volume" },
      priceScaleId: 'volume',
      lastValueVisible: true,
      priceLineVisible: false,
    });

    // Unified Delta Series (histogram / deltaBars mode)
    const dSeries = chart.addHistogramSeries({
      color: typeof deltaColor === 'string' ? deltaColor : "#3b82f6",
      priceFormat: { type: 'price', precision: 0, minMove: 0.01 },
      priceScaleId: 'delta',
      lastValueVisible: true,
      priceLineVisible: false,
    });
    volumeSeriesRef.current = vSeries;
    deltaSeriesRef.current = dSeries;

    // Cumulative Delta Candle Series
    const deltaMode = chartSettings?.filters?.deltaDisplayMode || 'histogram';
    const cumUpColor = chartSettings?.filters?.deltaCumPositiveColor || '#26a69a';
    const cumDownColor = chartSettings?.filters?.deltaCumNegativeColor || '#ef5350';
    const cumLineColor = chartSettings?.filters?.deltaCumLineColor || '#3b82f6';
    const cumLineWidth = chartSettings?.filters?.deltaCumLineWidth || 2;

    const dCumCandleSeries = chart.addCandlestickSeries({
      upColor: cumUpColor,
      downColor: cumDownColor,
      borderUpColor: cumUpColor,
      borderDownColor: cumDownColor,
      wickUpColor: cumUpColor,
      wickDownColor: cumDownColor,
      wickVisible: true,
      priceFormat: { type: 'price', precision: 0, minMove: 1 },
      priceScaleId: 'delta',
      lastValueVisible: true,
      priceLineVisible: false,
      visible: false,
    });
    deltaCumCandleSeriesRef.current = dCumCandleSeries;

    // Cumulative Delta Line Series
    const dCumLineSeries = chart.addLineSeries({
      color: cumLineColor,
      lineWidth: cumLineWidth,
      priceFormat: { type: 'price', precision: 0, minMove: 1 },
      priceScaleId: 'delta',
      lastValueVisible: true,
      priceLineVisible: false,
      crosshairMarkerVisible: false,
      visible: false,
    });
    deltaCumLineSeriesRef.current = dCumLineSeries;

    const GAP = 0.01;          // margen general entre paneles
    const VOL_BOTTOM = 0.005;  // volumen pegado al piso de su contenedor
    const DELTA_TOP = 0.04;    // delta no desborda arriba hacia volumen
    // Clamp margins so top+bottom never reaches 1.0 (lightweight-charts requirement)
    const _safeMargins = (t, b) => {
      const top = Math.max(0, t);
      const bot = Math.max(0, b);
      if (top + bot >= 0.95) {
        const ratio = 0.94 / (top + bot);
        return { top: top * ratio, bottom: bot * ratio };
      }
      return { top, bottom: bot };
    };

    const initVTop = volPanelTop;
    const initDTop = deltaPanelTop;

    // ── Escala CANDLE (right) ─────────────────────────────────────────
    const initCandleBottom = showVolume
      ? (1 - initVTop + GAP)
      : showDelta
        ? (1 - initDTop + GAP)
        : 0.1;

    chart.priceScale('right').applyOptions({
      scaleMargins: _safeMargins(0.02, initCandleBottom)
    });

    // ── Escala VOLUME (pegado al piso) ───────────────────────────────
    const initVolTop = initVTop + GAP;
    const initVolBottom = showDelta
      ? (1 - initDTop + VOL_BOTTOM)
      : VOL_BOTTOM;

    chart.priceScale('volume').applyOptions({
      visible: true,
      borderVisible: false,
      autoScale: true,
      scaleMargins: _safeMargins(initVolTop, initVolBottom)
    });

    // ── Escala DELTA (no desborda arriba) ────────────────────────────
    chart.priceScale('delta').applyOptions({
      visible: true,
      borderVisible: false,
      autoScale: true,
      scaleMargins: _safeMargins(initDTop + DELTA_TOP, VOL_BOTTOM)
    });

    chart.priceScale('left').applyOptions({ visible: false });

    setIsChartReady(true);
    setIsVisible(true);
    let lastWidth = 0;
    let lastHeight = 0;
    const triggerResize = () => {
      if (!chartRef.current || !chartContainerRef.current) return;
      requestAnimationFrame(() => {
        if (chartContainerRef.current && chartRef.current) {
          const width = chartContainerRef.current.clientWidth;
          const height = chartContainerRef.current.clientHeight;
          if (width > 0 && height > 0) {
            chartRef.current.resize(width, height);
            
            const widthDiff = Math.abs(width - lastWidth);
            const heightDiff = Math.abs(height - lastHeight);
            if (lastWidth === 0 || lastHeight === 0 || widthDiff > 20 || heightDiff > 20) {
              // Layout changed (panel toggle), just resize. 
              // Removed fitContent() to preserve user's zoom/position.
            }
            
            lastWidth = width;
            lastHeight = height;
          } else {
            lastWidth = 0;
            lastHeight = 0;
          }
        }
      });
    };
    const resizeObserver = new ResizeObserver(() => triggerResize());
    if (chartContainerRef.current) resizeObserver.observe(chartContainerRef.current);
    const handleGlobalResize = () => triggerResize();
    window.addEventListener("resize", handleGlobalResize);
    window.addEventListener("focus", triggerResize);
    document.addEventListener("visibilitychange", triggerResize);

    return () => {
      if (resizeObserver) resizeObserver.disconnect();
      window.removeEventListener("resize", handleGlobalResize);
      window.removeEventListener("focus", triggerResize);
      document.removeEventListener("visibilitychange", triggerResize);
      if (chartRef.current) {
        try { chartRef.current.remove(); } catch (e) { console.warn("[CHART] Cleanup error:", e); }
      }
      chartRef.current = null;
      candleSeriesRef.current = null;
      areaSeriesRef.current = null;
      lineSeriesRef.current = null;
      barSeriesRef.current = null;
      volumeSeriesRef.current = null;
      deltaSeriesRef.current = null;
      deltaCumCandleSeriesRef.current = null;
      deltaCumLineSeriesRef.current = null;
      setIsChartReady(false);
      isInitializedRef.current = false;
      if (chartContainerRef.current) chartContainerRef.current.innerHTML = "";
    };
  }, []);

  // Panel layout margins effect - syncs scaleMargins with visual container positions
  useEffect(() => {
    if (!isChartReady || !chartRef.current) return;
    const chart = chartRef.current;

    const GAP = 0.01;
    const VOL_BOTTOM = 0.005;
    const DELTA_TOP = 0.04;
    const _safeMargins = (t, b) => {
      const top = Math.max(0, t);
      const bot = Math.max(0, b);
      if (top + bot >= 0.95) {
        const ratio = 0.94 / (top + bot);
        return { top: top * ratio, bottom: bot * ratio };
      }
      return { top, bottom: bot };
    };
    const vTop = volPanelTop;
    const dTop = deltaPanelTop;

    // ── Escala CANDLE (right) ─────────────────────────────────────────
    const candleBottom = showVolume
      ? (1 - vTop + GAP)
      : showDelta
        ? (1 - dTop + GAP)
        : 0.1;

    chart.priceScale('right').applyOptions({
      scaleMargins: _safeMargins(0.02, candleBottom)
    });

    // ── Escala VOLUME (pegado al piso) ───────────────────────────────
    if (volumeSeriesRef.current) {
      volumeSeriesRef.current.applyOptions({ visible: showVolume });
      const volTop = vTop + GAP;
      const volBottom = showDelta
        ? (1 - dTop + VOL_BOTTOM)
        : VOL_BOTTOM;

      chart.priceScale('volume').applyOptions({
        visible: showVolume,
        scaleMargins: _safeMargins(volTop, volBottom)
      });
    }

    // ── Escala DELTA (no desborda arriba) ────────────────────────────
    if (deltaSeriesRef.current) {
      const currentMode = chartSettings?.filters?.deltaDisplayMode || 'histogram';
      const isHist = currentMode === 'histogram' || currentMode === 'deltaBars' || !currentMode;
      deltaSeriesRef.current.applyOptions({ visible: showDelta && isHist });
      chart.priceScale('delta').applyOptions({
        visible: showDelta,
        scaleMargins: _safeMargins(dTop + DELTA_TOP, VOL_BOTTOM)
      });
    }

    chart.priceScale('left').applyOptions({ visible: false });
  }, [isChartReady, showVolume, showDelta, volPanelTop, deltaPanelTop]);

  // Dedicated Hover Data Effect
  useEffect(() => {
    if (!isChartReady || !chartRef.current) return;
    const chart = chartRef.current;
    const handleMove = (param) => {
      if (!param || !param.time || !param.point || !chartContainerRef.current) {
        setHoverData({ volume: null, delta: null });
        return;
      }
      const chartHeight = chartContainerRef.current.clientHeight;
      const yPct = param.point.y / chartHeight;
      const nextData = { volume: null, delta: null };
      const vSeries = volumeSeriesRef.current;
      const dSeries = deltaSeriesRef.current;
      const isOverVolume = showVolume && yPct >= (volPanelTop - 0.01) && (!showDelta || yPct < deltaPanelTop);
      const isOverDelta = showDelta && yPct >= (deltaPanelTop - 0.01);
      if (isOverVolume && vSeries) {
        const sd = param.seriesData ? param.seriesData.get(vSeries) : null;
        if (sd && typeof sd.value === 'number') {
          nextData.volume = sd.value;
        } else if (param.seriesPrices) {
          const sp = param.seriesPrices.get(vSeries);
          if (typeof sp === 'number') nextData.volume = sp;
        }
      }
      if (isOverDelta && dSeries) {
        const sd = param.seriesData ? param.seriesData.get(dSeries) : null;
        if (sd && typeof sd.value === 'number') {
          nextData.delta = sd.value;
        } else if (param.seriesPrices) {
          const sp = param.seriesPrices.get(dSeries);
          if (typeof sp === 'number') nextData.delta = sp;
        }
      }
      setHoverData(nextData);
    };
    chart.subscribeCrosshairMove(handleMove);
    return () => chart.unsubscribeCrosshairMove(handleMove);
  }, [isChartReady, showVolume, showDelta, volPanelTop, deltaPanelTop]);

  useEffect(() => {
    if (!chartRef.current) return;
    const chart = chartRef.current;
    const g = globalAppearance;
    chart.applyOptions({
      layout: {
        background: { type: 'solid', color: bgColor },
        textColor: "#94a3b8",
        fontSize: 11,
        fontFamily: "Inter, sans-serif"
      },
      grid: {
        vertLines: { color: "#1a1a1a", visible: showGrid },
        horzLines: { color: "#1a1a1a", visible: showGrid }
      }
    });
    if (candleSeriesRef.current) {
      candleSeriesRef.current.applyOptions({
        upColor: g.upColor,
        downColor: g.downColor,
        borderUpColor: g.borderUpColor,
        borderDownColor: g.borderDownColor,
        wickUpColor: g.borderUpColor,
        wickDownColor: g.borderDownColor,
        borderVisible: g.borderVisible
      });
    }
    if (volumeSeriesRef.current) volumeSeriesRef.current.applyOptions({ color: volumeColor });
    if (deltaSeriesRef.current) deltaSeriesRef.current.applyOptions({ color: deltaColor });
    chart.timeScale().applyOptions({ visible: true });
  }, [bgColor, showGrid, volumeColor, deltaColor, isChartReady, showVolume, showDelta, globalAppearance]);

  useEffect(() => {
    if (!isChartReady || !chartRef.current) return;
    const crosshairVisible = activeTool === "crosshair";
    chartRef.current.applyOptions({
      crosshair: {
        mode: LightweightCharts.CrosshairMode.Normal,
        vertLine: { visible: crosshairVisible, labelVisible: crosshairVisible, style: 2, width: 1, color: "#758696" },
        horzLine: { visible: crosshairVisible, labelVisible: crosshairVisible, style: 2, width: 1, color: "#758696" }
      }
    });
  }, [activeTool, isChartReady]);

  const getTimeframeSeconds = useCallback((tf) => {
    if (!tf) return 60;
    const value = parseInt(tf) || 1;
    if (tf.includes("M") && !tf.includes("m")) return value * 2592000;
    if (tf.toLowerCase().includes("mn") || tf.toLowerCase().includes("mo")) return value * 2592000;
    if (tf.toLowerCase().includes("w")) return value * 604800;
    if (tf.toLowerCase().includes("d")) return value * 86400;
    if (tf.toLowerCase().includes("h")) return value * 3600;
    if (tf.includes("m")) return value * 60;
    if (tf.toLowerCase().includes("s")) return value;
    return 60;
  }, []);

  const formatCandle = useCallback((d) => {
    const open = +d.Open || +d.open;
    const high = +d.High || +d.high;
    const low = +d.Low || +d.low;
    const close = +d.Close || +d.close;
    const volume = +d.Volume || +d.volume || 0;
    const range = high - low;
    const move = close - open;
    let delta = Number(d.delta || d.Delta || 0);
    if (delta === 0 && volume > 0) {
      // Improved heuristic: only calculate delta if obviously missing (0.0)
      delta = range === 0 ? (move >= 0 ? volume : -volume) : (volume * (move / range));
    }
    let time;
    if (typeof d.time === "string") {
      let timeStr = d.time.replace(" ", "T");
      if (!timeStr.endsWith('Z') && !timeStr.includes('+')) timeStr += 'Z';
      time = new Date(timeStr).getTime() / 1000;
    } else if (typeof d.time === "object" && d.time !== null) {
      if (d.time instanceof Date) {
        time = d.time.getTime() / 1000;
      } else if (d.time.timestamp !== undefined) {
        time = Number(d.time.timestamp);
        if (time > 10000000000) time = time / 1000;
      } else {
        time = Number(d.time) || Date.now() / 1000;
      }
    } else {
      time = Number(d.time);
    }
    if (isNaN(time)) time = Math.floor(Date.now() / 1000);
    if (time > 10000000000) time = time / 1000;
    time = Math.floor(time);
    const tfSeconds = getTimeframeSeconds(activeTimeframe);
    time = Math.floor(time / tfSeconds) * tfSeconds;
    return { time, open, high, low, close, volume, delta: Number(delta) || 0 };
  }, [activeTimeframe, getTimeframeSeconds]);

  const lastBar = useMemo(() => {
    let bar = null;
    if (allBarsRef.current && allBarsRef.current.length > 0) {
      bar = allBarsRef.current[allBarsRef.current.length - 1];
    } else {
      const liveDataArr = Array.isArray(liveData) ? liveData : liveData ? [liveData] : [];
      const combined = [...(historicalData || []), ...liveDataArr];
      if (combined.length > 0) bar = formatCandle(combined[combined.length - 1]);
    }
    if (!bar) return null;
    let time = bar.time;
    if (typeof time === 'string') {
      const parsed = new Date(time.replace(' ', 'T')).getTime();
      if (!isNaN(parsed)) time = Math.floor(parsed / 1000);
    } else if (typeof time === 'number' && time > 10000000000) {
      time = Math.floor(time / 1000);
    }
    return { ...bar, time };
  }, [historicalData, liveData, activeSymbol, formatCandle]);

  const aggregateData = useCallback((data) => {
    if (!data || data.length === 0) return [];
    const isValidCandle = (d) => {
      if (!d) return false;
      const t = typeof d.time === 'number' ? d.time :
        (typeof d.time === 'string' ? new Date(d.time.replace(' ', 'T')).getTime() / 1000 : 0);
      if (isNaN(t) || t <= 0) return false;
      if (isNaN(d.open) || isNaN(d.high) || isNaN(d.low) || isNaN(d.close)) return false;
      if (!isFinite(d.open) || !isFinite(d.high) || !isFinite(d.low) || !isFinite(d.close)) return false;
      if (d.open <= 0 || d.high <= 0 || d.low <= 0 || d.close <= 0) return false;
      return true;
    };
    const sorted = [...data].map((item) => formatCandle(item)).filter(isValidCandle).sort((a, b) => a.time - b.time);
    const aggregated = [];
    let current = null;
    for (const candle of sorted) {
      if (!current || candle.time !== current.time) {
        if (current) aggregated.push(current);
        current = { ...candle };
      } else {
        current.high = Math.max(current.high, candle.high);
        current.low = Math.min(current.low, candle.low);
        current.close = candle.close;
        current.volume += candle.volume || 0;
        current.delta += candle.delta || 0;
      }
    }
    if (current) aggregated.push(current);
    return aggregated;
  }, [formatCandle]);

  const lastHistoryLengthRef = useRef(0);
  const prevFirstTimeRef = useRef(0);

  // ─── MAIN DATA LOADING EFFECT ────────────────────────────────────────────────
  useEffect(() => {
    if (!candleSeriesRef.current) return;

    const dataToLoadState = historicalData && historicalData.length > 0 ? historicalData : liveData;
    const currentFirstTime = dataToLoadState && dataToLoadState.length > 0 ? dataToLoadState[0].time : 0;
    const isSymbolChanged = prevSymbolRef.current !== activeSymbol;
    const isTimeframeChanged = prevTimeframeRef.current !== activeTimeframe;
    const isFirstTimeChanged = prevFirstTimeRef.current !== currentFirstTime && currentFirstTime !== 0;
    const shouldFullReset = isSymbolChanged || isTimeframeChanged || isFirstTimeChanged || !isInitializedRef.current;

    if (shouldFullReset && isInitializedRef.current) {
      try {
        if (candleSeriesRef.current) candleSeriesRef.current.setData([]);
        if (areaSeriesRef.current) areaSeriesRef.current.setData([]);
        if (volumeSeriesRef.current) volumeSeriesRef.current.setData([]);
        if (deltaSeriesRef.current) deltaSeriesRef.current.setData([]);
      } catch (e) { }
      allBarsRef.current = [];
      lastFinalVolRef.current = 0;
      lastFinalDeltaRef.current = 0;
      lastLerpTimeRef.current = 0;
      isInitializedRef.current = false;
      setIsChartReady(false);
      if (candleSeriesRef.current) candleSeriesRef.current.setMarkers([]);
      if (chartRef.current) {
        try { chartRef.current.timeScale().scrollToPosition(0); } catch (e) { }
      }
    }

    // ── 1. HISTORICAL DATA INITIALIZATION ──
    if (!isInitializedRef.current) {
      if (!historicalData || historicalData.length === 0) return;
      
      const uniqueData = aggregateData(historicalData);
      if (uniqueData.length > 0) {
        if (window._refreshChartPrecision) window._refreshChartPrecision(uniqueData[uniqueData.length - 1].close);
        try {
          candleSeriesRef.current.setData(uniqueData);
          if (areaSeriesRef.current) areaSeriesRef.current.setData(uniqueData.map((d) => ({ time: d.time, value: d.close })));
          if (lineSeriesRef.current) lineSeriesRef.current.setData(uniqueData.map((d) => ({ time: d.time, value: d.close })));
          if (barSeriesRef.current) barSeriesRef.current.setData(uniqueData);
        } catch (e) { console.warn(e); }

        allBarsRef.current = [...uniqueData];

        const { vScale, dScale } = _getPlatformScales(activeSymbol);
        const volumeData = [];
        const deltaData = [];
        for (let i = 0; i < uniqueData.length; i++) {
          const d = uniqueData[i];
          const volVal = isFinite(d.volume) ? d.volume * vScale : 0;
          const deltaVal = isFinite(d.delta) ? d.delta * dScale : 0;
          const vHex = _ensureHex(d.close >= d.open ? volumeColor : "#f87171");
          const dHex = _ensureHex(d.delta >= 0 ? deltaColor : "#f59e0b");
          
          if (isFinite(volVal)) {
            volumeData.push({ time: d.time, value: volVal, color: _getRgba(vHex, volumeOpacity) });
          }
          if (isFinite(deltaVal)) {
            deltaData.push({ time: d.time, value: deltaVal, color: _getRgba(dHex, deltaOpacity) });
          }
        }
        
        if (volumeSeriesRef.current) {
          try {
            volumeSeriesRef.current.setData(showVolume ? volumeData : []);
            volumeSeriesRef.current.applyOptions({ visible: showVolume });
          } catch (e) { }
        }

        const currentDeltaMode = chartSettings?.filters?.deltaDisplayMode || 'histogram';
        const isHistMode = currentDeltaMode === 'histogram' || currentDeltaMode === 'deltaBars';
        const isCumCandleMode = currentDeltaMode === 'cumulativeCandles';
        const isCumLineMode = currentDeltaMode === 'cumulativeLine';

        if (deltaSeriesRef.current) {
          try {
            deltaSeriesRef.current.setData((showDelta && isHistMode) ? deltaData : []);
            deltaSeriesRef.current.applyOptions({ visible: showDelta && isHistMode });
          } catch (e) { }
        }

        if (showDelta && (isCumCandleMode || isCumLineMode)) {
          const { candles: cumCandles, lineData: cumLine } = _computeCumulativeDelta(uniqueData, dScale);
          if (deltaCumCandleSeriesRef.current) {
            try {
              deltaCumCandleSeriesRef.current.setData(isCumCandleMode ? cumCandles : []);
              deltaCumCandleSeriesRef.current.applyOptions({
                visible: showDelta && isCumCandleMode,
                upColor: chartSettings?.filters?.deltaCumPositiveColor || '#26a69a',
                downColor: chartSettings?.filters?.deltaCumNegativeColor || '#ef5350',
                borderUpColor: chartSettings?.filters?.deltaCumPositiveColor || '#26a69a',
                borderDownColor: chartSettings?.filters?.deltaCumNegativeColor || '#ef5350',
                wickUpColor: chartSettings?.filters?.deltaCumPositiveColor || '#26a69a',
                wickDownColor: chartSettings?.filters?.deltaCumNegativeColor || '#ef5350'
              });
            } catch (e) { }
          }
          if (deltaCumLineSeriesRef.current) {
            try {
              deltaCumLineSeriesRef.current.setData(isCumLineMode ? cumLine : []);
              deltaCumLineSeriesRef.current.applyOptions({
                visible: showDelta && isCumLineMode,
                color: chartSettings?.filters?.deltaCumLineColor || '#3b82f6',
                lineWidth: chartSettings?.filters?.deltaCumLineWidth || 2
              });
            } catch (e) { }
          }
        } else {
          if (deltaCumCandleSeriesRef.current) try { deltaCumCandleSeriesRef.current.setData([]); deltaCumCandleSeriesRef.current.applyOptions({ visible: false }); } catch (e) { }
          if (deltaCumLineSeriesRef.current) try { deltaCumLineSeriesRef.current.setData([]); deltaCumLineSeriesRef.current.applyOptions({ visible: false }); } catch (e) { }
        }

        if (chartRef.current) {
          chartRef.current._lastDataLoadTime = Date.now();
        }

        if (shouldFullReset || activeSymbol !== prevSymbolRef.current) {
          if (lastSyncTimeoutRef.current) clearTimeout(lastSyncTimeoutRef.current);
          lastSyncTimeoutRef.current = setTimeout(() => {
            if (!chartRef.current) return;
            
            if (restoredRangeRef.current) {
              const adjusted = getAdjustedRange(restoredRangeRef.current, uniqueData.length);
              const savedTotal = restoredRangeRef.current.totalBars || 0;
              const isAtRightEdge = savedTotal > 10 && restoredRangeRef.current.to >= (savedTotal - 5);
              if (isAtRightEdge) {
                if (adjusted) chartRef.current.timeScale().setVisibleLogicalRange(adjusted);
              } else if (restoredRangeRef.current.timeRange) {
                chartRef.current.timeScale().setVisibleRange(restoredRangeRef.current.timeRange);
              } else {
                if (adjusted) chartRef.current.timeScale().setVisibleLogicalRange(adjusted);
              }
            } else {
              const totalBars = uniqueData.length;
              if (totalBars > 150) {
                chartRef.current.timeScale().setVisibleLogicalRange({ from: totalBars - 150, to: totalBars + 2 });
              } else {
                chartRef.current.timeScale().fitContent();
                requestAnimationFrame(() => {
                  const newRange = chartRef.current?.timeScale().getVisibleLogicalRange();
                  if (newRange && chartRef.current) chartRef.current.timeScale().setVisibleLogicalRange(newRange);
                });
              }
            }
            lastSyncTimeoutRef.current = null;
          }, 200);
        }

        isInitializedRef.current = true;
        setIsChartReady(true);
        prevSymbolRef.current = activeSymbol;
        prevTimeframeRef.current = activeTimeframe;

        const lastCandle = uniqueData[uniqueData.length - 1];
        lastFinalVolRef.current = (lastCandle.volume || 0) * vScale;
        lastFinalDeltaRef.current = (lastCandle.delta || 0) * dScale;
        prevFirstTimeRef.current = uniqueData[0].time;
        
        // FIX: Reset visual refs for smooth transition when loading new timeframe data
        visualCloseRef.current = lastCandle.close;
        visualTimeRef.current = lastCandle.time;
        
        let lastTime = lastCandle.time;
        if (typeof lastTime === "string") {
          const parsed = new Date(lastTime).getTime();
          if (!isNaN(parsed)) lastTime = Math.floor(parsed / 1000);
        } else if (typeof lastTime === "number" && lastTime > 10000000000) {
          lastTime = Math.floor(lastTime / 1000);
        }
        setLocalLastCandleTime(lastTime);
        if (setLastCandleTime) setLastCandleTime(lastTime);
        lastLerpTimeRef.current = lastTime;
      }
      return;
    }
  }, [historicalData, liveData, activeTimeframe, activeSymbol, showVolume, showDelta, volumeColor, deltaColor, volumeOpacity, deltaOpacity, chartSettings, aggregateData]);

  // FIX: Force chart initialization if historical data fetch fails or hangs
  // This prevents the chart from being stuck on a black screen forever
  useEffect(() => {
    let timeoutId = null;
    if (!isInitializedRef.current && (!historicalData || historicalData.length === 0)) {
      timeoutId = setTimeout(() => {
        if (!isInitializedRef.current) {
          console.warn("[ChartComponent] History fetch timed out or returned empty. Forcing init for live ticks.");
          isInitializedRef.current = true;
          setIsChartReady(true);
          // Setup with empty data so live rendering can begin immediately
          if (candleSeriesRef.current) {
            try { candleSeriesRef.current.setData([]); } catch(e){}
          }
        }
      }, 3000); // 3 seconds is enough for a standard API fetch return
    }
    return () => {
      if (timeoutId) clearTimeout(timeoutId);
    };
  }, [historicalData, activeTimeframe, activeSymbol]);

  useEffect(() => {
    if (!isInitializedRef.current) return;
    
    // ── 2. SUBSEQUENT LIVEDATA OHLC OVERWRITE PROTECTION ──
    if (liveData && Object.keys(liveData).length > 0) {
      const liveCandle = formatCandle(liveData);
      const isValidCandle = (d) => {
        if (!d) return false;
        const t = typeof d.time === 'number' ? d.time :
          (typeof d.time === 'string' ? new Date(d.time.replace(' ', 'T')).getTime() / 1000 : 0);
        if (isNaN(t) || t <= 0) return false;
        if (isNaN(d.open) || isNaN(d.high) || isNaN(d.low) || isNaN(d.close)) return false;
        if (!isFinite(d.open) || !isFinite(d.high) || !isFinite(d.low) || !isFinite(d.close)) return false;
        if (d.open <= 0 || d.high <= 0 || d.low <= 0 || d.close <= 0) return false;
        return true;
      };

      if (isValidCandle(liveCandle)) {
        try {
          const lastIdx = allBarsRef.current.length - 1;
          const existingBar = lastIdx >= 0 ? allBarsRef.current[lastIdx] : null;
          
          let finalCandle = { ...liveCandle };
          
          if (existingBar && existingBar.time === finalCandle.time) {
            finalCandle.open = existingBar.open;
            finalCandle.high = Math.max(existingBar.high, finalCandle.high);
            finalCandle.low = Math.min(existingBar.low, finalCandle.low);
            // FIX: Use LIVE close from tick, NOT the historical close
            // The live tick's close is the real-time price that should be displayed
            finalCandle.close = (finalCandle.close && finalCandle.close > 0) ? finalCandle.close : existingBar.close;
            finalCandle.volume = Math.max(existingBar.volume || 0, finalCandle.volume || 0);
            // FIX: Use the MORE RECENT delta - prefer liveData delta over historical
            // For crypto, liveData delta is the authoritative accumulated delta
            if (liveData.delta !== undefined && liveData.delta !== null && liveData.delta !== 0) {
              finalCandle.delta = liveData.delta;
            } else {
              finalCandle.delta = existingBar.delta;
            }
          }

          if (existingBar && finalCandle.time < existingBar.time) {
            return;
          }
          
          candleSeriesRef.current.update(finalCandle);
          if (areaSeriesRef.current) areaSeriesRef.current.update({ time: finalCandle.time, value: finalCandle.close });
          if (lineSeriesRef.current) lineSeriesRef.current.update({ time: finalCandle.time, value: finalCandle.close });
          if (barSeriesRef.current) barSeriesRef.current.update(finalCandle);
          if (window._refreshChartPrecision) window._refreshChartPrecision(finalCandle.close);

          if (existingBar && existingBar.time === finalCandle.time) {
            allBarsRef.current[lastIdx] = finalCandle;
          } else if (!existingBar || finalCandle.time > existingBar.time) {
            allBarsRef.current.push(finalCandle);
            setLocalLastCandleTime(finalCandle.time);
            if (setLastCandleTime) setLastCandleTime(finalCandle.time);
          }
        } catch (e) { }
      }
    }
  }, [historicalData, liveData, activeSymbol, activeTimeframe, currentPlatform, showVolume, showDelta]);

  // ─── MARKET TICK HANDLER ──────────────────────────────────────────────────────
  useEffect(() => {
    if (!candleSeriesRef.current || !isInitializedRef.current) return;
    const tickBuffer = [];
    let animationId = null;
    
    // FIX: Helper to validate tick timestamp is reasonable
    const isValidTickTimestamp = (ts) => {
      if (ts === undefined || ts === null || isNaN(ts)) return false;
      const nowSec = Math.floor(Date.now() / 1000);
      // Allow up to 60s in the future (clock skew) and up to 1h in the past
      return ts > (nowSec - 3600) && ts < (nowSec + 60);
    };
    
    const isValidCandle = (d) => {
      if (!d) return false;
      if (typeof d.time !== 'number' || isNaN(d.time) || !isFinite(d.time) || d.time <= 0) return false;
      if (isNaN(d.open) || isNaN(d.high) || isNaN(d.low) || isNaN(d.close)) return false;
      if (!isFinite(d.open) || !isFinite(d.high) || !isFinite(d.low) || !isFinite(d.close)) return false;
      if (d.open <= 0 || d.high <= 0 || d.low <= 0 || d.close <= 0) return false;
      return true;
    };

    const flushTicks = () => {
      let isAnimating = false;
      let currentCandle = null;

      if (tickBuffer.length > 0) {
        const currentBatch = tickBuffer.splice(0, tickBuffer.length);
        let lastBar = allBarsRef.current[allBarsRef.current.length - 1];
        currentCandle = lastBar ? { ...lastBar } : null;
        let lastTick = null;
        const tfSeconds = getTimeframeSeconds(activeTimeframe);
        
        // Move scale lookup out of loop
        const { vScale, dScale } = _getPlatformScales(activeSymbol);

        for (const tick of currentBatch) {
          const isCryptoTick = localStorage.getItem('platform') === 'crypto' || activeSymbol.includes('USDT');

          const tickPrice = tick.price || tick.last || tick.bid || tick.ask;
          if (!tickPrice || isNaN(tickPrice)) continue;
        
          // FIX: Use server timestamp ALWAYS, fallback to reasonable local time only if invalid
          let tickTimeSec = Number(tick.timestamp);
          if (tick.timestamp === undefined || tick.timestamp === null || isNaN(tickTimeSec) || tickTimeSec <= 0) {
            // Invalid server timestamp - use local time as fallback
            tickTimeSec = Math.floor(Date.now() / 1000);
          } else {
            // Convert ms to s if needed
            if (tickTimeSec > 10000000000) tickTimeSec = tickTimeSec / 1000;
            tickTimeSec = Math.floor(tickTimeSec);
            
            // Validate timestamp is reasonable (not too far from now)
            const nowSec = Math.floor(Date.now() / 1000);
            if (tickTimeSec < (nowSec - 3600) || tickTimeSec > (nowSec + 60)) {
              // Timestamp is unreasonable - use local time instead
              tickTimeSec = nowSec;
            }
          }
        
        const tickBarTime = Math.floor(tickTimeSec / tfSeconds) * tfSeconds;
        if (currentCandle && tickTimeSec < currentCandle.time) continue;

        const tickVol = Number(tick.size !== undefined ? tick.size : (tick.last_size !== undefined ? tick.last_size : 0));
        const tickSide = (tick.side || 'buy').toLowerCase();

        if (!currentCandle || tickBarTime > currentCandle.time) {
          if (currentCandle) {
            // ── SNAP: directly write final values of closing candle synchronously ──
            const finalScaledVol = isFinite(currentCandle.volume) ? currentCandle.volume * vScale : 0;
            const finalScaledDelta = isFinite(currentCandle.delta) ? currentCandle.delta * dScale : 0;
            lastFinalVolRef.current = finalScaledVol;
            lastFinalDeltaRef.current = finalScaledDelta;
            if (volumeSeriesRef.current && showVolume && isFinite(finalScaledVol) && finalScaledVol >= 0) {
              try {
                const vClr = _ensureHex(currentCandle.close >= currentCandle.open ? volumeColor : "#f87171");
                volumeSeriesRef.current.update({
                  time: currentCandle.time,
                  value: finalScaledVol,
                  color: _getRgba(vClr, volumeOpacity)
                });
              } catch (e) { }
            }
            if (deltaSeriesRef.current && showDelta && isFinite(finalScaledDelta)) {
              try {
                const dClr = _ensureHex((currentCandle.delta || 0) >= 0 ? deltaColor : "#f59e0b");
                deltaSeriesRef.current.update({
                  time: currentCandle.time,
                  value: finalScaledDelta,
                  color: _getRgba(dClr, deltaOpacity)
                });
              } catch (e) { }
            }

            // Explicitly flush the old candle to the UI so it doesn't freeze its previous uncompleted shape!
            if (isValidCandle(currentCandle)) {
              try {
                if (candleSeriesRef.current) candleSeriesRef.current.update(currentCandle);
                if (areaSeriesRef.current) areaSeriesRef.current.update({ time: currentCandle.time, value: currentCandle.close });
                if (lineSeriesRef.current) lineSeriesRef.current.update({ time: currentCandle.time, value: currentCandle.close });
                if (barSeriesRef.current) barSeriesRef.current.update(currentCandle);
              } catch (le) { }
            }
          }
          // Calculate delta: if server sends non-zero delta, use it; otherwise calculate from size/side
          const prevPrice = currentCandle ? currentCandle.close : tickPrice;
          const priceUp = tickPrice >= prevPrice;
          const sideUp = tickSide === 'buy';
          const directionUp = sideUp || priceUp;
          const volForDelta = Number(tickVol) || Number(tick.last_size) || 0;

          // Server delta is valid only if it's non-zero
          const serverDelta = Number(tick.delta);
          const hasValidServerDelta = tick.delta !== undefined && tick.delta !== null && isFinite(serverDelta) && serverDelta !== 0;

          let startingTickSize = Number(tick.size) || Number(tick.last_size) || 0;
          if (startingTickSize === 0 && !isCryptoTick) {
            startingTickSize = Number(tick.volume) || 0;
          }
          const volForNewCandle = isFinite(startingTickSize) ? startingTickSize : 0;

          // FIX: Validate tickPrice is valid before creating candle
          if (!isFinite(tickPrice) || tickPrice <= 0) {
            continue;
          }
          
          // FIX: Prevent huge gaps! Always visually connect new candles to previous close
          // BUT ONLY if the time gap is small (e.g. <= 3 periods). If there's a huge time gap 
          // (like days of no trades on illiquid pairs), connecting them creates a massive artificial candle!
          let validOpen = tickPrice;
          const timeDiff = currentCandle ? (tickBarTime - currentCandle.time) : 0;
          
          // Relaxed connection logic: connect if gap is within 10 periods to reduce visual "jumping"
          if (currentCandle && isFinite(currentCandle.close) && currentCandle.close > 0 && timeDiff <= tfSeconds * 10) {
            validOpen = currentCandle.close; // Use previous close to connect the gap smoothly
          } else if (tick.open && isFinite(tick.open) && tick.open > 0) {
            validOpen = tick.open;
          }
          
          const validHigh = (tick.high && isFinite(tick.high) && tick.high > validOpen) ? tick.high : Math.max(validOpen, tickPrice);
          const validLow = (tick.low && isFinite(tick.low) && tick.low > 0 && tick.low < validOpen) ? tick.low : Math.min(validOpen, tickPrice);
          const validClose = isFinite(tickPrice) && tickPrice > 0 ? tickPrice : validOpen;

          currentCandle = {
            time: tickBarTime,
            open: validOpen,
            high: validHigh,
            low: validLow,
            close: validClose,
            volume: volForNewCandle,
            delta: hasValidServerDelta ? serverDelta : (isFinite(volForDelta) ? volForDelta * (directionUp ? 1 : -1) : 0)
          };
          allBarsRef.current.push(currentCandle);
          setLocalLastCandleTime(tickBarTime);
          if (setLastCandleTime) setLastCandleTime(tickBarTime);
          lastLerpTimeRef.current = tickBarTime;
        } else {
          const prevDelta = currentCandle.delta || 0;
          const prevPrice = currentCandle.close;
          // FIX: Validate tickPrice before updating candle
          if (isFinite(tickPrice) && tickPrice > 0) {
            currentCandle.close = tickPrice;
            currentCandle.high = Math.max(currentCandle.high, tickPrice);
            currentCandle.low = Math.min(currentCandle.low, tickPrice);
          }

          // ── SERVER OHLC: merge authoritative candle shape from backend ──
          // The server tracks the full candle from all trades (not just the
          // subset the frontend sees), so its high/low are more accurate.
          if (tick.high && tick.high > 0) {
            currentCandle.high = Math.max(currentCandle.high, tick.high);
          }
          if (tick.low && tick.low > 0) {
            currentCandle.low = Math.min(currentCandle.low, tick.low);
          }

          // ── VOLUME: Use tick.size for both Crypto and MT5 (App.jsx remaps it) ──
          const isCryptoTick = localStorage.getItem('platform') === 'crypto' || activeSymbol.includes('USDT');
          let tickSize = Number(tick.size) || Number(tick.last_size) || 0;
          if (tickSize === 0 && !isCryptoTick) {
            tickSize = Number(tick.volume) || 0;
          }
          
          if (tickSize > 0) {
            currentCandle.volume = (currentCandle.volume || 0) + tickSize;
          }

          // ── DELTA: Server delta is valid only if non-zero ─────────────────
          const serverDelta = Number(tick.delta);
          const hasValidServerDelta = tick.delta !== undefined && tick.delta !== null && serverDelta !== 0;

          if (hasValidServerDelta) {
            currentCandle.delta = serverDelta;
          } else {
            if (tickSize > 0) {
              const priceUp = tickPrice >= prevPrice;
              const sideUp = tickSide === 'buy';
              const directionUp = sideUp || priceUp;
              currentCandle.delta = prevDelta + (directionUp ? tickSize : -tickSize);
            }
          }
        }
        if (fpRendererRef.current && footprintMode !== 'off') {
          fpRendererRef.current.updateLiveState(currentCandle.time, currentCandle.close, tickVol, tickSide);
          fpRendererRef.current.setLivePrice(currentCandle.close);
        }
        lastTick = tick;
      }
      if (currentCandle) {
        allBarsRef.current[allBarsRef.current.length - 1] = currentCandle;
        const { vScale, dScale } = _getPlatformScales(activeSymbol);
        const rawVol = Number(currentCandle.volume) || 0;
        const rawDelta = Number(currentCandle.delta) || 0;
        const scaledVol = isFinite(rawVol) ? rawVol * vScale : 0;
        const scaledDelta = isFinite(rawDelta) ? rawDelta * dScale : 0;

        // Update volume series directly (no more separate smoothing loop)
        if (volumeSeriesRef.current && showVolume && isFinite(scaledVol) && scaledVol >= 0) {
          const vColor = currentCandle.close >= currentCandle.open ? volumeColor : "#f87171";
          try {
            volumeSeriesRef.current.update({
              time: currentCandle.time,
              value: scaledVol,
              color: _getRgba(_ensureHex(vColor), volumeOpacity)
            });
          } catch (e) { }
        }

        // Update delta series directly — mode aware
        const liveDeltaMode = chartSettings?.filters?.deltaDisplayMode || 'histogram';
        const liveIsHistMode = liveDeltaMode === 'histogram' || liveDeltaMode === 'deltaBars';
        if (deltaSeriesRef.current && showDelta && liveIsHistMode) {
          const posColor = chartSettings?.filters?.deltaPositiveColor || deltaColor;
          const negColor = chartSettings?.filters?.deltaNegativeColor || '#f59e0b';
          const dColor = rawDelta >= 0 ? posColor : negColor;
          try {
            deltaSeriesRef.current.update({
              time: currentCandle.time,
              value: scaledDelta,
              color: _getRgba(_ensureHex(dColor), deltaOpacity)
            });
          } catch (e) { }
        }
        // Cumulative delta live update
        if (showDelta && (liveDeltaMode === 'cumulativeCandles' || liveDeltaMode === 'cumulativeLine')) {
          try {
            const bars = allBarsRef.current;
            // Recompute cumulative for last 2 bars to keep it efficient
            let cumDelta = 0;
            for (let ci = 0; ci < bars.length - 1; ci++) {
              cumDelta += isFinite(bars[ci].delta) ? bars[ci].delta * dScale : 0;
            }
            const prevCum = cumDelta;
            cumDelta += scaledDelta;
            if (liveDeltaMode === 'cumulativeCandles' && deltaCumCandleSeriesRef.current) {
              deltaCumCandleSeriesRef.current.update({
                time: currentCandle.time,
                open: prevCum,
                high: Math.max(prevCum, cumDelta),
                low: Math.min(prevCum, cumDelta),
                close: cumDelta
              });
            }
            if (liveDeltaMode === 'cumulativeLine' && deltaCumLineSeriesRef.current) {
              deltaCumLineSeriesRef.current.update({
                time: currentCandle.time,
                value: cumDelta
              });
            }
          } catch (e) { }
        }

        dataUpdateInMinuteRef.current = true;
        isUpdatingDataRef.current = true;
      }
      isUpdatingDataRef.current = false;
      } // Closes if (tickBuffer.length > 0)
      
      // If we didn't have ticks, we still need to reference the last candle for lerping
      if (!currentCandle && allBarsRef.current.length > 0) {
        currentCandle = allBarsRef.current[allBarsRef.current.length - 1];
      }

      if (currentCandle) {
        // ── 60fps Smooth Lerp ──────────────────────────────────────────
        // FIX: Make lerp faster and more responsive for crypto
        let renderClose = currentCandle.close;
        const isCrypto = localStorage.getItem('platform') === 'crypto' || activeSymbol.includes('USDT');

        // Reset lerp if we moved to a new candle bar
        if (visualTimeRef.current !== currentCandle.time) {
          visualCloseRef.current = currentCandle.close;
          visualTimeRef.current = currentCandle.time;
        }

        if (visualCloseRef.current !== null) {
          const diff = currentCandle.close - visualCloseRef.current;
          // Only lerp if distance is meaningful (avoids floating point infinite loops)
          if (Math.abs(diff) > 0.00000001) {
            // FIX: For crypto, use faster lerp (50%) for real-time responsiveness
            // For other markets, keep smoother lerp (25%)
            const lerpFactor = isCrypto ? 0.5 : 0.25;
            visualCloseRef.current += diff * lerpFactor;
            
            // FIX: Smaller threshold for crypto (0.01 for crypto, 0.001 for others)
            const threshold = isCrypto ? 0.01 : 0.001;
            if (Math.abs(currentCandle.close - visualCloseRef.current) <= threshold) {
              visualCloseRef.current = currentCandle.close;
            } else {
              isAnimating = true;
            }
            renderClose = visualCloseRef.current;
          } else {
            visualCloseRef.current = currentCandle.close;
            renderClose = currentCandle.close;
          }
        } else {
          visualCloseRef.current = currentCandle.close;
        }

        // Apply visual close for rendering only; currentCandle remains authoritative
        const visualCandle = { ...currentCandle, close: renderClose };

        try {
          if (isValidCandle(visualCandle)) {
            try {
              if (candleSeriesRef.current) candleSeriesRef.current.update(visualCandle);
              if (areaSeriesRef.current) areaSeriesRef.current.update({ time: visualCandle.time, value: renderClose });
              if (lineSeriesRef.current) lineSeriesRef.current.update({ time: visualCandle.time, value: renderClose });
              if (barSeriesRef.current) barSeriesRef.current.update(visualCandle);
            } catch (le) { }
          }
          const now = Date.now();
          if (window[`updateVP_${chartId}`] && now - lastVPUpdateTimeRef.current > 200) {
            window[`updateVP_${chartId}`]();
            lastVPUpdateTimeRef.current = now;
          }
        } finally {}
      }
      
      // Keep animation alive if new ticks arrived OR we are still lerping
      if (tickBuffer.length > 0 || isAnimating) {
        animationId = requestAnimationFrame(flushTicks);
      } else {
        animationId = null;
      }
    };
    const handleDirectTick = (e) => {
      const t = e.detail;
      if (!t || !t.symbol) return;

      // Try multiple symbol variations for matching
      const rawSymbol = t.symbol;
      const detSym = window.getUniversalSymbol ? window.getUniversalSymbol(rawSymbol) : rawSymbol;
      const detSymUpper = detSym.toUpperCase();

      const targetRaw = activeSymbol;
      const targetSym = window.getUniversalSymbol ? window.getUniversalSymbol(targetRaw) : targetRaw;
      const targetSymUpper = targetSym.toUpperCase();

      // Match if normalized symbols match OR raw symbols match (case insensitive)
      const symbolMatch = (
        detSym === targetSym ||
        detSymUpper === targetSymUpper ||
        rawSymbol.toUpperCase() === targetRaw.toUpperCase()
      );

      if (!symbolMatch) return;
      tickBuffer.push(t);
      if (!animationId) animationId = requestAnimationFrame(flushTicks);
    };
    window.addEventListener('market_tick', handleDirectTick);
    return () => {
      window.removeEventListener('market_tick', handleDirectTick);
      if (animationId) cancelAnimationFrame(animationId);
    };
  }, [isInitializedRef.current, footprintMode, activeSymbol, activeTimeframe, formatCandle, getTimeframeSeconds]);

  useEffect(() => {
    if (!isChartReady || !candleSeriesRef.current || !areaSeriesRef.current || !lineSeriesRef.current || !barSeriesRef.current) return;
    const isCandle = chartType === "candle";
    const isArea = chartType === "area";
    const isLine = chartType === "line";
    const isBar = chartType === "bar";
    candleSeriesRef.current.applyOptions({ visible: isCandle });
    areaSeriesRef.current.applyOptions({ visible: isArea });
    lineSeriesRef.current.applyOptions({ visible: isLine });
    barSeriesRef.current.applyOptions({ visible: isBar });
    const dataToLoad = historicalData && historicalData.length > 0 ? historicalData : liveData;
    if (dataToLoad && dataToLoad.length > 0) {
      const isValidCandle = (d) => {
        if (!d) return false;
        if (typeof d.time !== 'number' || isNaN(d.time) || !isFinite(d.time) || d.time <= 0) return false;
        if (isNaN(d.open) || isNaN(d.high) || isNaN(d.low) || isNaN(d.close)) return false;
        if (!isFinite(d.open) || !isFinite(d.high) || !isFinite(d.low) || !isFinite(d.close)) return false;
        if (d.open <= 0 || d.high <= 0 || d.low <= 0 || d.close <= 0) return false;
        return true;
      };
      const formatted = dataToLoad.map(formatCandle).filter(isValidCandle).sort((a, b) => a.time - b.time);
      if (formatted.length > 0) {
        try {
          if (isCandle) candleSeriesRef.current.setData(formatted);
          else if (isArea) areaSeriesRef.current.setData(formatted.map((d) => ({ time: d.time, value: d.close })));
          else if (isLine) lineSeriesRef.current.setData(formatted.map((d) => ({ time: d.time, value: d.close })));
          else if (isBar) barSeriesRef.current.setData(formatted);
        } catch (e) { console.warn("Chart data apply ignored during vis toggle"); }
      }
    }
  }, [chartType, isChartReady]);

  useEffect(() => {
    if (!isChartReady || !candleSeriesRef.current || !areaSeriesRef.current || !lineSeriesRef.current || !barSeriesRef.current) return;
    let precision = { digits: 5, tick_size: 0.00001 };
    if (window.getSymbolPrecision) precision = window.getSymbolPrecision(activeSymbol, detectPlatformType());

    const hideLabel = footprintMode !== 'off' || chartType === 'tpo';
    const precisionOptions = {
      priceFormat: { type: "price", precision: precision.digits, minMove: precision.tick_size },
      lastValueLabelVisible: !hideLabel,
      lastValueVisible: !hideLabel, // Agregado para compatibilidad total
      priceLineVisible: false
    };

    candleSeriesRef.current.applyOptions(precisionOptions);
    areaSeriesRef.current.applyOptions(precisionOptions);
    lineSeriesRef.current.applyOptions(precisionOptions);
    barSeriesRef.current.applyOptions(precisionOptions);

    const labelOpts = { lastValueLabelVisible: !hideLabel, lastValueVisible: !hideLabel };
    if (volumeSeriesRef.current) volumeSeriesRef.current.applyOptions(labelOpts);
    if (deltaSeriesRef.current) deltaSeriesRef.current.applyOptions(labelOpts);
    if (deltaCumCandleSeriesRef.current) deltaCumCandleSeriesRef.current.applyOptions(labelOpts);
    if (deltaCumLineSeriesRef.current) deltaCumLineSeriesRef.current.applyOptions(labelOpts);

    if (chartRef.current) {
      chartRef.current.applyOptions({ localization: { priceFormatter: (price) => price.toFixed(precision.digits) } });
    }
  }, [activeSymbol, isChartReady, footprintMode, chartType]);

  useEffect(() => {
    if (!chartRef.current) return;
    const isBookmapActive = showAllOverlays && chartSettings?.overlays?.showBookmap;
    if (isBookmapActive) {
      chartRef.current.timeScale().applyOptions({ rightOffset: 0 });
      // Removed smoothPan loop that was locking the chart to the right edge
    } else {
      chartRef.current.timeScale().applyOptions({ rightOffset: 12 });
    }
  }, [showAllOverlays, chartSettings?.overlays?.showBookmap, isChartReady]);

  useEffect(() => {
    if (!chartRef.current) return;
    const chart = chartRef.current;
    chart.applyOptions({
      handleScroll: { mouseWheel: true, pressedMouseMove: true, horzTouchDrag: true, vertTouchDrag: true },
      handleScale: { axisPressedMouseMove: true, mouseWheel: true, pinch: true, axisDoubleClickReset: true, wheelSpeed: 1 }
    });
    let scrollTimeout;
    const handleScrollStart = () => {
      if (scrollTimeout) clearTimeout(scrollTimeout);
      scrollTimeout = setTimeout(() => {
        chart.applyOptions({
          layout: {
            background: {
              type: 'solid',
              color: (showAllOverlays && chartSettings?.overlays?.showBookmap) ? "transparent" : (settingsRef.current?.appearance?.backgroundColor || localStorage.getItem("global_chart_bg_color") || "#000000")
            },
            textColor: "#94a3b8", fontSize: 11, fontFamily: "Inter, sans-serif"
          }
        });
      }, 150);
    };
    chart.timeScale().subscribeVisibleTimeRangeChange(handleScrollStart);
    return () => {
      chart.timeScale().unsubscribeVisibleTimeRangeChange(handleScrollStart);
      if (scrollTimeout) clearTimeout(scrollTimeout);
    };
  }, []);

  useEffect(() => {
    if (!chartRef.current || !chartSettings?.layout) return;
    const { showGrid, showWatermark: showWatermarkSetting } = chartSettings.layout;
    setShowWatermark(showWatermarkSetting ?? true);
    const isBookmapActive = showAllOverlays && chartSettings?.overlays?.showBookmap;
    const isGridVisible = isBookmapActive ? false : (showGrid ?? true);
    chartRef.current.applyOptions({
      grid: { vertLines: { visible: isGridVisible }, horzLines: { visible: isGridVisible } },
      watermark: { visible: false }
    });
  }, [chartSettings?.layout, activeSymbol, isChartReady]);

  useEffect(() => {
    if (!chartRef.current) return;
    const chart = chartRef.current;
    let barSpacing = 6, minBarSpacing = 0.5, rightOffset = 12;
    switch (activeTimeframe) {
      case "1m": barSpacing = 4; minBarSpacing = 0.3; rightOffset = 20; break;
      case "5m": barSpacing = 5; minBarSpacing = 0.4; rightOffset = 15; break;
      case "1h": case "4h": barSpacing = 8; minBarSpacing = 0.8; rightOffset = 10; break;
      case "D": barSpacing = 12; minBarSpacing = 1.0; rightOffset = 8; break;
      default: break;
    }
    chart.applyOptions({ timeScale: { barSpacing, minBarSpacing, rightOffset, shiftVisibleRangeOnNewBar: false, fixRightEdge: false } });
  }, [activeTimeframe, isChartReady, showVolume, showDelta]);

  useEffect(() => { return () => { }; }, [activeSymbol, activeTimeframe]);

  const positionLinesRef = useRef([]);
  const prevThresholdsRef = useRef(null);
  useEffect(() => {
    const realT = chartSettings?.indicators?.bigTrades?.real?.threshold;
    const cumT = chartSettings?.indicators?.bigTrades?.cumulative?.threshold;
    const enabled = chartSettings?.indicators?.bigTrades?.enabled;
    const hLen = historicalData?.length || 0;
    const hFirst = hLen > 0 ? (historicalData[0].time || historicalData[0].t) : 0;
    const key = `${realT}_${cumT}_${enabled}_${activeTimeframe}_${hLen}_${hFirst}`;
    if (prevThresholdsRef.current !== null && prevThresholdsRef.current !== key) {
      hasProcessedHistoricalRef.current = {};
      setBigTrades([]);
      if (globalBigTradesRef?.current) globalBigTradesRef.current[activeSymbol] = [];
    }
    prevThresholdsRef.current = key;
  }, [
    chartSettings?.indicators?.bigTrades?.real?.threshold,
    chartSettings?.indicators?.bigTrades?.cumulative?.threshold,
    chartSettings?.indicators?.bigTrades?.enabled,
    activeSymbol, activeTimeframe, historicalData
  ]);

  useEffect(() => {
    if (!isChartReady || !candleSeriesRef.current || !historicalData) return;
    const defaults = getDefaultChartSettings().indicators.bigTrades;
    const currentBT = chartSettings?.indicators?.bigTrades || {};
    const config = {
      ...defaults, ...currentBT,
      real: { ...defaults.real, ...(currentBT.real || {}) },
      cumulative: { ...defaults.cumulative, ...(currentBT.cumulative || {}) }
    };
    const realThreshold = config.real?.threshold || 100;
    const cumThreshold = config.cumulative?.threshold || 500;
    const sessionKey = `${activeSymbol}_${activeTimeframe}_R${realThreshold}_C${cumThreshold}`;
    if (hasProcessedHistoricalRef.current[sessionKey]) return;
    const validData = historicalData.map((d) => ({ ...d, Volume: parseFloat(d.Volume) })).filter((d) => !isNaN(d.Volume));
    if (validData.length === 0) return;
    const newMarkers = [];
    {
      const threshold = realThreshold;
      const limit = config.real?.displayLimit || config.displayLimit || 100;
      const realMarkers = [];
      validData.forEach((d) => {
        if (d.Volume >= threshold) {
          const isUp = parseFloat(d.Close) >= parseFloat(d.Open);
          const time = typeof d.time === "string" ? new Date(d.time.replace(" ", "T")).getTime() / 1000 : d.time;
          realMarkers.push({ id: time + "_" + d.Volume + "_real", time, price: parseFloat(d.Close), size: Math.floor(d.Volume), side: isUp ? "buy" : "sell", bt_type: "real" });
        }
      });
      realMarkers.sort((a, b) => a.time - b.time);
      newMarkers.push(...realMarkers.slice(-limit));
    }
    {
      const threshold = cumThreshold;
      const limit = config.cumulative?.displayLimit || config.displayLimit || 100;
      const cumMarkers = [];
      validData.forEach((d) => {
        if (d.Volume >= threshold) {
          const isUp = parseFloat(d.Close) >= parseFloat(d.Open);
          const time = typeof d.time === "string" ? new Date(d.time.replace(" ", "T")).getTime() / 1000 : d.time;
          cumMarkers.push({ id: time + "_" + d.Volume + "_cum", time, price: parseFloat(d.Close), size: Math.floor(d.Volume), side: isUp ? "buy" : "sell", bt_type: "cumulative" });
        }
      });
      cumMarkers.sort((a, b) => a.time - b.time);
      newMarkers.push(...cumMarkers.slice(-limit));
    }
    newMarkers.sort((a, b) => a.time - b.time);
    hasProcessedHistoricalRef.current[sessionKey] = true;
    if (newMarkers.length > 0) {
      setBigTrades((prev) => {
        const existingIds = new Set(prev.map((t) => t.id));
        const uniqueNew = newMarkers.filter((t) => !existingIds.has(t.id));
        if (uniqueNew.length === 0) return prev;
        const combined = [...prev, ...uniqueNew].sort((a, b) => a.time - b.time);
        if (globalBigTradesRef?.current) globalBigTradesRef.current[activeSymbol] = combined;
        return combined;
      });
    }
  }, [
    historicalData,
    chartSettings?.indicators?.bigTrades?.enabled,
    chartSettings?.indicators?.bigTrades?.real?.enabled,
    chartSettings?.indicators?.bigTrades?.cumulative?.enabled,
    chartSettings?.indicators?.bigTrades?.real?.threshold,
    chartSettings?.indicators?.bigTrades?.cumulative?.threshold,
    chartSettings?.indicators?.bigTrades?.displayLimit,
    isChartReady
  ]);

  useEffect(() => {
    const defaults = getDefaultChartSettings().indicators.bigTrades;
    const currentBT = chartSettings?.indicators?.bigTrades || {};
    const config = {
      ...defaults, ...currentBT,
      real: { ...defaults.real, ...(currentBT.real || {}) },
      cumulative: { ...defaults.cumulative, ...(currentBT.cumulative || {}) }
    };
    let newDetectedTrades = [];
    if (liveRealTrades.length > 0) {
      const baseThreshold = config.real?.threshold || 100;
      const threshold = isBigLlamaActive && llamaParams.big?.minVol ? llamaParams.big.minVol : baseThreshold;
      const tfSeconds = getTimeframeSeconds(activeTimeframe);
      const detected = liveRealTrades
        .filter((t) => t.size >= threshold)
        .map((t) => ({ ...t, time: Math.floor(t.timestamp / tfSeconds) * tfSeconds, id: t.id + "_real", bt_type: "real" }));
      newDetectedTrades = [...newDetectedTrades, ...detected];
    }
    if (liveAggregatedTrades.length > 0) {
      const baseThreshold = config.cumulative?.threshold || 500;
      const threshold = isBigLlamaActive && llamaParams.big?.minVol ? llamaParams.big.minVol : baseThreshold;
      const tfSeconds = getTimeframeSeconds(activeTimeframe);
      const detected = liveAggregatedTrades
        .filter((t) => t.size >= threshold)
        .map((t) => ({ ...t, time: Math.floor(t.timestamp / tfSeconds) * tfSeconds, id: t.id + "_cum", bt_type: "cumulative" }));
      newDetectedTrades = [...newDetectedTrades, ...detected];
    }
    if (newDetectedTrades.length === 0) return;
    setBigTrades((prev) => {
      const existingIds = new Set(prev.map((t) => t.id));
      const uniqueNew = newDetectedTrades.filter((t) => !existingIds.has(t.id));
      if (uniqueNew.length === 0) return prev;
      const updated = [...prev, ...uniqueNew];
      const realLimit = config.real?.displayLimit || 100;
      const cumLimit = config.cumulative?.displayLimit || 100;
      const realTrades = updated.filter((t) => t.bt_type === 'real').sort((a, b) => a.time - b.time).slice(-realLimit);
      const cumTrades = updated.filter((t) => t.bt_type !== 'real').sort((a, b) => a.time - b.time).slice(-cumLimit);
      const finalTrades = [...realTrades, ...cumTrades].sort((a, b) => a.time - b.time);
      if (globalBigTradesRef?.current) globalBigTradesRef.current[activeSymbol] = finalTrades;
      return finalTrades;
    });
  }, [liveRealTrades, liveAggregatedTrades, chartSettings?.indicators?.bigTrades, activeSymbol, activeTimeframe, getTimeframeSeconds]);

  useEffect(() => {
    const handleBackendBigTrade = (e) => {
      const bt = e.detail;
      if (!bt || !activeSymbol) return;
      
      // Comparación robusta de símbolos (ignora mayúsculas/minúsculas y normaliza)
      const normActive = activeSymbol.split(':')[0].toUpperCase();
      const normIncoming = bt.symbol.split(':')[0].toUpperCase();
      if (normActive !== normIncoming) return;

      setBigTrades((prev) => {
        const id = bt.id || bt.timestamp + Math.random();
        if (prev.some((t) => t.id === id)) return prev;
        const tfSeconds = getTimeframeSeconds(activeTimeframe);
        const normTs = bt.timestamp > 1e11 ? bt.timestamp / 1000 : bt.timestamp;
        const newTrade = { ...bt, id, time: Math.floor(normTs / tfSeconds) * tfSeconds, bt_type: bt.bt_type || 'real' };
        const updated = [...prev, newTrade].sort((a, b) => a.time - b.time);
        
        // Read safely from ref to avoid dependency array thrashing
        const currentBTSettings = settingsRef.current?.indicators?.bigTrades;
        const limit = currentBTSettings?.[newTrade.bt_type]?.displayLimit || 100;
        
        const filtered = updated.filter((t) => t.bt_type === newTrade.bt_type).slice(-limit);
        const other = updated.filter((t) => t.bt_type !== newTrade.bt_type);
        const final = [...filtered, ...other].sort((a, b) => a.time - b.time);
        if (globalBigTradesRef?.current) globalBigTradesRef.current[activeSymbol] = final;
        return final;
      });
    };
    window.addEventListener('market_big_trade', handleBackendBigTrade);
    return () => window.removeEventListener('market_big_trade', handleBackendBigTrade);
  }, [activeSymbol, activeTimeframe, getTimeframeSeconds]);

  const handleChartContextMenu = (e) => {
    e.preventDefault();
    if (!candleSeriesRef.current || !chartContainerRef.current) return;
    const rect = chartContainerRef.current.getBoundingClientRect();
    const y = e.clientY - rect.top;
    const price = candleSeriesRef.current.coordinateToPrice(y);
    if (price) setChartMenu({ x: e.clientX, y: e.clientY, price });
  };

  useEffect(() => {
    if (volumeSeriesRef.current) {
      volumeSeriesRef.current.applyOptions({ visible: showVolume });
      if (showVolume && historicalData && historicalData.length > 0) {
        const uniqueData = [];
        const times = new Set();
        const formatted = historicalData.map(formatCandle).filter((d) => !isNaN(d.open) && d.time).sort((a, b) => a.time - b.time);
        for (let i = 0; i < formatted.length; i++) {
          if (!times.has(formatted[i].time)) { times.add(formatted[i].time); uniqueData.push(formatted[i]); }
        }
        const { vScale } = _getPlatformScales(activeSymbol);
        const volumeData = uniqueData.map((d) => ({
          time: d.time,
          value: isFinite(d.volume * vScale) ? d.volume * vScale : 0,
          color: _getRgba(_ensureHex(d.close >= d.open ? volumeColor : "#ef4444"), volumeOpacity)
        }));
        volumeSeriesRef.current.setData(volumeData);
      }
    }
    // Delta mode-aware visibility & data reload
    const deltaMode = chartSettings?.filters?.deltaDisplayMode || 'histogram';
    const isHistMode = deltaMode === 'histogram' || deltaMode === 'deltaBars';
    const isCumCandleMode = deltaMode === 'cumulativeCandles';
    const isCumLineMode = deltaMode === 'cumulativeLine';

    if (showDelta && historicalData && historicalData.length > 0) {
      const uniqueData = [];
      const times = new Set();
      const formatted = historicalData.map(formatCandle).filter((d) => !isNaN(d.open) && d.time).sort((a, b) => a.time - b.time);
      for (let i = 0; i < formatted.length; i++) {
        if (!times.has(formatted[i].time)) { times.add(formatted[i].time); uniqueData.push(formatted[i]); }
      }
      const { dScale } = _getPlatformScales(activeSymbol);

      if (isHistMode && deltaSeriesRef.current) {
        const posColor = chartSettings?.filters?.deltaPositiveColor || deltaColor;
        const negColor = chartSettings?.filters?.deltaNegativeColor || '#f59e0b';
        const deltaData = uniqueData.map((d) => ({
          time: d.time,
          value: isFinite(d.delta * dScale) ? d.delta * dScale : 0,
          color: _getRgba(_ensureHex(d.delta >= 0 ? posColor : negColor), deltaOpacity)
        }));
        deltaSeriesRef.current.setData(deltaData);
      }

      if (isCumCandleMode || isCumLineMode) {
        const { candles: cumCandles, lineData: cumLine } = _computeCumulativeDelta(uniqueData, dScale);
        if (isCumCandleMode && deltaCumCandleSeriesRef.current) {
          deltaCumCandleSeriesRef.current.setData(cumCandles);
          deltaCumCandleSeriesRef.current.applyOptions({
            upColor: chartSettings?.filters?.deltaCumPositiveColor || '#26a69a',
            downColor: chartSettings?.filters?.deltaCumNegativeColor || '#ef5350',
            borderUpColor: chartSettings?.filters?.deltaCumPositiveColor || '#26a69a',
            borderDownColor: chartSettings?.filters?.deltaCumNegativeColor || '#ef5350',
            wickUpColor: chartSettings?.filters?.deltaCumPositiveColor || '#26a69a',
            wickDownColor: chartSettings?.filters?.deltaCumNegativeColor || '#ef5350'
          });
        }
        if (isCumLineMode && deltaCumLineSeriesRef.current) {
          deltaCumLineSeriesRef.current.setData(cumLine);
          deltaCumLineSeriesRef.current.applyOptions({
            color: chartSettings?.filters?.deltaCumLineColor || '#3b82f6',
            lineWidth: chartSettings?.filters?.deltaCumLineWidth || 2
          });
        }
      }
    }

    _applyDeltaSeriesVisibility(deltaMode, showDelta, deltaSeriesRef, deltaCumCandleSeriesRef, deltaCumLineSeriesRef);
  }, [showVolume, showDelta, historicalData, volumeColor, deltaColor, chartSettings?.filters?.deltaDisplayMode, chartSettings?.filters?.deltaPositiveColor, chartSettings?.filters?.deltaNegativeColor, chartSettings?.filters?.deltaCumPositiveColor, chartSettings?.filters?.deltaCumNegativeColor, chartSettings?.filters?.deltaCumLineColor, chartSettings?.filters?.deltaCumLineWidth]);

  useEffect(() => {
    if (volumeSeriesRef.current) volumeSeriesRef.current.applyOptions({ visible: showVolume });
    const deltaMode = chartSettings?.filters?.deltaDisplayMode || 'histogram';
    _applyDeltaSeriesVisibility(deltaMode, showDelta, deltaSeriesRef, deltaCumCandleSeriesRef, deltaCumLineSeriesRef);
  }, [volumeSeriesRef.current, deltaSeriesRef.current, deltaCumCandleSeriesRef.current, deltaCumLineSeriesRef.current, showVolume, showDelta, footprintMode, chartSettings?.filters?.deltaDisplayMode]);

  useEffect(() => {
    if (isChartReady && chartRef.current) {
      if (candleSeriesRef.current) candleSeriesRef.current.applyOptions({ visible: chartType === "candle" });
      if (areaSeriesRef.current) areaSeriesRef.current.applyOptions({ visible: chartType === "area" });
      if (lineSeriesRef.current) lineSeriesRef.current.applyOptions({ visible: chartType === "line" });
      if (barSeriesRef.current) barSeriesRef.current.applyOptions({ visible: chartType === "bar" });
    }
  }, [chartType, isChartReady]);

  useEffect(() => {
    const close = () => setChartMenu(null);
    window.addEventListener("click", close);
    return () => window.removeEventListener("click", close);
  }, []);

  useEffect(() => {
    const hideCandles = footprintMode !== 'off' || chartType === 'tpo';
    if (!chartRef.current || !candleSeriesRef.current || !chartContainerRef.current) {
      if (fpRendererRef.current) fpRendererRef.current.setEnabled(false);
      return;
    }

    if (!hideCandles) {
      if (fpRendererRef.current) fpRendererRef.current.setEnabled(false);
      candleSeriesRef.current.applyOptions({
        visible: chartType === "candle",
        upColor: chartSettings?.appearance?.upColor || globalAppearance.upColor || "#00d084",
        downColor: chartSettings?.appearance?.downColor || globalAppearance.downColor || "#ff4757",
        borderVisible: globalAppearance.borderVisible,
        wickVisible: true
      });
      if (areaSeriesRef.current) {
        areaSeriesRef.current.applyOptions({
          visible: chartType === "area",
          lineColor: "#ffffff", lineWidth: 2,
          topColor: "rgba(0, 0, 0, 0)", bottomColor: "rgba(0, 0, 0, 0)"
        });
      }
      return;
    }

    // Si hay footprint
    const isFootprint = footprintMode !== 'off';
    if (!fpRendererRef.current && window.FootprintRenderer) {
      fpRendererRef.current = window.FootprintRenderer.create();
      fpRendererRef.current.init(footprintContainerRef.current, chartRef.current, candleSeriesRef.current);
      const savedFontSize = parseInt(localStorage.getItem('footprint_font_size')) || 11;
      const savedShowWicks = localStorage.getItem('footprint_show_wicks') !== 'false';
      const savedShowPOC = localStorage.getItem('footprint_show_poc') !== 'false';
      const savedThickness = parseInt(localStorage.getItem('footprint_wick_thickness')) || 1;
      const savedBuyColor = localStorage.getItem('footprint_buy_color') || '#00ff80';
      const savedSellColor = localStorage.getItem('footprint_sell_color') || '#ff0050';
      const savedPocColor = localStorage.getItem('footprint_poc_color') || '#ffd700';
      fpRendererRef.current.setFontSize(savedFontSize);
      fpRendererRef.current.setShowWicks(savedShowWicks);
      fpRendererRef.current.setShowPOC(savedShowPOC);
      fpRendererRef.current.setWickThickness(savedThickness);
      const buildBodyColor = (hex, opacityPct) => {
        const m = /^#?([a-f\d]{2})([a-f\d]{2})([a-f\d]{2})$/i.exec(hex);
        if (!m) return hex;
        const a = ((opacityPct ?? 55) / 100).toFixed(2);
        return `rgba(${parseInt(m[1], 16)},${parseInt(m[2], 16)},${parseInt(m[3], 16)},${a})`;
      };
      
      const fp = chartSettings?.footprint || {};
      const isSync = fp.syncWithChartColors ?? true;

      fpRendererRef.current.setColors({ 
        buy: fp.buyColor || savedBuyColor, 
        sell: fp.sellColor || savedSellColor, 
        poc: fp.pocColor || savedPocColor,
        bodyBull: buildBodyColor(
          isSync ? globalAppearance.upColor : (fp.bodyBullColor || '#00dc6e'),
          fp.bodyBullOpacity ?? 55
        ),
        bodyBear: buildBodyColor(
          isSync ? globalAppearance.downColor : (fp.bodyBearColor || '#e6284b'),
          fp.bodyBearOpacity ?? 55
        )
      });
      if (chartSettings?.appearance?.priceLine) {
        fpRendererRef.current.setPriceLineConfig(chartSettings.appearance.priceLine);
      }
    }
    if (fpRendererRef.current) {
      fpRendererRef.current.setMode(footprintMode);
      fpRendererRef.current.setEnabled(true);
      if (chartSettings?.appearance?.priceLine) {
        fpRendererRef.current.setPriceLineConfig(chartSettings.appearance.priceLine);
      }

      if (candleSeriesRef.current) {
        candleSeriesRef.current.applyOptions({
          visible: true,
          upColor: 'rgba(0,0,0,0)',
          downColor: 'rgba(0,0,0,0)',
          borderVisible: false,
          wickVisible: false,
          priceLineVisible: false,
          lastValueLabelVisible: false
        });
      }
      if (areaSeriesRef.current) areaSeriesRef.current.applyOptions({ visible: false });
      if (lineSeriesRef.current) lineSeriesRef.current.applyOptions({ visible: false });
      if (barSeriesRef.current) barSeriesRef.current.applyOptions({ visible: false });
    } else if (hideCandles) {
      // Caso para TPO u otros modos que ocultan velas
      if (candleSeriesRef.current) {
        candleSeriesRef.current.applyOptions({
          visible: true,
          upColor: 'rgba(0,0,0,0)',
          downColor: 'rgba(0,0,0,0)',
          borderVisible: false,
          wickVisible: false,
          priceLineVisible: false,
          lastValueLabelVisible: false
        });
      }
      if (areaSeriesRef.current) areaSeriesRef.current.applyOptions({ visible: false });
      if (lineSeriesRef.current) lineSeriesRef.current.applyOptions({ visible: false });
      if (barSeriesRef.current) barSeriesRef.current.applyOptions({ visible: false });
    }
    return () => {
      if (fpRendererRef.current && footprintMode === 'off') {
        fpRendererRef.current.destroy();
        fpRendererRef.current = null;
      }
    };
  }, [footprintMode, isChartReady, chartType]);

  useEffect(() => {
    setFootprintData(null);
    if (footprintMode === 'off' || !activeSymbol || !activeTimeframe) return;
    let cancelled = false;
    const mergeFootprintData = (prevData, newData) => {
      if (!prevData?.candles?.length) return newData;
      if (!newData?.candles?.length) return prevData;
      const map = new Map();
      const merged = [...prevData.candles];
      merged.forEach((c, i) => map.set(c.time, i));
      let changed = false;
      for (const nc of newData.candles) {
        const idx = map.get(nc.time);
        if (idx !== undefined) {
          const old = merged[idx];
          const getBetter = old.fidelity !== 'high' || nc.fidelity === 'high';
          if (getBetter) { merged[idx] = nc; changed = true; }
        } else {
          map.set(nc.time, merged.length);
          merged.push(nc);
          changed = true;
        }
      }
      if (!changed) return prevData;
      merged.sort((a, b) => a.time - b.time);
      return { ...newData, candles: merged };
    };
    const fetchFootprint = async (isInitial = false) => {
      if (footprintFetchingRef.current) return;
      const performFetch = async (targetLimit) => {
        footprintFetchingRef.current = true;
        try {
          const platformType = typeof detectPlatformType === "function" ? detectPlatformType() : window.detectPlatformType ? window.detectPlatformType() : "futures";
          const mappedSymbol = typeof getUniversalSymbol === "function" ? getUniversalSymbol(activeSymbol, platformType) : window.getUniversalSymbol ? window.getUniversalSymbol(activeSymbol, platformType) : activeSymbol;
          let url = `/api/footprint?symbol=${encodeURIComponent(mappedSymbol)}&timeframe=${encodeURIComponent(activeTimeframe)}&limit=${targetLimit}&platform=${encodeURIComponent(platformType)}`;
          let res = await fetch(url);
          if (res.status === 422 && targetLimit > 2000) {
            url = `/api/footprint?symbol=${encodeURIComponent(mappedSymbol)}&timeframe=${encodeURIComponent(activeTimeframe)}&limit=2000&platform=${encodeURIComponent(platformType)}`;
            res = await fetch(url);
          }
          if (!res.ok) return;
          const data = await res.json();
          if (!cancelled && data?.candles) {
            if (isInitial) setFootprintData(data);
            else setFootprintData((prev) => mergeFootprintData(prev, data));
          }
        } catch (e) {
          console.error('[FOOTPRINT] Fetch error:', e);
        } finally {
          footprintFetchingRef.current = false;
        }
      };
      if (isInitial) {
        await performFetch(200);
        if (!cancelled) setTimeout(() => performFetch(1000), 500);
      } else {
        await performFetch(100);
      }
    };
    fetchFootprint(true);
    const interval = setInterval(() => fetchFootprint(false), 10000);
    return () => { cancelled = true; clearInterval(interval); };
  }, [footprintMode, activeSymbol, activeTimeframe]);

  const effectiveFootprintData = useMemo(() => {
    if (footprintMode === 'off') return null;

    const baseCandles = allBarsRef.current?.length
      ? allBarsRef.current
      : historicalData?.length
        ? aggregateData(historicalData)
        : [];

    if (baseCandles.length > 0) {
      const footprintByTime = new Map();
      for (const candle of footprintData?.candles || []) {
        footprintByTime.set(Number(candle.time), candle);
      }

      return {
        ...(footprintData || {}),
        symbol: activeSymbol,
        timeframe: activeTimeframe,
        candles: baseCandles.map((base) => {
          const fp = footprintByTime.get(Number(base.time));
          return {
            ...base,
            volume: fp?.volume ?? base.volume ?? base.tick_volume ?? 0,
            levels: fp?.levels || [],
            poc: fp?.poc,
            delta: fp?.delta ?? base.delta ?? 0,
            fidelity: fp?.fidelity || 'chart'
          };
        })
      };
    }

    if (footprintData?.candles?.length) return footprintData;
    return null;
  }, [footprintData, footprintMode, historicalData, activeSymbol, activeTimeframe, aggregateData, localLastCandleTime]);

  useEffect(() => {
    if (fpRendererRef.current) fpRendererRef.current.setData(effectiveFootprintData);
  }, [effectiveFootprintData]);

  useEffect(() => {
    const vpConfig = normalizedVpConfig;
    if (!isChartReady || !chartRef.current || !vpConfig?.enabled) {
      if (vpRendererRef.current) { vpRendererRef.current.destroy(); vpRendererRef.current = null; }
      vpEngineRef.current = null;
      return;
    }
    if (!vpEngineRef.current) vpEngineRef.current = new window.VolumeProfileEngine();
    if (!vpRendererRef.current) vpRendererRef.current = new window.VolumeProfileRenderer(chartRef.current, chartContainerRef.current);
    const updateVP = () => {
      if (!vpEngineRef.current || !vpRendererRef.current || !chartRef.current || !candleSeriesRef.current || !isChartReady) return;
      try {
        const vpConfig = normalizedVpConfig;
        if (vpConfig && vpConfig.enabled) {
          const params = vpConfig.params;
          let profiles = [];
          if (params.rangeMode === "visible") {
            const range = chartRef.current.timeScale().getVisibleRange();
            if (range) {
              const visibleBars = allBarsRef.current.filter((b) => b.time >= range.from && b.time <= range.to);
              profiles = [vpEngineRef.current._computeProfile(visibleBars, "visible", "visible", params)];
            }
          } else {
            profiles = vpEngineRef.current.getActiveProfiles(allBarsRef.current, params.rangeMode, params);
            const range = chartRef.current.timeScale().getVisibleRange();
            if (range) profiles = profiles.filter((p) => p.timeEnd >= range.from && p.timeStart <= range.to);
          }
          vpRendererRef.current.render(profiles, params, candleSeriesRef.current);
        }
      } catch (e) { }
    };
    updateVP();
    const timeScale = chartRef.current.timeScale();
    let rafId;

    const handleVisibleRangeChange = () => {
      if (rafId) cancelAnimationFrame(rafId);
      rafId = requestAnimationFrame(() => {
        updateVP();
        if (fpRendererRef.current && footprintMode !== 'off') {
            fpRendererRef.current._draw();
        }
        // Save logical range for persistence
        if (chartRef.current) {
          const range = chartRef.current.timeScale().getVisibleLogicalRange();
          if (range) saveLogicalRange(range, allBarsRef.current.length);
        }
      });
    };

    timeScale.subscribeVisibleLogicalRangeChange(handleVisibleRangeChange);
    
    // Initial draw
    handleVisibleRangeChange();

    window[`updateVP_${chartId}`] = updateVP;
    
    return () => {
      timeScale.unsubscribeVisibleLogicalRangeChange(handleVisibleRangeChange);
      if (rafId) cancelAnimationFrame(rafId);
      delete window[`updateVP_${chartId}`];
    };
  }, [chartId, normalizedVpConfig, isChartReady, activeSymbol, localLastCandleTime, footprintMode]);

  const executeMenuOrder = (type, orderPrice) => {
    const isOneClick = localStorage.getItem("oneClickTrading") === "true";
    const parts = type.split(" ");
    const action = parts[0];
    const orderType = parts[1] || "MKT";
    const currentSL = parseFloat(localStorage.getItem("orderEntry_sl") || "20");
    const currentTP = parseFloat(localStorage.getItem("orderEntry_tp") || "40");
    const smartSL = !isNaN(currentSL) && currentSL > 0 ? currentSL : null;
    const smartTP = !isNaN(currentTP) && currentTP > 0 ? currentTP : null;
    onOrder(action, volume || 1, smartSL, smartTP, orderType, orderPrice);
    setChartMenu(null);
  };

  return (
    React.createElement("div", {
      className: "w-full h-full relative group flex flex-col",
      onContextMenu: handleChartContextMenu,
      onMouseMove: (e) => { },
      onMouseLeave: () => {
        mousePosRef.current = { time: null, price: null, point: null };
        if (chartRef.current) chartRef.current.setCrosshairPosition(null, null, undefined);
        setHoverData({ volume: null, delta: null });
        lastActivePaneRef.current = null;
      }
    },
      React.createElement("style", null, `
        div[class*="tv-logo"],
        div[class*="tradingview-logo"],
        a[href*="tradingview.com"] {
          display: none !important;
          visibility: hidden !important;
          opacity: 0 !important;
          pointer-events: none !important;
        }
      `),
      React.createElement("div", {
        className: "relative flex-grow min-h-0",
        style: { height: '100%', backgroundColor: bgColor }
      },
        React.createElement("div", {
          className: "absolute inset-0 z-0",
          style: { backgroundColor: chartSettings?.appearance?.backgroundColor || localStorage.getItem("global_chart_bg_color") || "#000000" }
        }),
        React.createElement("div", {
          className: "absolute inset-0 z-0",
          style: { pointerEvents: 'none' }
        },
          React.createElement(DOMHeatmapOverlay, {
            container: chartContainerRef.current,
            chart: chartRef.current,
            series: chartType === 'area' ? areaSeriesRef.current : candleSeriesRef.current,
            symbol: activeSymbol,
            activeTimeframe: activeTimeframe,
            visible: isBookmapActive,
            config: normalizedBookmapConfig
          })
        ),
        React.createElement("div", {
          ref: chartContainerRef,
          className: "absolute inset-0 z-10",
          style: { opacity: isVisible ? 1 : 0, transition: "opacity 0.15s ease-out" }
        }),
        React.createElement("div", {
          ref: footprintContainerRef,
          className: "absolute inset-0 z-20 pointer-events-none",
          style: { display: footprintMode !== 'off' ? 'block' : 'none' }
        }),
        showWatermark &&
        React.createElement("div", { className: "absolute top-1/2 left-1/2 transform -translate-x-1/2 -translate-y-1/2 pointer-events-none select-none z-10" },
          React.createElement("div", {
            className: "font-black tracking-wider",
            style: {
              fontSize: getPlatformConfig(detectPlatformType()).watermarkSize,
              fontFamily: "Inter, sans-serif",
              letterSpacing: "0.15em",
              color: `rgba(156, 163, 175, ${getPlatformConfig(detectPlatformType()).watermarkOpacity})`,
              mixBlendMode: "overlay",
              filter: "blur(0.5px)"
            }
          }, (activeSymbol || "").split(':')[0])
        ),
        window.CandleTimer &&
        React.createElement(window.CandleTimer, {
          symbol: activeSymbol,
          timeframe: activeTimeframe,
          lastCandleTime: localLastCandleTime,
          indicatorPanelTop: showVolume ? volPanelTop : showDelta ? deltaPanelTop : 1,
          timerConfig: chartSettings?.timer || getDefaultChartSettings().timer
        }),
        window.PriceChangeIndicator &&
        React.createElement(window.PriceChangeIndicator, {
          symbol: activeSymbol,
          allBars: allBarsRef.current,
          tickData: tickData,
          indicatorPanelTop: showVolume ? volPanelTop : showDelta ? deltaPanelTop : 1,
          settings: chartSettings || getDefaultChartSettings()
        }),
        (() => {
          const platform = detectPlatformType();
          const hasTickData = tickData && (tickData.bid || tickData.ask);
          return (
            chartRef.current && candleSeriesRef.current &&
            React.createElement("div", {
              className: "absolute inset-0 pointer-events-none",
              style: { overflow: 'hidden', zIndex: 20, pointerEvents: 'none' }
            },
              React.createElement("div", { id: "chart-tooltip", className: "hidden absolute z-50 pointer-events-none shadow-lg backdrop-blur-sm transition-opacity duration-150" }),
              React.createElement(DOMHistogramOverlay, {
                container: chartContainerRef.current,
                chart: chartRef.current,
                series: candleSeriesRef.current,
                symbol: activeSymbol,
                visible: showAllOverlays && chartSettings?.overlays?.showDomHistogram,
                config: normalizedDomConfig
              }),
              footprintMode === 'off' &&
              React.createElement(CurrentPriceLineOverlay, {
                chart: chartRef.current,
                series: chartType === 'area' ? areaSeriesRef.current : candleSeriesRef.current,
                liveData: liveData,
                historicalData: historicalData,
                settings: chartSettings?.appearance?.priceLine
              }),
              footprintMode === 'off' &&
              React.createElement(PriceSmoothingOverlay, {
                chart: chartRef.current,
                series: candleSeriesRef.current,
                symbol: activeSymbol,
                lastPrice: tickData && (tickData.last || tickData.bid || tickData.ask) || (liveData && liveData.length > 0 ? liveData[liveData.length - 1].close : null),
                precision: window.getSymbolPrecision ? window.getSymbolPrecision(activeSymbol, detectPlatformType(), tickData?.last || 0).digits : detectPlatformType() === 'mt5' ? 5 : 2,
                enabled: true
              }),
              React.createElement(OrderFlowOverlay, {
                chart: chartRef.current,
                series: candleSeriesRef.current,
                data: ofDataState,
                visible: showAllOverlays && (chartSettings?.overlays?.showOrderFlow ?? false),
                color: chartSettings?.indicators?.orderflow?.cumDeltaColor || "#3b82f6",
                width: chartSettings?.indicators?.orderflow?.cumDeltaWidth || 2
              }),
              React.createElement(LiquidityHeatmapOverlay, {
                chart: chartRef.current,
                series: candleSeriesRef.current,
                data: liquidityHeatmapData,
                visible: showAllOverlays && (chartSettings?.indicators?.liquidity_heatmap?.enabled ?? false),
                tickSize: chartSettings?.indicators?.liquidity_heatmap?.tickSize || 0.25,
                opacity: chartSettings?.indicators?.liquidity_heatmap?.opacity || 0.85
              }),
              (() => {
                const Overlay = window.TpoRenderer;
                const isTpo = chartType === 'tpo';
                if (Overlay && isTpo) {
                  return React.createElement(Overlay, {
                    chart: chartRef.current,
                    series: candleSeriesRef.current,
                    data: footprintMode !== 'off' ? (footprintData?.candles || allBarsRef.current) : allBarsRef.current,
                    settings: chartSettings,
                    visible: true
                  });
                }
                return null;
              })(),
              (() => {
                const Overlay = window.DeltaGridOverlay;
                const isDeltaGrid = chartSettings?.filters?.deltaDisplayMode === 'deltaBars';
                if (Overlay && isDeltaGrid && showDelta) {
                  return React.createElement(Overlay, {
                    chart: chartRef.current,
                    series: candleSeriesRef.current,
                    data: footprintMode !== 'off' ? (footprintData?.candles || allBarsRef.current) : allBarsRef.current,
                    settings: chartSettings,
                    visible: true,
                    style: { top: `${deltaPanelTop * 100}%`, height: `${(1 - deltaPanelTop) * 100}%` }
                  });
                }
                return null;
              })(),
              (() => {
                const isVisible = showAllOverlays && (chartSettings?.indicators?.bigTrades?.enabled ?? true);
                const Overlay = window.BigTradeOverlay;
                if (Overlay) {
                  const baseSettings = chartSettings?.indicators?.bigTrades || window.getDefaultChartSettings && window.getDefaultChartSettings().indicators.bigTrades;
                  const mergedSettings = isBigLlamaActive && llamaParams.big ? {
                    ...baseSettings,
                    real: { ...baseSettings.real, threshold: llamaParams.big.minVol || baseSettings.real.threshold },
                    cumulative: { ...baseSettings.cumulative, threshold: llamaParams.big.minVol || baseSettings.cumulative.threshold }
                  } : baseSettings;
                  return React.createElement(Overlay, {
                    chart: chartRef.current, series: candleSeriesRef.current,
                    trades: bigTrades, settings: mergedSettings, visible: isVisible,
                    tfSeconds: typeof getTimeframeSeconds === 'function' ? getTimeframeSeconds(activeTimeframe) : 0
                  });
                }
                return null;
              })(),
              React.createElement(PositionOverlay, {
                chart: chartRef.current,
                series: candleSeriesRef.current,
                status: systemStatus,
                platform: platform,
                activeSymbol: activeSymbol,
                mt5Positions: mt5Positions,
                mt5PendingOrders: mt5PendingOrders,
                visible: showAllOverlays && (chartSettings?.overlays?.showPositions ?? true),
                tickData: tickData
              }),
              React.createElement(UserDrawingOverlay, {
                chart: chartRef.current,
                series: candleSeriesRef.current,
                activeTool: activeTool,
                activeSymbol: activeSymbol,
                activeTimeframe: activeTimeframe,
                lastBar: lastBar,
                visible: showAllOverlays && (chartSettings?.overlays?.showDrawings ?? true),
                chartId: chartId,
                syncDrawings: chartSettings?.layout?.syncDrawings ?? true,
                onFinish: onToolFinish
              }),
              (() => {
                const isFourier = systemStatus?.algorithm === "FourierCycle";
                let isStale = false;
                if (systemStatus?.timestamp) {
                  const statusTime = new Date(systemStatus.timestamp).getTime();
                  const now = Date.now();
                  if (!isNaN(statusTime)) {
                    const diffSeconds = (now - statusTime) / 1000;
                    if (diffSeconds > 30) isStale = true;
                  }
                }
                const isActive = systemStatus?.trading_mode === "ALGO" && !isStale;
                return isFourier && isActive;
              })() &&
              React.createElement(FourierOverlay, {
                chart: chartRef.current,
                series: candleSeriesRef.current,
                fourierData: systemStatus?.fourier_data,
                visible: showAllOverlays
              })
            )
          );
        })()
      ),

      // ── Volume Panel Splitter & Label ──
      showVolume && React.createElement(React.Fragment, null,
        React.createElement("div", {
          className: "absolute left-0 right-0 z-30 cursor-ns-resize group/splitter",
          style: { top: `${volPanelTop * 100}%`, height: '4px', transform: 'translateY(-2px)' },
          onMouseDown: (e) => {
            e.preventDefault();
            e.stopPropagation();
            const startY = e.clientY;
            const startTop = volPanelTop;
            const outerRect = e.currentTarget.parentElement.getBoundingClientRect();
            let currentT = startTop;
            const handleMouseMove = (me) => {
              const dy = me.clientY - startY;
              let nt = startTop + (dy / outerRect.height);
              nt = Math.max(0.2, Math.min(showDelta ? deltaPanelTop - 0.1 : 0.9, nt));
              currentT = nt;
              setVolPanelTop(nt);
              localStorage.setItem(`chart_${chartId}_vol_top`, nt.toString());
            };
            const handleMouseUp = () => {
              document.removeEventListener('mousemove', handleMouseMove);
              document.removeEventListener('mouseup', handleMouseUp);
              document.body.style.cursor = '';
              if (onUpdateSettings) {
                onUpdateSettings({
                  ...chartSettings,
                  layout: {
                    ...chartSettings?.layout,
                    volumeHeight: Math.round((showDelta ? deltaPanelTop - currentT : 1 - currentT) * 100)
                  }
                });
              }
            };
            document.addEventListener('mousemove', handleMouseMove);
            document.addEventListener('mouseup', handleMouseUp);
            document.body.style.cursor = 'ns-resize';
          }
        },
          React.createElement("div", { className: "w-full h-[1px] bg-white/10 group-hover/splitter:bg-accent/50 transition-colors" })
        ),
        React.createElement("div", {
          className: "absolute left-2 z-30 pointer-events-none",
          style: { top: `${volPanelTop * 100 + 1}%` }
        },
          React.createElement("span", {
            className: "text-[10px] font-black px-1.5 py-0.5 rounded bg-black/70 border border-white/10 shadow-lg",
            style: { color: volumeColor }
          }, "VOLUME"),
          hoverData.volume !== null && React.createElement("span", {
            className: "ml-2 text-[10px] font-mono px-1.5 py-0.5 rounded bg-blue-500/20 text-blue-200 border border-blue-500/30 shadow-lg highlight-shimmer"
          }, Math.round(hoverData.volume).toLocaleString())
        )
      ),

      // ── Delta Panel Splitter & Label ──
      showDelta && React.createElement(React.Fragment, null,
        React.createElement("div", {
          className: "absolute left-0 right-0 z-30 cursor-ns-resize group/splitter",
          style: { top: `${deltaPanelTop * 100}%`, height: '4px', transform: 'translateY(-2px)' },
          onMouseDown: (e) => {
            e.preventDefault();
            e.stopPropagation();
            const startY = e.clientY;
            const startTop = deltaPanelTop;
            const outerRect = e.currentTarget.parentElement.getBoundingClientRect();
            let currentT = startTop;
            const handleMouseMove = (me) => {
              const dy = me.clientY - startY;
              let nt = startTop + (dy / outerRect.height);
              const minT = showVolume ? volPanelTop + 0.1 : 0.3;
              nt = Math.max(minT, Math.min(0.95, nt));
              currentT = nt;
              setDeltaPanelTop(nt);
              localStorage.setItem(`chart_${chartId}_delta_top`, nt.toString());
            };
            const handleMouseUp = () => {
              document.removeEventListener('mousemove', handleMouseMove);
              document.removeEventListener('mouseup', handleMouseUp);
              document.body.style.cursor = '';
              if (onUpdateSettings) {
                onUpdateSettings({
                  ...chartSettings,
                  layout: {
                    ...chartSettings?.layout,
                    deltaHeight: Math.round((1 - currentT) * 100)
                  }
                });
              }
            };
            document.addEventListener('mousemove', handleMouseMove);
            document.addEventListener('mouseup', handleMouseUp);
            document.body.style.cursor = 'ns-resize';
          }
        },
          React.createElement("div", { className: "w-full h-[1px] bg-white/10 group-hover/splitter:bg-accent/50 transition-colors" })
        ),
        React.createElement("div", {
          className: "absolute left-2 z-30 pointer-events-none",
          style: { top: `${deltaPanelTop * 100 + 1}%` }
        },
          React.createElement("span", {
            className: "text-[10px] font-black px-1.5 py-0.5 rounded bg-black/70 border border-white/10 shadow-lg",
            style: { color: deltaColor }
          }, (() => {
            const modeNames = { histogram: 'HISTOGRAM', deltaBars: 'DELTA BARS', cumulativeCandles: 'CUM. CANDLES', cumulativeLine: 'CUM. LINE' };
            const dm = chartSettings?.filters?.deltaDisplayMode || 'histogram';
            return 'DELTA \u00b7 ' + (modeNames[dm] || 'HISTOGRAM');
          })()),
          hoverData.delta !== null && React.createElement("span", {
            className: "ml-2 text-[10px] font-mono px-1.5 py-0.5 rounded bg-orange-500/20 text-orange-200 border border-orange-500/30 shadow-lg highlight-shimmer"
          }, (hoverData.delta > 0 ? "+" : "") + Math.round(hoverData.delta).toLocaleString())
        )
      ),

      chartMenu &&
      React.createElement("div", {
        className: "fixed z-50 bg-[#1a1a1a] border border-border rounded shadow-xl py-1 w-56 text-xs text-white backdrop-blur-md animate-in fade-in zoom-in-95 duration-100",
        style: { left: chartMenu.x, top: chartMenu.y }
      },
        React.createElement("div", { className: "px-3 py-1.5 text-muted border-b border-white/10 font-bold mb-1" },
          "Price: ", chartMenu.price.toFixed(window.getSymbolPrecision ? window.getSymbolPrecision(activeSymbol, detectPlatformType(), chartMenu.price).digits : 2)
        ),
        React.createElement("div", { className: "px-3 py-1 text-[10px] text-accent/70 border-b border-white/5 mb-1" },
          (() => {
            const currentSL = parseFloat(localStorage.getItem("orderEntry_sl") || "20");
            const currentTP = parseFloat(localStorage.getItem("orderEntry_tp") || "40");
            const hasSL = !isNaN(currentSL) && currentSL > 0;
            const hasTP = !isNaN(currentTP) && currentTP > 0;
            if (hasSL && hasTP) return `Smart: Order + SL(${currentSL}) + TP(${currentTP})`;
            if (hasSL) return `Smart: Order + SL(${currentSL})`;
            if (hasTP) return `Smart: Order + TP(${currentTP})`;
            return "Smart: No SL/TP (None)";
          })()
        ),
        React.createElement("button", { className: "w-full text-left px-3 py-1.5 hover:bg-white/10 text-green-400 font-bold flex justify-between", onClick: () => executeMenuOrder("BUY LIMIT", chartMenu.price) },
          React.createElement("span", null, "BUY LIMIT"), React.createElement("i", { className: "fas fa-arrow-up text-[10px] opacity-50" })
        ),
        React.createElement("button", { className: "w-full text-left px-3 py-1.5 hover:bg-white/10 text-red-400 font-bold flex justify-between", onClick: () => executeMenuOrder("SELL LIMIT", chartMenu.price) },
          React.createElement("span", null, "SELL LIMIT"), React.createElement("i", { className: "fas fa-arrow-down text-[10px] opacity-50" })
        ),
        React.createElement("button", { className: "w-full text-left px-3 py-1.5 hover:bg-white/10 text-green-400 font-bold flex justify-between", onClick: () => executeMenuOrder("BUY STOP", chartMenu.price) },
          React.createElement("span", null, "BUY STOP"), React.createElement("i", { className: "fas fa-arrow-up text-[10px] opacity-50" })
        ),
        React.createElement("button", { className: "w-full text-left px-3 py-1.5 hover:bg-white/10 text-red-400 font-bold flex justify-between", onClick: () => executeMenuOrder("SELL STOP", chartMenu.price) },
          React.createElement("span", null, "SELL STOP"), React.createElement("i", { className: "fas fa-arrow-down text-[10px] opacity-50" })
        ),
        React.createElement("div", { className: "h-px bg-white/10 my-1" }),
        React.createElement("button", { className: "w-full text-left px-3 py-1.5 hover:bg-white/10 text-green-500 font-bold", onClick: () => executeMenuOrder("BUY MKT", 0) }, "BUY MARKET"),
        React.createElement("button", { className: "w-full text-left px-3 py-1.5 hover:bg-white/10 text-red-500 font-bold", onClick: () => executeMenuOrder("SELL MKT", 0) }, "SELL MARKET")
      )
    )
  );
});

class ErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false, error: null, errorInfo: null };
  }
  static getDerivedStateFromError(error) {
    return { hasError: true };
  }
  componentDidCatch(error, errorInfo) {
    this.setState({ error, errorInfo });
    console.error("React Error Boundary:", error, errorInfo);
  }
  render() {
    if (this.state.hasError) {
      return (
        React.createElement("div", { className: "p-4 bg-red-900/50 text-white border border-red-500 rounded m-4" },
          React.createElement("h2", { className: "font-bold text-lg mb-2" },
            React.createElement("i", { className: "fas fa-exclamation-triangle" }), " ", "UI Critical Error"
          ),
          React.createElement("pre", { className: "text-xs font-mono bg-black/50 p-2 rounded overflow-auto max-h-40" },
            this.state.error && this.state.error.toString()
          ),
          React.createElement("button", {
            onClick: () => window.location.reload(),
            className: "mt-4 px-4 py-2 bg-red-600 hover:bg-red-500 rounded font-bold text-sm"
          }, "RELOAD PLATFORM")
        )
      );
    }
    return this.props.children;
  }
}

window.ChartComponent = ChartComponent;
window.ErrorBoundary = ErrorBoundary;
