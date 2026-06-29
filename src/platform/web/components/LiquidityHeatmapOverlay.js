const { useEffect, useRef, useCallback } = React;

// ---------------------------------------------------------------------------
// 8-stop palette — máximo contraste frío→caliente para fondo oscuro de trading
// Las zonas frías son casi invisibles; las calientes explotan en color
// invisible → azul oscuro → azul → cian → verde-lima → dorado → naranja → blanco
// ---------------------------------------------------------------------------
const HEAT_COLOR_STOPS = [
    [0.00,   0,   0,   0],
    [0.18,   6,  30,  90],
    [0.34,   0, 100, 200],
    [0.50,   0, 200, 180],
    [0.65, 120, 230,  60],
    [0.78, 255, 200,   0],
    [0.90, 255,  60,   0],
    [1.00, 255, 250, 220]
];

const getHeatColor = (intensity) => {
    const c = Math.max(0, Math.min(1, intensity));
    for (let i = 1; i < HEAT_COLOR_STOPS.length; i++) {
        const [t0, r0, g0, b0] = HEAT_COLOR_STOPS[i - 1];
        const [t1, r1, g1, b1] = HEAT_COLOR_STOPS[i];
        if (c <= t1) {
            const span = t1 - t0 || 1e-9;
            const t    = (c - t0) / span;
            return {
                r: Math.round(r0 + (r1 - r0) * t),
                g: Math.round(g0 + (g1 - g0) * t),
                b: Math.round(b0 + (b1 - b0) * t)
            };
        }
    }
    return { r: 255, g: 250, b: 220 };
};

const _getTimeframeSeconds = (tf) => {
    if (!tf) return 60;
    const value = parseInt(tf) || 1;
    if (tf.includes("M") && !tf.includes("m")) return value * 2592000;
    if (tf.toLowerCase().includes("mn") || tf.toLowerCase().includes("mo")) return value * 2592000;
    if (tf.toLowerCase().includes("w")) return value * 604800;
    if (tf.toLowerCase().includes("d")) return value * 86400;
    if (tf.toLowerCase().includes("h")) return value * 3600;
    if (tf.toLowerCase().includes("m")) return value * 60;
    if (tf.toLowerCase().includes("s")) return value;
    return 60;
};

// Estimate effective tick size from actual heatmap price data
const _estimateTickSize = (dataBuffer, fallbackTickSize) => {
    if (!dataBuffer || dataBuffer.length === 0) return fallbackTickSize;
    const samples = [];
    const sampleCount = Math.min(20, dataBuffer.length);
    for (let i = dataBuffer.length - sampleCount; i < dataBuffer.length; i++) {
        const hm = dataBuffer[i]?.heatmap;
        if (hm && hm.length > 1) {
            const prices = hm.map(h => h.price).sort((a, b) => a - b);
            for (let j = 1; j < Math.min(prices.length, 30); j++) {
                const diff = prices[j] - prices[j - 1];
                if (diff > 1e-8) samples.push(diff);
            }
        }
    }
    if (samples.length === 0) return fallbackTickSize;
    samples.sort((a, b) => a - b);
    return samples[Math.floor(samples.length / 2)];
};

