const DOMHeatmapOverlay = ({
    container,
    chart,
    series,
    symbol,
    activeTimeframe = '1m',
    visible = false,
    config = {}
}) => {
    const { useEffect, useRef, useState } = React;
    const canvasRef = useRef(null);

    // Historical data buffer
    const historyRef = useRef([]);
    const pollingRef = useRef(null);
    const lastSymbolRef = useRef(symbol);
    const lastRenderTsRef = useRef(0);

    const settings = {
        levels: Math.max(50, config.levels || 1000),
        opacity: config.opacity !== undefined ? config.opacity : 1.0,
        updateInterval: Math.max(100, config.updateInterval || 250),
        colorTheme: config.colorTheme || 'classic', 
        minVolumeFilter: config.minVolumeFilter || 0,
        maxIntensityFactor: config.maxIntensityFactor || 1.0,
        historySize: config.historySize || 1000,
    };

    const { 
        levels, 
        opacity, 
        updateInterval, 
        colorTheme, 
        minVolumeFilter, 
        maxIntensityFactor, 
        historySize 
    } = settings;

    const [requiredLevels, setRequiredLevels] = useState(levels);
    const [isRateLimited, setIsRateLimited] = useState(false);

    // Clear history on symbol change
    useEffect(() => {
        if (symbol !== lastSymbolRef.current) {
            historyRef.current = [];
            setRequiredLevels(levels);
            lastSymbolRef.current = symbol;
        }
    }, [symbol, levels]);

    // Fetch and accumulate data
    useEffect(() => {
        if (!visible || !symbol) return;

        let active = true;
        const ctrl = new AbortController();

        const processDomData = (data) => {
            if (!data.bids || !data.asks) return;
            const now = Date.now() / 1000;
            const compactBids = data.bids.map(b => [b.price, b.size]);
            const compactAsks = data.asks.map(a => [a.price, a.size]);

            historyRef.current.push({
                time: now, // Real UNIX timestamp in seconds
                bids: compactBids,
                asks: compactAsks
            });

            // Maintain rolling history window
            if (historyRef.current.length > historySize) {
                historyRef.current.shift();
            }
            window.dispatchEvent(new CustomEvent('dom_heatmap_redraw'));
        };

        const handleUpdate = (e) => {
            const data = e.detail;
            if (!data || !active) return;
            const norm = (s) => window.getUniversalSymbol ? window.getUniversalSymbol(s) : s;
            if (norm(data.symbol) !== norm(symbol)) return;
            const now = Date.now();
            if (now - lastRenderTsRef.current < updateInterval) return;
            lastRenderTsRef.current = now;
            processDomData(data);
        };

        window.addEventListener('market_dom', handleUpdate);

        const fetchData = async () => {
            try {
                const url = `/api/v2/feed/dom/${encodeURIComponent(symbol)}?levels=${requiredLevels}`;
                const res = await fetch(url, { signal: ctrl.signal });
                if (!res.ok) return;

                const data = await res.json();
                if (active && data.bids && data.asks) {
                    processDomData(data);
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
    }, [symbol, visible, requiredLevels, updateInterval, historySize]);

    // Rendering Loop
    useEffect(() => {
        if (!visible || !canvasRef.current || !chart || !series) {
            if (canvasRef.current) {
                const ctx = canvasRef.current.getContext('2d');
                ctx.clearRect(0, 0, canvasRef.current.width, canvasRef.current.height);
            }
            return;
        }

        const canvas = canvasRef.current;
        const ctx = canvas.getContext('2d');
        const dpr = window.devicePixelRatio || 1;
        let animationId;

        const getTimeframeSeconds = (tf) => {
            if (!tf) return 60;
            if (tf === '1m') return 60;
            if (tf === '5m') return 300;
            if (tf === '15m') return 900;
            if (tf === '30m') return 1800;
            if (tf === '1h') return 3600;
            if (tf === '4h') return 14400;
            if (tf === 'D') return 86400;
            return 60;
        };
        const tfSeconds = getTimeframeSeconds(activeTimeframe);

        // 8-stop pre-calculated palette to avoid dynamic math evaluations on every cell
        const CLASSIC_COLOR_LUT = [];
        const LLAMA_COLOR_LUT = [];
        const GRAY_COLOR_LUT = [];

        const initColorLut = (theme) => {
            const lut = [];
            for (let idx = 0; idx <= 256; idx++) {
                const i = (idx / 256) * maxIntensityFactor;
                let r, g, b;
                if (theme === 'grayscale') {
                    const v = Math.floor(i * 255);
                    r = v; g = v; b = v;
                } else if (theme === 'llama') {
                    if (i <= 0.001) { r = 8; g = 20; b = 41; }
                    else if (i < 0.2) { r = 0; g = 0; b = Math.floor(i * 5 * 255); }
                    else if (i < 0.4) { r = 0; g = Math.floor((i - 0.2) * 5 * 255); b = 255; }
                    else if (i < 0.6) { r = Math.floor((i - 0.4) * 5 * 255); g = 255; b = 255 - Math.floor((i - 0.4) * 5 * 255); }
                    else if (i < 0.8) { r = 255; g = 255 - Math.floor((i - 0.6) * 5 * 255); b = 0; }
                    else { r = 255; g = Math.floor((i - 0.8) * 5 * 255); b = Math.floor((i - 0.8) * 5 * 255); }
                } else {
                    if (i <= 0.001) { r = 10; g = 10; b = 10; }
                    else if (i < 0.33) { r = Math.floor(i * 3 * 255); g = 0; b = 0; }
                    else if (i < 0.66) { r = 255; g = Math.floor((i - 0.33) * 3 * 165); b = 0; }
                    else if (i < 0.9) { r = 255; g = 165 + Math.floor((i - 0.66) * 4.16 * 90); b = 0; }
                    else { r = 255; g = 255; b = Math.floor((i - 0.9) * 10 * 255); }
                }
                lut.push(`rgba(${r}, ${g}, ${b}, ${opacity})`);
            }
            return lut;
        };

        const themeLuts = {
            classic: initColorLut('classic'),
            llama: initColorLut('llama'),
            grayscale: initColorLut('grayscale')
        };

        const getColorFast = (intensity, theme) => {
            const idx = Math.max(0, Math.min(256, Math.floor(intensity * 256)));
            return themeLuts[theme]?.[idx] || themeLuts.classic[idx];
        };

        let cachedMaxVol = 1;
        let cachedTickSize = 0;
        let lastCalcTime = 0;

        const draw = () => {
            const parent = canvas.parentNode || container;
            const rect = parent.getBoundingClientRect();
            const W = rect.width;

            // Limit height so we don't draw over the Lightweight Charts time scale axis
            const xAxisH = chart.timeScale().options().height || 26;
            const H = Math.max(1, rect.height - xAxisH);

            if (canvas.width !== W * dpr || canvas.height !== H * dpr) {
                canvas.width = W * dpr;
                canvas.height = H * dpr;
                canvas.style.width = `${W}px`;
                canvas.style.height = `${H}px`;
            }

            ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
            ctx.clearRect(0, 0, W, H);

            // Fill the whole canvas with the "0 intensity" base color to give the authentic ATAS background
            ctx.fillStyle = getColorFast(0, colorTheme);
            ctx.fillRect(0, 0, W, H);

            const history = historyRef.current;
            if (history.length === 0) {
                animationId = requestAnimationFrame(draw);
                return;
            }

            const topPrice = series.coordinateToPrice(0);
            const bottomPrice = series.coordinateToPrice(H);
            if (topPrice === null || bottomPrice === null) {
                animationId = requestAnimationFrame(draw);
                return;
            }

            const visibleMax = Math.max(topPrice, bottomPrice);
            const visibleMin = Math.min(topPrice, bottomPrice);
            const visibleRange = visibleMax - visibleMin;
            if (visibleRange <= 0) {
                animationId = requestAnimationFrame(draw);
                return;
            }

            const now = Date.now();
            if (now - lastCalcTime > 1000 || cachedTickSize <= 0) {
                // Calculate a dynamic global max volume over the recent history using 95th percentile
                // to prevent extreme outliers from darkening the entire heatmap
                let allVols = [];
                for (let i = Math.max(0, history.length - 50); i < history.length; i++) {
                    const snap = history[i];
                    for (let j = 0; j < snap.bids.length; j++) allVols.push(snap.bids[j][1]);
                    for (let j = 0; j < snap.asks.length; j++) allVols.push(snap.asks[j][1]);
                }
                allVols.sort((a, b) => a - b);
                let maxVol = allVols.length > 0 ? allVols[Math.floor(allVols.length * 0.95)] : 1;
                if (maxVol < 1) maxVol = 1;
                cachedMaxVol = maxVol;

                // Estimate tick size and required line height using median price difference to avoid gaps
                const latest = history[history.length - 1];
                const allPrices = [...latest.bids, ...latest.asks].map(x => x[0]).sort((a, b) => a - b);
                const diffs = [];
                for (let i = 1; i < allPrices.length; i++) {
                    const diff = allPrices[i] - allPrices[i - 1];
                    if (diff > 0) diffs.push(diff);
                }
                diffs.sort((a, b) => a - b);
                let tickSize = diffs.length > 0 ? diffs[Math.floor(diffs.length / 2)] : (visibleRange / 100);
                if (tickSize <= 0) tickSize = visibleRange / 100;
                cachedTickSize = tickSize;

                lastCalcTime = now;
            }

            const midPrice = (visibleMax + visibleMin) / 2;
            const yRef1 = series.priceToCoordinate(midPrice);
            const yRef2 = series.priceToCoordinate(midPrice + cachedTickSize);
            let rectH = Math.max(1.5, Math.abs(yRef1 - yRef2));

            // Expand rectH slightly to avoid sub-pixel gaps between adjacent price rows
            rectH = Math.ceil(rectH);

            // We need logical timescale coordinates
            const logicalRange = chart.timeScale().getVisibleLogicalRange();
            if (!logicalRange) {
                animationId = requestAnimationFrame(draw);
                return;
            }

            const rightTime = chart.timeScale().coordinateToTime(W - 55);
            const leftTime = chart.timeScale().coordinateToTime(0);

            let timeNowPx = W - 55; // default scale width reserved

            const pxPerMs = 0.05; // default fallback speed
            const rightMostTs = history[history.length - 1].time;
            const barSpacing = chart.timeScale().options().barSpacing || 6;
            const pixelsPerSec = barSpacing / tfSeconds;

            ctx.globalCompositeOperation = 'source-over';

            const rightScaleW = chart.priceScale('right').width() || 60;
            const rightBoundary = W - rightScaleW;
            let currentRightEdge = rightBoundary;

            // 1-Pass Price Coordinate Cache to completely eliminate massive O(N * M) priceToCoordinate API bottlenecks
            const priceCoordCache = new Map();
            const getCachedPriceY = (price) => {
                let y = priceCoordCache.get(price);
                if (y === undefined) {
                    y = series.priceToCoordinate(price);
                    priceCoordCache.set(price, y);
                }
                return y;
            };

            for (let i = history.length - 1; i >= 0; i--) {
                const snap = history[i];

                let x = null;
                const candleTime = Math.floor(snap.time / tfSeconds) * tfSeconds;
                const candleX = chart.timeScale().timeToCoordinate(candleTime);

                if (candleX !== null) {
                    // Intra-bar interpolation
                    const offsetSec = snap.time - candleTime;
                    x = candleX + (offsetSec * pixelsPerSec);
                } else {
                    // Fallback to relative from right edge if charting gap isn't resolved
                    const timeDiffSec = rightMostTs - snap.time;
                    x = rightBoundary - (timeDiffSec * pixelsPerSec);
                }

                let drawX = x;
                const isOldest = i === 0;

                if (isOldest && drawX > 0) {
                    drawX = 0;          // start from deep left
                }

                let mathW = currentRightEdge - drawX;

                if (drawX > rightBoundary) {
                    currentRightEdge = drawX;
                    continue;
                }

                // If column is completely out of screen on the left, break out immediately
                if (drawX + mathW < -10) break;

                const isLatest = i === history.length - 1;

                // Force the absolute newest tick to stretch perfectly flush against the price axis boundary
                if (isLatest) {
                    mathW = rightBoundary - drawX;
                }

                // Overlap 1px to eliminate horizontal visual artifacting seams completely
                let finalDrawX = Math.floor(drawX);
                let finalDrawW = Math.ceil(mathW) + 2; // Aggressive +2 overlap to prevent sub-pixel tearing during aggressive chart scaling

                currentRightEdge = drawX;

                const drawLevels = (levels) => {
                    for (let j = 0; j < levels.length; j++) {
                        const price = levels[j][0];
                        const size = levels[j][1];

                        if (size < minVolumeFilter) continue;
                        if (price < visibleMin || price > visibleMax) continue;

                        const y = getCachedPriceY(price);
                        if (y === null) continue;

                        const intensity = Math.pow(Math.min(1, size / cachedMaxVol), 0.5);
                        ctx.fillStyle = getColorFast(intensity, colorTheme);

                        // Enforce strict integer pixels to prevent Canvas antialiasing flicker
                        const finalY = Math.floor(y - rectH / 2);
                        const finalH = Math.ceil(rectH) + 1; // +1 vertical overlap to prevent horizontal line tearing

                        ctx.fillRect(finalDrawX, finalY, finalDrawW, finalH);
                    }
                };

                drawLevels(snap.bids);
                drawLevels(snap.asks);
            }
        };

        let _isDrawing = false;
        let _needsRedraw = false;
        let lastDrawTime = 0;
        const onEventDraw = () => {
            if (_isDrawing) {
                _needsRedraw = true;
                return;
            }
            const now = performance.now();
            const elapsed = now - lastDrawTime;
            const waitTime = Math.max(0, 16 - elapsed); // throttle to max 60fps

            _isDrawing = true;
            setTimeout(() => {
                requestAnimationFrame(() => {
                    _isDrawing = false;
                    lastDrawTime = performance.now();
                    try { draw(); } catch(e) {}
                    if (_needsRedraw) {
                        _needsRedraw = false;
                        onEventDraw();
                    }
                });
            }, waitTime);
        };

        if (chart) {
            chart.timeScale().subscribeVisibleTimeRangeChange(onEventDraw);
            chart.timeScale().subscribeVisibleLogicalRangeChange(onEventDraw);
            // Disabled subscribeCrosshairMove to prevent redraw overload on simple mouse hover
            // chart.subscribeCrosshairMove(onEventDraw);
        }
        window.addEventListener('dom_heatmap_redraw', onEventDraw);

        // Initial draw
        onEventDraw();

        return () => {
            if (chart) {
                chart.timeScale().unsubscribeVisibleTimeRangeChange(onEventDraw);
                chart.timeScale().unsubscribeVisibleLogicalRangeChange(onEventDraw);
            }
            window.removeEventListener('dom_heatmap_redraw', onEventDraw);
            if (animationId) cancelAnimationFrame(animationId);
        };
    }, [
        visible, 
        chart, 
        series, 
        activeTimeframe, 
        colorTheme,
        opacity, 
        maxIntensityFactor, 
        minVolumeFilter, 
        updateInterval
    ]);

    if (!visible) return null;

    return React.createElement('canvas', {
        ref: canvasRef,
        className: 'absolute inset-0',
        style: {
            pointerEvents: 'none',
            zIndex: 0 // MUST be exactly 0 to sit behind the default Lightweight Charts Canvas (z:1)
        }
    });
};

window.DOMHeatmapOverlay = DOMHeatmapOverlay;
