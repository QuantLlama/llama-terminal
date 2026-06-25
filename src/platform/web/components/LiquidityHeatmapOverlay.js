const { useEffect, useRef } = React;

const HEAT_COLOR_STOPS = [
    [0.00, 8, 28, 84],
    [0.28, 0, 152, 220],
    [0.52, 42, 226, 157],
    [0.74, 255, 207, 64],
    [0.90, 255, 82, 38],
    [1.00, 255, 244, 196]
];

const getHeatColor = (intensity) => {
    for (let i = 1; i < HEAT_COLOR_STOPS.length; i++) {
        const prev = HEAT_COLOR_STOPS[i - 1];
        const next = HEAT_COLOR_STOPS[i];
        if (intensity <= next[0]) {
            const span = next[0] - prev[0] || 1;
            const t = (intensity - prev[0]) / span;
            return {
                r: Math.round(prev[1] + (next[1] - prev[1]) * t),
                g: Math.round(prev[2] + (next[2] - prev[2]) * t),
                b: Math.round(prev[3] + (next[3] - prev[3]) * t)
            };
        }
    }

    return { r: 255, g: 244, b: 196 };
};

const LiquidityHeatmapOverlay = ({
    chart,
    series,
    data,
    visible = false,
    tickSize = 0.25,
    opacity = 0.85
}) => {
    const canvasRef = useRef(null);
    const animationFrameRef = useRef(null);

    const _dataRef = useRef(data || []);

    useEffect(() => {
        _dataRef.current = data || [];
    }, [data]);

    useEffect(() => {
        if (!visible || !chart || !series || !_dataRef.current || !canvasRef.current) {
            if (canvasRef.current) {
                const ctx = canvasRef.current.getContext('2d');
                ctx.clearRect(0, 0, canvasRef.current.width, canvasRef.current.height);
            }
            return;
        }

        const canvas = canvasRef.current;
        const ctx = canvas.getContext('2d');
        const dpr = window.devicePixelRatio || 1;

        const _tickSize = tickSize;
        const draw = () => {
            const parent = canvas.parentElement;
            if (!parent) return;

            const rect = parent.getBoundingClientRect();
            const w = rect.width;
            const h = rect.height;

            if (canvas.width !== w * dpr || canvas.height !== h * dpr) {
                canvas.width = w * dpr;
                canvas.height = h * dpr;
                canvas.style.width = `${w}px`;
                canvas.style.height = `${h}px`;
            }

            ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
            ctx.clearRect(0, 0, w, h);

            const timeScale = chart.timeScale();
            const logicalRange = timeScale.getVisibleLogicalRange();
            if (!logicalRange) {
                return;
            }

            const barSpacing = timeScale.options().barSpacing || 6;
            // Expand width slightly to cover gaps
            const rectW = Math.ceil(barSpacing) + 1;

            // Calculate height of one tick
            const dummyY1 = series.priceToCoordinate(1000);
            const dummyY2 = series.priceToCoordinate(1000 - _tickSize);
            const rectH = dummyY1 !== null && dummyY2 !== null ? Math.abs(dummyY2 - dummyY1) : 2;
            const finalRectH = Math.max(1, Math.ceil(rectH)) + 1;

            ctx.globalCompositeOperation = 'source-over';

            // Prepare fixed buckets for batched rendering
            const BUCKET_COUNT = 16;
            const buckets = Array.from({ length: BUCKET_COUNT }, () => []);
            const visibleHeat = [];
            const hotRects = [];
            const priceCoordCache = new Map();
            const getPriceY = (price) => {
                if (priceCoordCache.has(price)) return priceCoordCache.get(price);
                const y = series.priceToCoordinate(price);
                priceCoordCache.set(price, y);
                return y;
            };

            const currentData = _dataRef.current;
            
            let minTime = timeScale.coordinateToTime(-200);
            if (minTime !== null && typeof minTime === 'object') minTime = minTime.timestamp || 0;
            if (minTime === null) minTime = 0;

            let maxTime = timeScale.coordinateToTime(w + 200);
            if (maxTime !== null && typeof maxTime === 'object') maxTime = maxTime.timestamp || Infinity;
            if (maxTime === null) maxTime = Infinity;
            let startIdx = 0;
            while (startIdx < currentData.length && currentData[startIdx].time < minTime) {
                startIdx++;
            }
            let endIdx = currentData.length - 1;
            while (endIdx >= startIdx && currentData[endIdx].time > maxTime) {
                endIdx--;
            }

            for (let i = endIdx; i >= startIdx; i--) {
                const item = currentData[i];
                
                if (!item.heatmap || item.heatmap.length === 0) continue;

                const x = timeScale.timeToCoordinate(item.time);
                if (x === null) continue;
                
                const drawX = Math.floor(x - barSpacing / 2);
                let barPeak = null;

                for (const hItem of item.heatmap) {
                    const price = hItem.price;
                    const depth = Number(hItem.depth) || 0;
                    if (depth <= 0) continue;

                    const y = getPriceY(price);
                    
                    if (y === null || y < -50 || y > h + 50) continue;

                    const drawY = Math.floor(y - rectH / 2);
                    const point = { x: drawX, y: drawY, depth, isBarPeak: false };
                    visibleHeat.push(point);

                    if (!barPeak || depth > barPeak.depth) {
                        barPeak = point;
                    }
                }

                if (barPeak) {
                    barPeak.isBarPeak = true;
                }
            }

            let localMaxDepth = 1;
            for (const point of visibleHeat) {
                if (point.depth > localMaxDepth) localMaxDepth = point.depth;
            }

            const logMaxDepth = Math.log1p(localMaxDepth);
            const HOTSPOT_INTENSITY = 0.84;
            const MAX_HOTSPOT_RECTS = 600;

            for (const point of visibleHeat) {
                const logIntensity = Math.log1p(point.depth) / logMaxDepth;
                if (logIntensity < 0.16 && point.depth < localMaxDepth * 0.02) continue;

                const intensity = Math.pow(Math.min(1, logIntensity), 0.9);
                const bucketIndex = Math.min(
                    BUCKET_COUNT - 1,
                    Math.floor(intensity * (BUCKET_COUNT - 1))
                );

                buckets[bucketIndex].push(point);

                if (
                    point.isBarPeak &&
                    intensity >= HOTSPOT_INTENSITY &&
                    hotRects.length < MAX_HOTSPOT_RECTS
                ) {
                    hotRects.push(point);
                }
            }

            // Draw each bucket in a single GPU path
            for (let i = 0; i < BUCKET_COUNT; i++) {
                if (buckets[i].length === 0) continue;
                
                const intensity = (i + 0.5) / BUCKET_COUNT;
                const { r, g, b } = getHeatColor(intensity);
                const alpha = Math.min(0.72, 0.06 + Math.pow(intensity, 1.35) * 0.66);
                
                ctx.fillStyle = `rgba(${r}, ${g}, ${b}, ${alpha})`;
                ctx.beginPath();
                for (const rect of buckets[i]) {
                    ctx.rect(rect.x, rect.y, rectW, finalRectH);
                }
                ctx.fill();
            }

            if (hotRects.length > 0) {
                ctx.save();
                ctx.globalCompositeOperation = 'lighter';
                ctx.shadowBlur = 7;
                ctx.shadowColor = 'rgba(255, 170, 44, 0.38)';
                ctx.fillStyle = 'rgba(255, 205, 64, 0.22)';
                ctx.beginPath();
                for (const rect of hotRects) {
                    ctx.rect(rect.x - 1, rect.y - 1, rectW + 2, finalRectH + 2);
                }
                ctx.fill();

                ctx.shadowBlur = 0;
                ctx.fillStyle = 'rgba(255, 255, 210, 0.48)';
                ctx.beginPath();
                for (const rect of hotRects) {
                    ctx.rect(rect.x, rect.y, Math.max(1, rectW - 1), Math.max(1, finalRectH - 1));
                }
                ctx.fill();
                ctx.restore();
            }
        };

        let _drawQueued = false;
        const scheduleDraw = () => {
            if (_drawQueued) return;
            _drawQueued = true;
            animationFrameRef.current = requestAnimationFrame(() => {
                _drawQueued = false;
                try { draw(); } catch(e) {}
            });
        };

        const resizeObserver = typeof ResizeObserver !== 'undefined'
            ? new ResizeObserver(() => scheduleDraw())
            : null;
        if (resizeObserver && canvas.parentElement) {
            resizeObserver.observe(canvas.parentElement);
        }




        const onMarketDom = (e) => {
            const domData = e.detail;
            if (!domData) return;
            const tfSeconds = 60; // Assuming 60 as fallback, or we can use activeTimeframe if passed
            const ts = domData.timestamp > 1e11 ? domData.timestamp / 1000 : domData.timestamp;
            const time = Math.floor(ts / tfSeconds) * tfSeconds;
            
            const heatmap = [];
            if (domData.bids) domData.bids.forEach(b => heatmap.push({ price: b.price, depth: b.size }));
            if (domData.asks) domData.asks.forEach(a => heatmap.push({ price: a.price, depth: a.size }));
            
            if (heatmap.length > 0) {
                const lastIdx = _dataRef.current.length - 1;
                if (lastIdx >= 0 && _dataRef.current[lastIdx].time === time) {
                    _dataRef.current[lastIdx] = { time, heatmap };
                } else {
                    _dataRef.current.push({ time, heatmap });
                }
                if (_dataRef.current.length > 5000) _dataRef.current = _dataRef.current.slice(-5000);
                scheduleDraw();
            }
        };

        // Initial draw
        scheduleDraw();

        window.addEventListener('market_dom', onMarketDom);
        chart.timeScale().subscribeVisibleLogicalRangeChange(scheduleDraw);
        chart.timeScale().subscribeVisibleTimeRangeChange(scheduleDraw);

        return () => {
            if (resizeObserver) resizeObserver.disconnect();
            window.removeEventListener('market_dom', onMarketDom);
            chart.timeScale().unsubscribeVisibleLogicalRangeChange(scheduleDraw);
            chart.timeScale().unsubscribeVisibleTimeRangeChange(scheduleDraw);
            if (animationFrameRef.current) cancelAnimationFrame(animationFrameRef.current);
        };

    }, [chart, series, data, visible, tickSize, opacity]);

    if (!visible) return null;

    return React.createElement('canvas', {
        ref: canvasRef,
        className: 'absolute inset-0',
        style: {
            pointerEvents: 'none',
            zIndex: 1, // Sit above chart
            mixBlendMode: 'normal', // Blend with background without hiding candles
            opacity: opacity
        }
    });
};

window.LiquidityHeatmapOverlay = LiquidityHeatmapOverlay;