const LiquidityHeatmapOverlay = ({
    chart,
    series,
    data,
    symbol,
    activeTimeframe = '1m',
    visible = false,
    tickSize = 0.25,
    opacity = 0.85
}) => {
    const canvasRef = useRef(null);
    const animationFrameRef = useRef(null);

    const _dataRef = useRef([]);
    const _lastDataIdRef = useRef(null);
    const _liveConfirmMap = useRef(new Map());
    const MIN_CONFIRM_SNAPSHOTS = 2;

    useEffect(() => {
        if (!data || data.length === 0) return;
        const dataId = `${data.length}_${data[0]?.time}_${data[data.length - 1]?.time}`;
        if (_lastDataIdRef.current === dataId) return;
        _lastDataIdRef.current = dataId;

        const buffer = _dataRef.current;
        if (buffer.length === 0) {
            _dataRef.current = data.map(d => ({ ...d }));
            return;
        }

        const historicalMap = new Map();
        for (const d of data) historicalMap.set(d.time, d);

        const liveMap = new Map();
        for (const d of buffer) liveMap.set(d.time, d);

        for (const [time, d] of historicalMap) {
            if (!liveMap.has(time)) liveMap.set(time, { ...d });
        }

        const merged = Array.from(liveMap.values()).sort((a, b) => a.time - b.time);
        _dataRef.current = merged.length > 5000 ? merged.slice(-5000) : merged;
    }, [data]);

    useEffect(() => {
        if (!visible || !chart || !series || !canvasRef.current) {
            if (canvasRef.current) {
                const ctx = canvasRef.current.getContext('2d');
                ctx.clearRect(0, 0, canvasRef.current.width, canvasRef.current.height);
            }
            return;
        }

        const canvas = canvasRef.current;
        const ctx    = canvas.getContext('2d');
        const dpr    = window.devicePixelRatio || 1;

        const draw = () => {
            const parent = canvas.parentElement;
            if (!parent) return;

            const rect = parent.getBoundingClientRect();
            const w = rect.width;
            const h = rect.height;

            const physW = Math.round(w * dpr);
            const physH = Math.round(h * dpr);
            if (canvas.width !== physW || canvas.height !== physH) {
                canvas.width        = physW;
                canvas.height       = physH;
                canvas.style.width  = `${w}px`;
                canvas.style.height = `${h}px`;
            }

            ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
            ctx.clearRect(0, 0, w, h);

            const currentData = _dataRef.current;
            if (!currentData || currentData.length === 0) return;

            const timeScale    = chart.timeScale();
            const logicalRange = timeScale.getVisibleLogicalRange();
            if (!logicalRange) return;

            const effectiveTickSize = _estimateTickSize(currentData, tickSize);
            const barSpacing        = timeScale.options().barSpacing || 6;

            // ----------------------------------------------------------------
            // Ancho de barra — siempre al menos 3px para ser visible
            // ----------------------------------------------------------------
            const rectW = Math.max(3, Math.ceil(barSpacing) + 1);

            // ----------------------------------------------------------------
            // Altura de un tick en píxeles
            // Problema original: con prices altos (NQ 20000, BTC 65000) y
            // effectiveTickSize chico, rectH resultaba en ~1px → líneas finísimas.
            // Solución: garantizar mínimo 3px y escalar según zoom.
            // ----------------------------------------------------------------
            const midPrice = currentData[currentData.length - 1]?.close || 1000;
            const py1      = series.priceToCoordinate(midPrice);
            const py2      = series.priceToCoordinate(midPrice - effectiveTickSize);
            const rawRectH = (py1 !== null && py2 !== null) ? Math.abs(py2 - py1) : 3;
            // Mínimo 3px — nunca líneas de 1px que no se ven
            // +2px de overlap vertical — elimina gaps entre ticks adyacentes
            const finalRectH = Math.max(3, Math.ceil(rawRectH)) + 2;

            ctx.globalCompositeOperation = 'source-over';

            let minTime = timeScale.coordinateToTime(-200);
            if (minTime !== null && typeof minTime === 'object') minTime = minTime.timestamp || 0;
            if (minTime === null) minTime = 0;

            let maxTime = timeScale.coordinateToTime(w + 200);
            if (maxTime !== null && typeof maxTime === 'object') maxTime = maxTime.timestamp || Infinity;
            if (maxTime === null) maxTime = Infinity;

            let startIdx = 0;
            while (startIdx < currentData.length && currentData[startIdx].time < minTime) startIdx++;
            let endIdx = currentData.length - 1;
            while (endIdx >= startIdx && currentData[endIdx].time > maxTime) endIdx--;

            // ----------------------------------------------------------------
            // Recolectar puntos visibles
            // ----------------------------------------------------------------
            const BUCKET_COUNT    = 20;
            const buckets         = Array.from({ length: BUCKET_COUNT }, () => []);
            const visibleHeat     = [];
            const hotRects        = [];
            const extremeRects    = []; // top 5% — "paredes" máximas
            const priceCoordCache = new Map();

            const getPriceY = (price) => {
                if (priceCoordCache.has(price)) return priceCoordCache.get(price);
                const y = series.priceToCoordinate(price);
                priceCoordCache.set(price, y);
                return y;
            };

            for (let i = endIdx; i >= startIdx; i--) {
                const item = currentData[i];
                if (!item.heatmap || item.heatmap.length === 0) continue;

                const x = timeScale.timeToCoordinate(item.time);
                if (x === null) continue;

                const drawX  = Math.floor(x - barSpacing / 2);
                let barPeak  = null;

                for (const hItem of item.heatmap) {
                    const depth = Number(hItem.depth) || 0;
                    if (depth <= 0) continue;

                    const y = getPriceY(hItem.price);
                    if (y === null || y < -50 || y > h + 50) continue;

                    const drawY = Math.floor(y - rawRectH / 2);
                    const point = { x: drawX, y: drawY, depth, isBarPeak: false };
                    visibleHeat.push(point);

                    if (!barPeak || depth > barPeak.depth) barPeak = point;
                }

                if (barPeak) barPeak.isBarPeak = true;
            }

            if (visibleHeat.length === 0) return;

            // ----------------------------------------------------------------
            // Normalización doble optimizada:
            //   1. Estimación O(N) del techo para evitar sort() costoso.
            //   2. Sqrt sobre la intensidad → eleva el rango medio
            // ----------------------------------------------------------------
            let maxDepth = 0;
            let sumDepth = 0;
            const len = visibleHeat.length;
            for (let i = 0; i < len; i++) {
                const d = visibleHeat[i].depth;
                if (d > maxDepth) maxDepth = d;
                sumDepth += d;
            }
            const avgDepth = sumDepth / (len || 1);
            const p90depth = Math.max(1, avgDepth + (maxDepth - avgDepth) * 0.6);

            const logMax       = Math.log1p(p90depth);
            const noiseFloor   = p90depth * 0.015; // filtro de ruido: 1.5% del p90

            const HOTSPOT_INTENSITY  = 0.78;  // naranja → zona caliente
            const EXTREME_INTENSITY  = 0.92;  // blanco  → pared máxima
            const MAX_HOTSPOT_RECTS  = 800;
            const MAX_EXTREME_RECTS  = 200;

            for (const point of visibleHeat) {
                if (point.depth < noiseFloor) continue;

                const logI = Math.min(1, Math.log1p(point.depth) / logMax);
                // Sqrt: eleva el rango medio para que cian/verde/amarillo sean visibles
                const intensity = Math.sqrt(logI);

                if (intensity < 0.10) continue;

                const bi = Math.min(BUCKET_COUNT - 1, Math.floor(intensity * BUCKET_COUNT));
                buckets[bi].push({ ...point, intensity });

                if (point.isBarPeak) {
                    if (intensity >= EXTREME_INTENSITY && extremeRects.length < MAX_EXTREME_RECTS) {
                        extremeRects.push(point);
                    } else if (intensity >= HOTSPOT_INTENSITY && hotRects.length < MAX_HOTSPOT_RECTS) {
                        hotRects.push(point);
                    }
                }
            }

            // ----------------------------------------------------------------
            // RENDER 1 — Cuerpo del heatmap por bucket
            // Alpha en curva S: zonas frías casi invisibles, calientes bien opacas
            // ----------------------------------------------------------------
            for (let i = 0; i < BUCKET_COUNT; i++) {
                if (!buckets[i].length) continue;

                const intensity = (i + 0.5) / BUCKET_COUNT;
                const { r, g, b } = getHeatColor(intensity);

                // Curva S centrada en 0.50 — corte limpio frío/caliente
                const sig   = 1 / (1 + Math.exp(-9 * (intensity - 0.50)));
                const alpha = Math.min(0.80, 0.03 + sig * 0.77) * opacity;

                ctx.fillStyle = `rgba(${r},${g},${b},${alpha.toFixed(3)})`;
                ctx.beginPath();
                for (const pt of buckets[i]) {
                    ctx.rect(pt.x, pt.y, rectW, finalRectH);
                }
                ctx.fill();
            }

            // ----------------------------------------------------------------
            // RENDER 2 — Zonas calientes (naranja): glow suave
            // ----------------------------------------------------------------
            if (hotRects.length > 0) {
                ctx.save();
                ctx.globalCompositeOperation = 'lighter';
                // Removed shadowBlur to fix severe panning/zooming lag
                ctx.fillStyle   = 'rgba(255,160,30,0.40)';
                ctx.beginPath();
                for (const pt of hotRects) {
                    ctx.rect(pt.x - 1, pt.y - 1, rectW + 2, finalRectH + 2);
                }
                ctx.fill();
                ctx.restore();
            }

            // ----------------------------------------------------------------
            // RENDER 3 — Paredes extremas (blanco-amarillo): máximo destaque
            // Estas son las "órdenes institucionales" — deben verse de inmediato
            // ----------------------------------------------------------------
            if (extremeRects.length > 0) {
                // Capa 1: glow exterior amplio simulado sin shadowBlur
                ctx.save();
                ctx.globalCompositeOperation = 'lighter';
                ctx.fillStyle   = 'rgba(255,200,40,0.50)';
                ctx.beginPath();
                for (const pt of extremeRects) {
                    ctx.rect(pt.x - 2, pt.y - 2, rectW + 4, finalRectH + 4);
                }
                ctx.fill();
                ctx.restore();

                // Capa 2: núcleo blanco brillante
                ctx.save();
                ctx.globalCompositeOperation = 'source-over';
                ctx.fillStyle = `rgba(255,250,200,${(0.85 * opacity).toFixed(3)})`;
                ctx.beginPath();
                for (const pt of extremeRects) {
                    ctx.rect(pt.x, pt.y, rectW, finalRectH);
                }
                ctx.fill();
                ctx.restore();

                // Capa 3: línea horizontal de 1px en el centro del tick
                // Marca con precisión el PRECIO EXACTO de la pared
                ctx.save();
                ctx.globalCompositeOperation = 'source-over';
                ctx.strokeStyle = `rgba(255,245,150,${(0.95 * opacity).toFixed(3)})`;
                ctx.lineWidth   = 1.5;
                ctx.beginPath();
                for (const pt of extremeRects) {
                    const cy = pt.y + Math.floor(finalRectH / 2);
                    ctx.moveTo(pt.x - 2, cy);
                    ctx.lineTo(pt.x + rectW + 2, cy);
                }
                ctx.stroke();
                ctx.restore();
            }
        };

        let _drawQueued = false;
        const scheduleDraw = () => {
            if (_drawQueued) return;
            _drawQueued = true;
            animationFrameRef.current = requestAnimationFrame(() => {
                _drawQueued = false;
                try { draw(); } catch(e) { /* silent */ }
            });
        };

        const resizeObserver = typeof ResizeObserver !== 'undefined'
            ? new ResizeObserver(() => scheduleDraw())
            : null;
        if (resizeObserver && canvas.parentElement) {
            resizeObserver.observe(canvas.parentElement);
        }

        // Real-time DOM event handler with spoof filtering
        const onMarketDom = (e) => {
            const domData = e.detail;
            if (!domData) return;

            const norm = (s) => window.getUniversalSymbol ? window.getUniversalSymbol(s) : s;
            const currentSymbol = symbol || (chart && chart._activeSymbol);
            if (currentSymbol && domData.symbol && norm(domData.symbol) !== norm(currentSymbol)) return;

            const effectiveTickSize = _estimateTickSize(_dataRef.current, tickSize);
            const tfSeconds = _getTimeframeSeconds(activeTimeframe);
            const ts   = domData.timestamp > 1e11 ? domData.timestamp / 1000 : domData.timestamp;
            const time = Math.floor(ts / tfSeconds) * tfSeconds;

            const bids   = domData.bids || [];
            const asks   = domData.asks || [];
            const binMap = new Map();
            const groupToBin = (price, size) => {
                if (!price || !size) return;
                const p = Number(price);
                const s = Number(size);
                if (!isFinite(p) || !isFinite(s) || s <= 0) return;
                const binPrice = Math.round(p / effectiveTickSize) * effectiveTickSize;
                binMap.set(binPrice, (binMap.get(binPrice) || 0) + s);
            };

            bids.forEach(b => groupToBin(b.price, b.size));
            asks.forEach(a => groupToBin(a.price, a.size));
            if (binMap.size === 0) return;

            const confirmMap    = _liveConfirmMap.current;
            const currentPrices = new Set(binMap.keys());

            for (const [price] of confirmMap) {
                if (!currentPrices.has(price)) confirmMap.delete(price);
            }
            for (const price of currentPrices) {
                confirmMap.set(price, (confirmMap.get(price) || 0) + 1);
            }

            const confirmedHeatmap = [];
            for (const [binPrice, depth] of binMap) {
                if ((confirmMap.get(binPrice) || 0) >= MIN_CONFIRM_SNAPSHOTS) {
                    confirmedHeatmap.push({ price: binPrice, depth });
                }
            }

            const isFirstSnapshot = _dataRef.current.length === 0 ||
                (_dataRef.current.length > 0 && _dataRef.current[_dataRef.current.length - 1].time !== time);

            const heatmap = isFirstSnapshot
                ? Array.from(binMap.entries()).map(([p, d]) => ({ price: Number(p), depth: Number(d) }))
                : confirmedHeatmap;

            if (heatmap.length === 0) return;

            const buffer  = _dataRef.current;
            const lastIdx = buffer.length - 1;

            if (lastIdx >= 0 && buffer[lastIdx].time === time) {
                const EMA_WEIGHT = 0.7;
                const oldMap     = new Map();
                if (buffer[lastIdx].heatmap) {
                    for (const h of buffer[lastIdx].heatmap) oldMap.set(h.price, h.depth);
                }
                const mergedMap = new Map();
                for (const [price, oldDepth] of oldMap) {
                    if (binMap.has(price)) {
                        mergedMap.set(price, binMap.get(price) * EMA_WEIGHT + oldDepth * (1 - EMA_WEIGHT));
                    } else {
                        const decayed = oldDepth * 0.3;
                        if (decayed > 0.01) mergedMap.set(price, decayed);
                    }
                }
                for (const [price, depth] of binMap) {
                    if (!mergedMap.has(price)) mergedMap.set(price, depth);
                }
                buffer[lastIdx] = {
                    ...buffer[lastIdx],
                    heatmap: Array.from(mergedMap.entries()).map(([p, d]) => ({ price: p, depth: d }))
                };
            } else {
                const lastClose = lastIdx >= 0 ? buffer[lastIdx].close : (heatmap[0]?.price || 0);
                buffer.push({ time, heatmap, close: lastClose });
                _liveConfirmMap.current = new Map();
            }

            if (buffer.length > 5000) _dataRef.current = buffer.slice(-5000);
            scheduleDraw();
        };

        let _lastPriceCoord = null;
        let _lastTimeCoord  = null;
        let _lastDataLen    = 0;
        let _monitorRaf     = null;
        const monitorChanges = () => {
            let needsDraw = false;
            const curLen  = _dataRef.current ? _dataRef.current.length : 0;
            if (curLen !== _lastDataLen) { _lastDataLen = curLen; needsDraw = true; }
            if (series) {
                try {
                    const pc           = series.priceToCoordinate(0) || series.priceToCoordinate(100);
                    const logicalRange = chart.timeScale().getVisibleLogicalRange();
                    const tc           = logicalRange ? logicalRange.from : null;
                    if (pc !== _lastPriceCoord || tc !== _lastTimeCoord) {
                        _lastPriceCoord = pc;
                        _lastTimeCoord  = tc;
                        needsDraw = true;
                    }
                } catch(e) {}
            }
            if (needsDraw) scheduleDraw();
            _monitorRaf = requestAnimationFrame(monitorChanges);
        };
        _monitorRaf = requestAnimationFrame(monitorChanges);

        scheduleDraw();

        window.addEventListener('market_dom', onMarketDom);
        chart.timeScale().subscribeVisibleLogicalRangeChange(scheduleDraw);
        chart.timeScale().subscribeVisibleTimeRangeChange(scheduleDraw);

        return () => {
            if (_monitorRaf) cancelAnimationFrame(_monitorRaf);
            if (resizeObserver) resizeObserver.disconnect();
            window.removeEventListener('market_dom', onMarketDom);
            chart.timeScale().unsubscribeVisibleLogicalRangeChange(scheduleDraw);
            chart.timeScale().unsubscribeVisibleTimeRangeChange(scheduleDraw);
            if (animationFrameRef.current) cancelAnimationFrame(animationFrameRef.current);
        };

    }, [chart, series, symbol, activeTimeframe, visible, tickSize, opacity]);

    if (!visible) return null;

    return React.createElement('canvas', {
        ref: canvasRef,
        className: 'absolute inset-0',
        style: {
            pointerEvents: 'none',
            zIndex: 1,
            mixBlendMode: 'normal',
            opacity: opacity
        }
    });
};

window.LiquidityHeatmapOverlay = LiquidityHeatmapOverlay;
