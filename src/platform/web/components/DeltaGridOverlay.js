const DeltaGridOverlay = ({ chart, series, data, settings, visible = true, style }) => {
  const { useEffect, useRef } = React;
  const canvasRef = useRef(null);
  const dataRef = useRef(data);
  const settingsRef = useRef(settings);
  const visibleRef = useRef(visible);

  useEffect(() => {
    dataRef.current = data;
    settingsRef.current = settings;
    visibleRef.current = visible;
  }, [data, settings, visible, style]);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas || !chart) return;
    const ctx = canvas.getContext('2d', { alpha: true });
    let animationFrameId;

    const render = () => {
      const dpr = window.devicePixelRatio || 1;
      const rect = canvas.parentNode.getBoundingClientRect();
      
      if (rect.width === 0 || rect.height === 0) {
        animationFrameId = requestAnimationFrame(render);
        return;
      }

      const canvasWidth = rect.width * dpr;
      const canvasHeight = rect.height * dpr;

      if (canvas.width !== canvasWidth || canvas.height !== canvasHeight) {
        canvas.width = canvasWidth;
        canvas.height = canvasHeight;
        canvas.style.width = `${rect.width}px`;
        canvas.style.height = `${rect.height}px`;
      }

      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.clearRect(0, 0, rect.width, rect.height);

      if (!visibleRef.current || !dataRef.current || dataRef.current.length === 0) {
        animationFrameId = requestAnimationFrame(render);
        return;
      }

      const timeScale = chart.timeScale();
      const visibleRange = timeScale.getVisibleLogicalRange();
      if (!visibleRange) {
        animationFrameId = requestAnimationFrame(render);
        return;
      }

      const barSpacing = timeScale.options().barSpacing || 6;
      const cellW = Math.max(2, Math.floor(barSpacing) - 1);
      
      // Calculate row height (we have 7 rows: Ask, Bid, Delta, Delta/Vol, Session Delta, Max.Delta, Volume)
      const rows = ['Ask', 'Bid', 'Delta', 'Delt/Vol', 'Sess.Delt', 'Max.Delt', 'Volume'];
      const rowCount = rows.length;
      const rowH = rect.height / rowCount;
      const fontSize = Math.max(5, Math.min(11, rowH * 0.75));
      
      // Colors from settings or defaults
      const posColor = settingsRef.current?.filters?.deltaPositiveColor || '#26a69a';
      const negColor = settingsRef.current?.filters?.deltaNegativeColor || '#ef5350';
      const textDim = 'rgba(255, 255, 255, 0.7)';
      const textBright = 'rgba(255, 255, 255, 0.95)';
      const bgDark = 'rgb(10, 10, 12)';
      const bgLight = 'rgb(18, 18, 20)';
      
      ctx.font = `${fontSize}px "JetBrains Mono", ui-monospace, Consolas, monospace`;
      ctx.textAlign = 'center';
      ctx.textBaseline = 'middle';

      // Draw row backgrounds and labels
      const labelWidth = 65;
      for (let i = 0; i < rowCount; i++) {
        const y = i * rowH;
        // Background strip
        ctx.fillStyle = i % 2 === 0 ? bgDark : bgLight;
        ctx.fillRect(labelWidth, y, rect.width - labelWidth, rowH);
        
        ctx.fillStyle = 'rgba(10, 10, 10, 0.8)';
        ctx.fillRect(0, y, labelWidth, rowH);
        
        // Separator line
        ctx.strokeStyle = 'rgba(255, 255, 255, 0.1)';
        ctx.lineWidth = 1;
        ctx.beginPath();
        ctx.moveTo(0, y);
        ctx.lineTo(rect.width, y);
        ctx.stroke();
        
        // Row Label
        ctx.textAlign = 'left';
        ctx.fillStyle = textDim;
        ctx.fillText(rows[i], 4, y + rowH / 2);
      }

      ctx.textAlign = 'center';
      
      // Start processing data
      let cumulativeDelta = 0;
      let maxDeltaSession = 0;
      // We will loop through all data to calculate cumulative values up to the visible range
      // In a highly optimized version, we'd cache this, but for <10k bars it's fast enough in JS
      
      const candles = dataRef.current;
      const startLogical = Math.floor(visibleRange.from);
      const endLogical = Math.ceil(visibleRange.to);
      
      // Calculate running values
      // Map to store precalculated values so we don't recalculate per frame
      const processCandles = () => {
        let cum = 0;
        let md = 0;
        const result = new Array(candles.length);
        for (let i = 0; i < candles.length; i++) {
          const c = candles[i];
          const vol = c.volume || 0;
          const delta = c.delta || 0;
          
          cum += delta;
          if (Math.abs(delta) > Math.abs(md)) md = delta; // approximate max delta tracking
          
          let ask = c.ask;
          let bid = c.bid;
          if (ask === undefined || bid === undefined) {
            ask = (vol + delta) / 2;
            bid = (vol - delta) / 2;
          }
          
          let deltaVolPct = vol > 0 ? (delta / vol) * 100 : 0;
          
          result[i] = {
            ask: ask,
            bid: bid,
            delta: delta,
            deltaVolPct: deltaVolPct,
            cumDelta: cum,
            maxDelta: md,
            vol: vol,
            time: c.time,
            logicalIndex: i
          };
        }
        return result;
      };
      
      // In production we'd want to memoize this, but doing it in render for now.
      const processed = processCandles();

      for (let i = Math.max(0, startLogical - 10); i <= Math.min(processed.length - 1, endLogical + 10); i++) {
        const item = processed[i];
        if (!item) continue;
        
        const x = timeScale.timeToCoordinate(item.time);
        if (x === null || x < labelWidth || x > rect.width) continue;

        const cx = x;
        const cy = (rowIdx) => rowIdx * rowH + rowH / 2;
        
        // Helper to draw a cell
        const drawCell = (rowIdx, text, isPositive, emphasize = false, useBg = false) => {
          const yTop = rowIdx * rowH;
          if (useBg) {
             const bgC = isPositive ? 'rgba(38, 166, 154, 0.2)' : 'rgba(239, 83, 80, 0.2)';
             ctx.fillStyle = bgC;
             ctx.fillRect(cx - cellW/2, yTop + 1, cellW, rowH - 2);
          }
          
          ctx.fillStyle = emphasize ? 
            (isPositive ? posColor : negColor) : 
            textBright;
            
          // Truncate text if it's too wide for the cell
          let displayTxt = text;
          if (cellW < 24 && displayTxt.length > 3) displayTxt = displayTxt.substring(0, 2) + '..';
          if (cellW >= 18 || i % Math.ceil(30/cellW) === 0) { // skip drawing text if cell is too small
             if (fontSize >= 5.5) {
               ctx.fillText(displayTxt, cx, cy(rowIdx));
             }
          }
        };

        const fmt = (v) => {
          if (Math.abs(v) >= 1000) return (v/1000).toFixed(1) + 'k';
          return Math.round(v).toString();
        };

        // 0: Ask
        drawCell(0, fmt(item.ask), item.ask > item.bid);
        // 1: Bid
        drawCell(1, fmt(item.bid), item.bid > item.ask);
        // 2: Delta
        drawCell(2, fmt(item.delta), item.delta > 0, true);
        // 3: Delta/Volume
        drawCell(3, item.deltaVolPct.toFixed(1) + '%', item.deltaVolPct > 0, false, true);
        // 4: Session Delta
        drawCell(4, fmt(item.cumDelta), item.cumDelta > 0, true, true);
        // 5: Max.Delta
        drawCell(5, fmt(item.maxDelta), item.maxDelta > 0, true);
        // 6: Volume
        drawCell(6, fmt(item.vol), true);
        
        // Cell right border
        ctx.strokeStyle = 'rgba(255, 255, 255, 0.05)';
        ctx.beginPath();
        ctx.moveTo(cx + cellW/2, 0);
        ctx.lineTo(cx + cellW/2, rect.height);
        ctx.stroke();
      }

      animationFrameId = requestAnimationFrame(render);
    };

    animationFrameId = requestAnimationFrame(render);
    return () => cancelAnimationFrame(animationFrameId);
  }, [chart]);

  return (
    React.createElement("canvas", {
      ref: canvasRef,
      className: "absolute left-0 right-0 z-40 pointer-events-none",
      style: { display: visible ? 'block' : 'none', ...style }
    })
  );
};

window.DeltaGridOverlay = DeltaGridOverlay;
