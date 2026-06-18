const { useEffect, useRef } = React;

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
        
        let maxDepth = 1;
        const initialData = _dataRef.current;
        for (const item of initialData) {
            for (const h of (item.heatmap || [])) {
                if (h.depth > maxDepth) maxDepth = h.depth;
            }
        }

        const _tickSize = tickSize;
        const _opacity = opacity;

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

            // Prepare 20 buckets for batched rendering
            const BUCKET_COUNT = 20;
            const buckets = Array.from({ length: BUCKET_COUNT }, () => []);

            const currentData = _dataRef.current;
            
            let minTime = timeScale.coordinateToTime(-200);
            if (minTime !== null && typeof minTime === 'object') minTime = minTime.timestamp || 0;
            if (minTime === null) minTime = 0;

            let maxTime = timeScale.coordinateToTime(w + 200);
            if (maxTime !== null && typeof maxTime === 'object') maxTime = maxTime.timestamp || Infinity;
            if (maxTime === null) maxTime = Infinity;



            for (let i = currentData.length - 1; i >= 0; i--) {
                const item = currentData[i];
                if (item.time > maxTime) continue;
                if (item.time < minTime) break;
                
                if (!item.heatmap || item.heatmap.length === 0) continue;

                const x = timeScale.timeToCoordinate(item.time);
                if (x === null) continue;
                
                const drawX = Math.floor(x - barSpacing / 2);

                for (const hItem of item.heatmap) {
                    const price = hItem.price;
                    const depth = hItem.depth;
                    const y = series.priceToCoordinate(price);
                    
                    if (y === null || y < -50 || y > h + 50) continue;

                    const drawY = Math.floor(y - rectH / 2);

                    // Calculate color intensity (0.0 to 1.0)
                    const intensity = Math.pow(Math.min(1, depth / maxDepth), 0.6);
                    const bucketIndex = Math.min(BUCKET_COUNT - 1, Math.floor(intensity * BUCKET_COUNT));
                    
                    buckets[bucketIndex].push({ x: drawX, y: drawY });
                }
            }

            // Draw each bucket in a single GPU path
            for (let i = 0; i < BUCKET_COUNT; i++) {
                if (buckets[i].length === 0) continue;
                
                const intensity = (i + 0.5) / BUCKET_COUNT;
                let r, g, b;
                if (intensity < 0.2) {
                    r = 0; g = 0; b = Math.floor(intensity * 5 * 255);
                } else if (intensity < 0.4) {
                    r = 0; g = Math.floor((intensity - 0.2) * 5 * 255); b = 255;
                } else if (intensity < 0.6) {
                    r = Math.floor((intensity - 0.4) * 5 * 255); g = 255; b = 255 - Math.floor((intensity - 0.4) * 5 * 255);
                } else if (intensity < 0.8) {
                    r = 255; g = 255 - Math.floor((intensity - 0.6) * 5 * 255); b = 0;
                } else {
                    r = 255; g = Math.floor((intensity - 0.8) * 5 * 255); b = Math.floor((intensity - 0.8) * 5 * 255);
                }
                
                ctx.fillStyle = `rgba(${r}, ${g}, ${b}, ${0.1 + intensity * 0.35})`;
                ctx.beginPath();
                for (const rect of buckets[i]) {
                    ctx.rect(rect.x, rect.y, rectW, finalRectH);
                }
                ctx.fill();
            }
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
                onEventDraw();
            }
        };

        // Initial draw
        onEventDraw();

        window.addEventListener('market_dom', onMarketDom);
        chart.timeScale().subscribeVisibleLogicalRangeChange(onEventDraw);
        chart.timeScale().subscribeVisibleTimeRangeChange(onEventDraw);
        chart.subscribeCrosshairMove(onEventDraw);

        return () => {
            if (_monitorRaf) cancelAnimationFrame(_monitorRaf);
            window.removeEventListener('market_dom', onMarketDom);
            chart.timeScale().unsubscribeVisibleLogicalRangeChange(onEventDraw);
            chart.timeScale().unsubscribeVisibleTimeRangeChange(onEventDraw);
            chart.unsubscribeCrosshairMove(onEventDraw);
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
