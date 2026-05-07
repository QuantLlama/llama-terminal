const { useState, useEffect, useRef, useMemo, useCallback } = React;

const defaultFibLevels = [
  { level: 0, color: "#787b86", enabled: true },
  { level: 0.236, color: "#f23645", enabled: true },
  { level: 0.382, color: "#ff9800", enabled: true },
  { level: 0.5, color: "#4caf50", enabled: true },
  { level: 0.618, color: "#089981", enabled: true },
  { level: 0.786, color: "#00bcd4", enabled: true },
  { level: 1, color: "#787b86", enabled: true },
  { level: 1.618, color: "#2962ff", enabled: true },
  { level: 2.618, color: "#2962ff", enabled: true },
  { level: 3.618, color: "#2962ff", enabled: true },
  { level: 4.236, color: "#2962ff", enabled: true }
];

const UserDrawingOverlay = ({ chart, series, activeTool, activeSymbol, activeTimeframe, lastBar, chartId, syncDrawings, onFinish, visible = true }) => {
  const [activeSettingsId, setActiveSettingsId] = useState(null);
  const [drawings, setDrawings] = useState(() => {
    try {return JSON.parse(localStorage.getItem('user_drawings_v2')) || [];} catch {return [];}
  });
  const [tempPoints, setTempPoints] = useState([]);
  const [selectedId, setSelectedId] = useState(null);
  const [dragTarget, setDragTarget] = useState(null);
  const [toolbar, setToolbar] = useState(null);
  const [toolbarManualPos, setToolbarManualPos] = useState(() => {
    try { return JSON.parse(localStorage.getItem('drawing_toolbar_pos')); } catch { return null; }
  });
  const [toolbarDrag, setToolbarDrag] = useState(null);
  const [isCreating, setIsCreating] = useState(false);
  const [settingsModalPos, setSettingsModalPos] = useState(null);
  const [modalDrag, setModalDrag] = useState(null);
  const canvasRef = useRef(null);
  const overlayRef = useRef(null);
  useEffect(() => {
    localStorage.setItem('user_drawings_v2', JSON.stringify(drawings));
  }, [drawings]);

  useEffect(() => {
    if (!modalDrag) return;
    const handleMove = (e) => {
      setSettingsModalPos({
        x: e.clientX - modalDrag.offsetX,
        y: e.clientY - modalDrag.offsetY
      });
    };
    const handleUp = () => setModalDrag(null);
    window.addEventListener('mousemove', handleMove, { passive: true });
    window.addEventListener('mouseup', handleUp);
    return () => {
      window.removeEventListener('mousemove', handleMove);
      window.removeEventListener('mouseup', handleUp);
    };
  }, [modalDrag]);
  useEffect(() => {
    const handleClear = () => {
      setDrawings([]);
      setSelectedId(null);
      setIsCreating(false);
      setTempPoints([]);
      localStorage.setItem('user_drawings_v2', '[]');
      if (canvasRef.current) {
        const ctx = canvasRef.current.getContext('2d');
        ctx.clearRect(0, 0, canvasRef.current.width, canvasRef.current.height);
      }
    };
    const handleStorage = (e) => {
      if (e.key === 'user_drawings_v2') {
        try {
          const next = JSON.parse(e.newValue);
          if (Array.isArray(next)) setDrawings(next);
        } catch (err) {}
      }
    };
    window.addEventListener('clear_drawings_local', handleClear);
    window.addEventListener('storage', handleStorage);
    return () => {
      window.removeEventListener('clear_drawings_local', handleClear);
      window.removeEventListener('storage', handleStorage);
    };
  }, []);
  const updateDrawing = (id, updates) => {
    setDrawings((prev) => prev.map((d) => d.id === id ? { ...d, props: { ...d.props, ...updates } } : d));
  };
  const deleteDrawing = (id) => {
    setDrawings((prev) => prev.filter((d) => d.id !== id));
    setToolbar(null);
    if (selectedId === id) setSelectedId(null);
  };
  const cloneDrawing = (id) => {
    const original = drawings.find((d) => d.id === id);
    if (!original) return;
    const newId = Date.now().toString() + Math.random().toString(36).substr(2, 5);
    setDrawings((prev) => [...prev, { ...original, id: newId, points: original.points.map((p) => ({ ...p })) }]);
    setSelectedId(newId);
  };
  useEffect(() => {
    const handleKeyDown = (e) => {
      if (['INPUT', 'TEXTAREA', 'SELECT'].includes(e.target.tagName)) return;
      if ((e.key === 'Delete' || e.key === 'Backspace') && selectedId) {
        deleteDrawing(selectedId);
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [selectedId]);
  const tfSec = useMemo(() => {
    if (!activeTimeframe) return 60;
    const s = String(activeTimeframe).toLowerCase();
    const num = parseInt(s.replace(/[^0-9]/g, '')) || 1;
    if (s.includes('mn')) return num * 30 * 24 * 3600;
    if (s.includes('w')) return num * 604800;
    if (s.includes('d')) return num * 86400;
    if (s.includes('h')) return num * 3600;
    return num * 60;
  }, [activeTimeframe]);
  const refBar = useMemo(() => {
    if (!chart || !series) return { index: 0, time: Math.floor(Date.now() / 1000) };
    const timeScale = chart.timeScale();
    if (lastBar?.time) {
      const logical = timeScale.timeToCoordinate(lastBar.time);
      if (logical !== null) {
        const idx = timeScale.coordinateToLogical(logical);
        if (idx !== null) return { index: idx, time: lastBar.time };
      }
    }
    const range = timeScale.getVisibleLogicalRange();
    if (range) {
      const safeLogicalToTime = (idx) => {
        if (typeof timeScale.logicalToTime === 'function') return timeScale.logicalToTime(idx);
        const coord = timeScale.logicalToCoordinate(idx);
        return coord !== null ? timeScale.coordinateToTime(coord) : null;
      };
      let start = Math.floor(range.to);
      for (let i = 0; i < 1000; i++) {
        const t = safeLogicalToTime(start - i);
        if (t) return { index: start - i, time: typeof t === 'object' ? t.timestamp : t };
      }
    }
    return { index: 0, time: Math.floor(Date.now() / 1000) };
  }, [chart, series, lastBar]);
  const getMapper = useCallback(() => {
    if (!chart || !series || !overlayRef.current) return null;
    const timeScale = chart.timeScale();
    return {
      toX: (time, logical) => {
        if (logical !== undefined && logical !== null) {
          const x = timeScale.logicalToCoordinate(logical);
          if (x !== null) return x;
        }
        const x = timeScale.timeToCoordinate(time);
        if (x !== null) return x;
        const spacing = timeScale.options().barSpacing || 6;
        const range = timeScale.getVisibleLogicalRange();
        if (!range) return null;
        const anchorX = timeScale.logicalToCoordinate(range.from);
        if (anchorX === null) return null;
        const targetLog = logical !== undefined && logical !== null ? logical : refBar.index + (time - refBar.time) / tfSec;
        return anchorX + (targetLog - range.from) * spacing;
      },
      toPoint: (clientX, clientY, rect) => {
        const x = clientX - rect.left,y = clientY - rect.top;
        let price = series.coordinateToPrice(y);
        if (price === null) {
          const h = rect.height;
          const pRange = series.priceScale().getVisiblePriceRange();
          if (pRange) {
            const pDiff = pRange.to - pRange.from;
            price = pRange.to - y / h * pDiff;
          }
        }
        const logical = timeScale.coordinateToLogical(x);
        const futureTime = refBar.time + (logical - refBar.index) * tfSec;
        return { time: Math.round(futureTime), price, logical };
      }
    };
  }, [chart, series, refBar, tfSec]);
  const performHitTest = useCallback((clickX, clickY) => {
    const mapper = getMapper();
    if (!mapper) return null;
    const activeDrawings = [...drawings].reverse().filter((d) => (!d.symbol || d.symbol === activeSymbol) && (syncDrawings !== false || d.chartId === chartId));
    for (const d of activeDrawings) {
      const coords = d.points.map((p) => ({ x: mapper.toX(p.time, p.logical), y: series.priceToCoordinate(p.price) }));
      if (coords.some((c) => c.y === null) || coords.every((c) => c.x === null)) continue;
      const isSelected = d.id === selectedId;
      for (let i = 0; i < coords.length; i++) {
        const dist = Math.sqrt(Math.pow(coords[i].x - clickX, 2) + Math.pow(coords[i].y - clickY, 2));
        if (dist < (isSelected ? 15 : 10)) return { id: d.id, pointIndex: i, drawing: d };
      }
      if (['line', 'pencil', 'arrow'].includes(d.type)) {
        for (let i = 0; i < coords.length - 1; i++) {
          const p1 = coords[i],p2 = coords[i + 1];
          const L2 = Math.pow(p2.x - p1.x, 2) + Math.pow(p2.y - p1.y, 2);
          if (L2 === 0) continue;
          const r = ((clickX - p1.x) * (p2.x - p1.x) + (clickY - p1.y) * (p2.y - p1.y)) / L2;
          if (r < 0 || r > 1) continue;
          const dist = Math.sqrt(Math.pow(clickX - (p1.x + r * (p2.x - p1.x)), 2) + Math.pow(clickY - (p1.y + r * (p2.y - p1.y)), 2));
          if (dist < 10) return { id: d.id, pointIndex: -1, drawing: d };
        }
      } else if (['rect', 'rectangle', 'risk'].includes(d.type)) {
        const xMin = Math.min(coords[0].x, coords[1].x),xMax = Math.max(coords[0].x, coords[1].x);
        const yMin = Math.min(coords[0].y, coords[1].y),yMax = Math.max(coords[0].y, coords.length > 2 ? Math.max(coords[1].y, coords[2].y) : coords[1].y);
        if (clickX >= xMin - 5 && clickX <= xMax + 5 && clickY >= yMin - 5 && clickY <= yMax + 5) return { id: d.id, pointIndex: -1, drawing: d };
      } else if (d.type === 'circle') {
        const r = Math.sqrt(Math.pow(coords[1].x - coords[0].x, 2) + Math.pow(coords[1].y - coords[0].y, 2));
        const dist = Math.sqrt(Math.pow(coords[0].x - clickX, 2) + Math.pow(coords[0].y - clickY, 2));
        if (Math.abs(dist - r) < 10 || dist < r) return { id: d.id, pointIndex: -1, drawing: d };
      } else if (d.type === 'hline') {
        if (Math.abs(coords[0].y - clickY) < 10) return { id: d.id, pointIndex: -1, drawing: d };
      } else if (d.type === 'text') {
        const textWidth = ctx.measureText(d.text || "").width || 60;
        const textHeight = (d.fontSize || 12) * 1.5;
        if (Math.abs(coords[0].x - clickX) < textWidth/2 + 10 && Math.abs(coords[0].y - clickY) < textHeight/2 + 10) 
          return { id: d.id, pointIndex: -1, drawing: d };
      } else if (d.type === 'fib' || d.type === 'measure') {
        const xMin = Math.min(coords[0].x, coords[1].x), xMax = Math.max(coords[0].x, coords[1].x);
        const yMin = Math.min(coords[0].y, coords[1].y), yMax = Math.max(coords[0].y, coords[1].y);
        if (clickX >= xMin - 10 && clickX <= xMax + 10 && clickY >= yMin - 10 && clickY <= yMax + 10) {
           return { id: d.id, pointIndex: -1, drawing: d };
        }
      }
    }
    return null;
  }, [drawings, activeSymbol, chartId, syncDrawings, getMapper, series, selectedId]);

  const updateToolbarPos = useCallback((drawingId) => {
    const drawing = drawings.find(d => d.id === drawingId);
    if (!drawing) return;
    const mapper = getMapper();
    if (!mapper) return;
    const coords = drawing.points.map(p => ({ x: mapper.toX(p.time, p.logical), y: series.priceToCoordinate(p.price) }));
    if (coords.some(c => c.y === null) || coords.every(c => c.x === null)) return;
    
    const xMin = Math.min(...coords.map(c => c.x));
    const xMax = Math.max(...coords.map(c => c.x));
    const yMin = Math.min(...coords.map(c => c.y));
    
    const rect = overlayRef.current?.getBoundingClientRect();
    if (!rect) return;
    
    // Default position: top center of chart if no manual pos
    const defaultX = rect.left + (xMin + xMax) / 2;
    const defaultY = rect.top + yMin - 60;

    setToolbar({
      id: drawingId,
      x: toolbarManualPos ? toolbarManualPos.x : defaultX,
      y: toolbarManualPos ? toolbarManualPos.y : Math.max(20, defaultY),
      drawing: drawing
    });
  }, [drawings, getMapper, series, toolbarManualPos]);
  useEffect(() => {
    const handleGlobalMousedown = (e) => {
      if (activeTool !== 'cursor' && activeTool !== 'crosshair') return;
      if (e.button !== 0 && e.button !== 2) return;
      const rect = overlayRef.current?.getBoundingClientRect();
      if (!rect) return;
      const clickX = e.clientX - rect.left,clickY = e.clientY - rect.top;
      if (clickX < 0 || clickX > rect.width || clickY < 0 || clickY > rect.height) return;
      const hit = performHitTest(clickX, clickY);
      // console.log("[UserDrawingOverlay] Hit test result:", hit?.id, "Button:", e.button);
      if (hit) {
        e.preventDefault();e.stopPropagation();
        setSelectedId(hit.id);
        if (e.button === 2) {
          // No context menu for drawings, just show toolbar
          updateToolbarPos(hit.id);
        } else {
          setDragTarget({ id: hit.id, startX: e.clientX, startY: e.clientY, initialPoints: hit.drawing.points.map((p) => ({ ...p })), pointIndex: hit.pointIndex });
          updateToolbarPos(hit.id);
        }
      } else {
        if (!e.target.closest('.drawing-floating-toolbar')) {
          setSelectedId(null);setToolbar(null);
        } else {
          // If clicked on toolbar, check if it's the grip for dragging
          const grip = e.target.closest('.toolbar-drag-handle');
          if (grip && toolbar) {
            setToolbarDrag({ startX: e.clientX, startY: e.clientY, initialX: toolbar.x, initialY: toolbar.y });
          }
        }
      }
    };
    const handleGlobalContextmenu = (e) => {
      if (activeTool !== 'cursor' && activeTool !== 'crosshair') return;
      const rect = overlayRef.current?.getBoundingClientRect();
      if (!rect) return;
      if (performHitTest(e.clientX - rect.left, e.clientY - rect.top)) e.preventDefault();
    };
    window.addEventListener('mousedown', handleGlobalMousedown, true);
    window.addEventListener('contextmenu', handleGlobalContextmenu, true);
    return () => {
      window.removeEventListener('mousedown', handleGlobalMousedown, true);
      window.removeEventListener('contextmenu', handleGlobalContextmenu, true);
    };
  }, [activeTool, performHitTest]);
  useEffect(() => {
    if (!dragTarget || !chart) return;
    const mapper = getMapper();
    if (!mapper) return;
    const onMove = (e) => {
      if (!overlayRef.current) return;
      const rect = overlayRef.current.getBoundingClientRect();
      const dx = e.clientX - dragTarget.startX,dy = e.clientY - dragTarget.startY;
      if (dragTarget.pointIndex !== -1) {
        const drawing = drawings.find(d => d.id === dragTarget.id);
        const newPoints = dragTarget.initialPoints.map((p, idx) => {
          if (drawing?.type === 'risk' && dragTarget.pointIndex === 0) {
            // Move whole tool when dragging entry point
            const px = mapper.toX(p.time, p.logical), py = series.priceToCoordinate(p.price);
            return mapper.toPoint(rect.left + px + dx, rect.top + py + dy, rect) || p;
          }
          if (idx !== dragTarget.pointIndex) {
             if (drawing?.type === 'risk' && (idx === 1 || idx === 2)) {
               // Update X of other risk points to match the dragged point
               const draggedP = dragTarget.initialPoints[dragTarget.pointIndex];
               const draggedPx = mapper.toX(draggedP.time, draggedP.logical);
               const nextDraggedP = mapper.toPoint(rect.left + draggedPx + dx, rect.top + 0, rect);
               if (nextDraggedP) {
                 const dt = nextDraggedP.time - draggedP.time, dLog = nextDraggedP.logical - (draggedP.logical || 0);
                 return { ...p, time: p.time + dt, logical: p.logical !== undefined ? p.logical + dLog : undefined };
               }
             }
             return p;
          }
          const px = mapper.toX(p.time, p.logical), py = series.priceToCoordinate(p.price);
          if (px === null || py === null) return p;
          return mapper.toPoint(rect.left + px + dx, rect.top + py + dy, rect) || p;
        });
        setDrawings((prev) => prev.map((d) => d.id === dragTarget.id ? { ...d, points: newPoints } : d));
      } else {
        const f = dragTarget.initialPoints[0];
        const sPx = mapper.toX(f.time, f.logical),sPy = series.priceToCoordinate(f.price);
        if (sPx === null || sPy === null) return;
        const nextF = mapper.toPoint(rect.left + sPx + dx, rect.top + sPy + dy, rect);
        if (nextF) {
          const dt = nextF.time - f.time,dp = nextF.price - f.price,dLog = nextF.logical - (f.logical || 0);
          setDrawings((prev) => prev.map((d) => d.id === dragTarget.id ? {
            ...d, points: dragTarget.initialPoints.map((p) => ({
              time: p.time + dt,
              price: p.price + dp,
              logical: p.logical !== undefined ? p.logical + dLog : undefined
            }))
          } : d));
        }
      }
      updateToolbarPos(dragTarget.id);
    };
    const onUp = () => setDragTarget(null);
    window.addEventListener('mousemove', onMove, { passive: true });
    window.addEventListener('mouseup', onUp);
    return () => {window.removeEventListener('mousemove', onMove);window.removeEventListener('mouseup', onUp);};
  }, [dragTarget, chart, series, getMapper, updateToolbarPos]);

  useEffect(() => {
    if (!toolbarDrag) return;
    const onMove = (e) => {
      const dx = e.clientX - toolbarDrag.startX;
      const dy = e.clientY - toolbarDrag.startY;
      const newX = toolbarDrag.initialX + dx;
      const newY = toolbarDrag.initialY + dy;
      setToolbar(prev => prev ? { ...prev, x: newX, y: newY } : null);
    };
    const onUp = (e) => {
      const dx = e.clientX - toolbarDrag.startX;
      const dy = e.clientY - toolbarDrag.startY;
      const finalPos = { x: toolbarDrag.initialX + dx, y: toolbarDrag.initialY + dy };
      setToolbarManualPos(finalPos);
      localStorage.setItem('drawing_toolbar_pos', JSON.stringify(finalPos));
      setToolbarDrag(null);
    };
    window.addEventListener('mousemove', onMove, { passive: true });
    window.addEventListener('mouseup', onUp);
    return () => { window.removeEventListener('mousemove', onMove); window.removeEventListener('mouseup', onUp); };
  }, [toolbarDrag]);

  useEffect(() => {
    if (selectedId && !dragTarget && !isCreating) {
      updateToolbarPos(selectedId);
    }
  }, [selectedId, dragTarget, isCreating, updateToolbarPos]);
  const handleOverlayMouseDown = (e) => {
    if (e.button !== 0 || activeTool === 'cursor' || activeTool === 'crosshair') return;
    const mapper = getMapper();
    if (!mapper) return;
    const rect = overlayRef.current.getBoundingClientRect();
    const pt = mapper.toPoint(e.clientX, e.clientY, rect);
    if (pt) {
      setIsCreating(true);setTempPoints([pt]);
      e.preventDefault();e.stopPropagation();
    }
  };
  const handleOverlayMouseMove = (e) => {
    if (!isCreating) return;
    const mapper = getMapper();
    if (!mapper) return;
    const rect = overlayRef.current.getBoundingClientRect();
    const pt = mapper.toPoint(e.clientX, e.clientY, rect);
    if (pt) {
      if (activeTool === 'pencil') {
        const last = tempPoints[tempPoints.length - 1];
        if (last) {
          const lx = mapper.toX(last.time, last.logical),ly = series.priceToCoordinate(last.price);
          const cx = mapper.toX(pt.time, pt.logical),cy = series.priceToCoordinate(pt.price);
          if (lx !== null && ly !== null && cx !== null && cy !== null && Math.sqrt(Math.pow(cx - lx, 2) + Math.pow(cy - ly, 2)) < 5) return;
        }
        setTempPoints((prev) => [...prev, pt]);
      } else
      if (['hline', 'text'].includes(activeTool)) setTempPoints([pt]);else
      setTempPoints((prev) => [prev[0], pt]);
    }
  };
  const handleOverlayMouseUp = (e) => {
    if (!isCreating) return;
    const mapper = getMapper();
    let fps = [...tempPoints];
    if (mapper && overlayRef.current) {
      const pt = mapper.toPoint(e.clientX, e.clientY, overlayRef.current.getBoundingClientRect());
      if (pt) {
        if (activeTool === 'pencil') fps.push(pt);else
        if (['hline', 'text'].includes(activeTool)) fps = [pt];else
        fps = [fps[0], pt];
      }
    }
    let props = { color: '#fbbf24' };
    if (activeTool === 'risk' && fps.length >= 2) {
      const r = Math.abs(fps[0].price - fps[1].price);
      fps.push({ time: fps[1].time, price: fps[0].price + (fps[1].price < fps[0].price ? r * 2 : -r * 2) });
    }
    if (activeTool === 'fib') {
      props.fibLevels = JSON.parse(JSON.stringify(defaultFibLevels));
      props.extendRight = true;
      props.showPrices = true;
    }
    if (activeTool === 'text') {
      setActiveSettingsId("TEMP_TEXT");
      // Text will be updated via settings modal for the newly created drawing
    }
    const newId = Date.now().toString() + Math.random().toString(36).substr(2, 5);
    if (fps.length >= 1) {
      setDrawings((prev) => [...prev, { id: newId, type: activeTool, points: fps, props, symbol: activeSymbol, chartId, syncDrawings: syncDrawings !== false }]);
      if (activeTool === 'text') setActiveSettingsId(newId);
      if (onFinish) onFinish();
    }
    setIsCreating(false);setTempPoints([]);
  };
  useEffect(() => {
    if (!chart || !series || !canvasRef.current) return;
    let fid;const ctx = canvasRef.current.getContext('2d');
    const draw = () => {
      if (!canvasRef.current || !visible) return;
      const rect = canvasRef.current.getBoundingClientRect();
      if (rect.width === 0) {fid = requestAnimationFrame(draw);return;}
      const dpr = window.devicePixelRatio || 1;
      if (canvasRef.current.width !== rect.width * dpr || canvasRef.current.height !== rect.height * dpr) {
        canvasRef.current.width = rect.width * dpr;canvasRef.current.height = rect.height * dpr;
      }
      ctx.save();ctx.scale(dpr, dpr);ctx.clearRect(0, 0, rect.width, rect.height);
      const mapper = getMapper();
      if (mapper) {
        const items = drawings.filter((d) => (!d.symbol || d.symbol === activeSymbol) && (syncDrawings !== false || d.chartId === chartId)).
        map((d) => ({ ...d, isSelected: d.id === selectedId }));
        if (tempPoints.length > 0) items.push({ type: activeTool, points: tempPoints, isTemp: true, props: { color: '#fbbf24' } });
        items.forEach((d) => {
          const coords = d.points.map((p) => ({ x: mapper.toX(p.time, p.logical), y: series.priceToCoordinate(p.price) }));
          if (coords.length === 0 || coords.some((c) => c.y === null) || coords.every((c) => c.x === null)) return;
          const color = d.isSelected ? '#3b82f6' : d.props?.color || '#fbbf24';
          ctx.strokeStyle = color;ctx.fillStyle = `${color}22`;
          ctx.lineWidth = d.props?.lineWidth || (d.isSelected ? 2 : 1.5);
          if (['line', 'pencil', 'arrow'].includes(d.type)) {
            ctx.beginPath();ctx.moveTo(coords[0].x, coords[0].y);
            coords.slice(1).forEach((c) => ctx.lineTo(c.x, c.y));ctx.stroke();
            if (d.type === 'arrow' && coords.length >= 2) {
              const len = 10,angle = Math.atan2(coords[1].y - coords[0].y, coords[1].x - coords[0].x);
              ctx.beginPath();ctx.moveTo(coords[1].x, coords[1].y);
              ctx.lineTo(coords[1].x - len * Math.cos(angle - Math.PI / 6), coords[1].y - len * Math.sin(angle - Math.PI / 6));
              ctx.lineTo(coords[1].x - len * Math.cos(angle + Math.PI / 6), coords[1].y - len * Math.sin(angle + Math.PI / 6));
              ctx.closePath();ctx.fillStyle = color;ctx.fill();
            }
          } else if (['rect', 'rectangle'].includes(d.type) && coords.length >= 2) {
            const x = Math.min(coords[0].x, coords[1].x),y = Math.min(coords[0].y, coords[1].y);
            const w = Math.abs(coords[0].x - coords[1].x),h = Math.abs(coords[0].y - coords[1].y);
            ctx.fillRect(x, y, w, h);ctx.strokeRect(x, y, w, h);
          } else if (d.type === 'risk' && coords.length >= 2) {
            const entry = coords[0], stop = coords[1], target = coords[2] || coords[0];
            const x = Math.min(entry.x, stop.x), w = Math.abs(entry.x - stop.x);
            const isLong = d.points[1].price < d.points[0].price;
            
            // Draw Areas
            ctx.fillStyle = "rgba(239, 68, 68, 0.2)"; // Red for Stop
            ctx.fillRect(x, Math.min(entry.y, stop.y), w, Math.abs(entry.y - stop.y));
            if (coords.length >= 3) {
              ctx.fillStyle = "rgba(16, 185, 129, 0.2)"; // Green for Target
              ctx.fillRect(x, Math.min(entry.y, target.y), w, Math.abs(entry.y - target.y));
            }
            // Borders
            ctx.strokeStyle = "#ef4444"; ctx.strokeRect(x, Math.min(entry.y, stop.y), w, Math.abs(entry.y - stop.y));
            if (coords.length >= 3) {
              ctx.strokeStyle = "#10b981"; ctx.strokeRect(x, Math.min(entry.y, target.y), w, Math.abs(entry.y - target.y));
            }
            // Entry Line
            ctx.strokeStyle = "white"; ctx.lineWidth = 1; ctx.beginPath();
            ctx.moveTo(x, entry.y); ctx.lineTo(x + w, entry.y); ctx.stroke();

            // Labels helper
            const drawPill = (text, cx, cy, bg) => {
              ctx.font = "11px sans-serif";
              const tw = ctx.measureText(text).width;
              const pw = tw + 14, ph = 20;
              ctx.fillStyle = bg;
              ctx.beginPath();
              ctx.roundRect(cx - pw/2, cy - ph/2, pw, ph, 4);
              ctx.fill();
              ctx.fillStyle = "white";
              ctx.fillText(text, cx - tw/2, cy + 4);
            };

            const formatVal = (v) => v.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
            const pEntry = d.points[0].price, pStop = d.points[1].price;
            const stopDist = Math.abs(pEntry - pStop), stopPerc = (stopDist / pEntry * 100).toFixed(2);
            
            // Stop Label
            drawPill(`Stop: ${formatVal(pStop)} (${stopPerc}%)`, x + w/2, stop.y + (isLong ? 15 : -15), "#ef4444");

            if (coords.length >= 3) {
              const pTarget = d.points[2].price;
              const targetDist = Math.abs(pTarget - pEntry), targetPerc = (targetDist / pEntry * 100).toFixed(2);
              const rr = (targetDist / stopDist).toFixed(2);
              // Target Label
              drawPill(`Target: ${formatVal(pTarget)} (${targetPerc}%)`, x + w/2, target.y + (isLong ? -15 : 15), "#10b981");
              // Center Label (P&L / RR)
              drawPill(`Risk/Reward: ${rr}`, x + w/2, entry.y, "#333");
            }
          } else if (d.type === 'measure' && coords.length >= 2) {
            const isUp = d.points[1].price > d.points[0].price;
            const color = isUp ? '#10b981' : '#ef4444';
            const bgColor = isUp ? 'rgba(16, 185, 129, 0.15)' : 'rgba(239, 68, 68, 0.15)';
            const x1 = coords[0].x, y1 = coords[0].y, x2 = coords[1].x, y2 = coords[1].y;
            const x = Math.min(x1, x2), y = Math.min(y1, y2), w = Math.abs(x2 - x1), h = Math.abs(y2 - y1);
            
            ctx.fillStyle = bgColor;
            ctx.strokeStyle = color;
            ctx.lineWidth = 1;

            // Cross style lines
            ctx.beginPath();
            ctx.moveTo(x1, y1); ctx.lineTo(x2, y1);
            ctx.moveTo(x2, y1); ctx.lineTo(x2, y2);
            ctx.stroke();

            // Background rect
            ctx.fillRect(x, y, w, h);
            
            // Dashed border
            ctx.setLineDash([4, 4]);
            ctx.strokeRect(x, y, w, h);
            ctx.setLineDash([]);
            
            const p1 = d.points[0], p2 = d.points[1];
            const pDiff = p2.price - p1.price, pPerc = (pDiff / p1.price * 100).toFixed(2), bars = Math.abs(p2.logical - p1.logical);
            const durMin = Math.abs(p2.time - p1.time) / 60, durText = durMin < 60 ? `${Math.round(durMin)}m` : `${(durMin/60).toFixed(1)}h`;
            
            const line1 = `${pDiff.toFixed(2)} (${pPerc}%)`;
            const line2 = `${bars} bars, ${durText}`;
            
            ctx.font = "11px sans-serif";
            const tw1 = ctx.measureText(line1).width, tw2 = ctx.measureText(line2).width;
            const boxW = Math.max(tw1, tw2) + 20, boxH = 40;
            ctx.fillStyle = color + "ee"; // Slightly transparent solid color
            ctx.beginPath(); ctx.roundRect(x + w/2 - boxW/2, y + h/2 - boxH/2, boxW, boxH, 4); ctx.fill();
            ctx.fillStyle = "white";
            ctx.fillText(line1, x + w/2 - tw1/2, y + h/2 - 5);
            ctx.fillText(line2, x + w/2 - tw2/2, y + h/2 + 10);
          } else if (d.type === 'circle' && coords.length >= 2) {
            ctx.beginPath();ctx.arc(coords[0].x, coords[0].y, Math.sqrt(Math.pow(coords[1].x - coords[0].x, 2) + Math.pow(coords[1].y - coords[0].y, 2)), 0, Math.PI * 2);
            ctx.fill();ctx.stroke();
          } else if (d.type === 'hline' && coords.length >= 1) {
            ctx.beginPath();ctx.moveTo(0, coords[0].y);ctx.lineTo(rect.width, coords[0].y);ctx.stroke();
          } else if (d.type === 'fib' && coords.length >= 2) {
            const p1 = d.points[0], p2 = d.points[1];
            const levels = d.props?.fibLevels || defaultFibLevels;
            const extendRight = d.props?.extendRight !== false;
            const showPrices = d.props?.showPrices !== false;
            
            levels.forEach((l) => {
              if (!l.enabled) return;
              const price = p1.price + (p2.price - p1.price) * l.level;
              const y = series.priceToCoordinate(price);
              if (y === null) return;
              ctx.strokeStyle = l.color || d.color;
              ctx.setLineDash(d.lineWidth === 1 ? [2, 2] : []);
              ctx.beginPath();
              ctx.moveTo(coords[0].x, y);
              ctx.lineTo(extendRight ? rect.width : coords[1].x, y);
              ctx.stroke();
              ctx.setLineDash([]);
              
              if (showPrices) {
                ctx.fillStyle = l.color || "white";
                ctx.font = "10px sans-serif";
                const label = `${l.level} (${price.toFixed(2)})`;
                ctx.fillText(label, (extendRight ? rect.width : coords[1].x) - 70, y - 3);
              }
            });
          }
          if (d.props?.text) {
            const fontSize = d.props.fontSize || 12;
            const textAlign = d.props.textAlign || "center";
            const textVAlign = d.props.textVAlign || "top";
            
            const xs = coords.map(c => c.x), ys = coords.map(c => c.y);
            let xMin = Math.min(...xs), xMax = Math.max(...xs);
            if (d.type === 'hline') { xMin = 0; xMax = rect.width; }
            const yMin = Math.min(...ys), yMax = Math.max(...ys);
            const midX = (xMin + xMax) / 2, midY = (yMin + yMax) / 2;

            ctx.save();
            ctx.fillStyle = d.props.textColor || "white"; 
            ctx.font = `bold ${fontSize}px sans-serif`;
            ctx.textAlign = textAlign === "left" ? "left" : (textAlign === "right" ? "right" : "center");
            ctx.textBaseline = textVAlign === "top" ? "bottom" : (textVAlign === "bottom" ? "top" : "middle");

            let tx = midX, ty = midY;
            if (textAlign === "left") tx = xMin + (d.type === 'hline' ? 10 : 0);
            if (textAlign === "right") tx = xMax - (d.type === 'hline' ? 10 : 0);
            
            if (textVAlign === "top") ty = yMin - 5;
            else if (textVAlign === "bottom") ty = yMax + 5;
            else ty = midY;

            ctx.fillText(d.props.text, tx, ty);
            ctx.restore();
          }
          if (d.isSelected && !d.isTemp) {
            coords.forEach((c) => {
              ctx.beginPath();ctx.arc(c.x, c.y, 5, 0, Math.PI * 2);
              ctx.fillStyle = "white";ctx.fill();ctx.strokeStyle = "#3b82f6";ctx.lineWidth = 2;ctx.stroke();
            });
          }
        });
      }
      ctx.restore();fid = requestAnimationFrame(draw);
    };
    fid = requestAnimationFrame(draw);
  }, [chart, series, drawings, tempPoints, activeTool, activeSymbol, chartId, syncDrawings, getMapper, visible, selectedId]);

  const renderSettingsModal = () => {
    if (!activeSettingsId) return null;
    let drawing = drawings.find(d => d.id === activeSettingsId);
    if (!drawing && activeSettingsId === "TEMP_TEXT") {
        // Handle temp text settings if needed, but usually we just wait for ID
        return null;
    }
    if (!drawing) return null;

    const p = drawing.props || {};

    return React.createElement("div", {
      className: "fixed inset-0 flex items-center justify-center p-4 bg-black/30 backdrop-blur-[2px] animate-in fade-in duration-200",
      style: { zIndex: 2147483647, pointerEvents: 'auto' },
      onMouseDown: (e) => {
        if (e.target === e.currentTarget) setActiveSettingsId(null);
      }
    },
      React.createElement("div", {
        className: "bg-[#1a1a1a] border border-white/10 rounded-xl shadow-2xl w-full max-w-md overflow-hidden flex flex-col max-h-[90vh]",
        style: {
          zIndex: 2147483647,
          pointerEvents: 'auto',
          ...(settingsModalPos ? {
            position: 'fixed',
            left: settingsModalPos.x,
            top: settingsModalPos.y,
            transform: 'none',
            margin: 0
          } : {})
        },
        onMouseDown: (e) => e.stopPropagation(),
        onClick: (e) => e.stopPropagation()
      },
        // Modal Header
        React.createElement("div", { 
          className: "px-4 py-3 border-b border-white/5 flex items-center justify-between bg-white/5 cursor-move active:cursor-grabbing",
          style: { pointerEvents: 'auto' },
          onMouseDown: (e) => {
            e.stopPropagation();
            const rect = e.currentTarget.closest('.bg-[#1a1a1a]').getBoundingClientRect();
            setModalDrag({
              offsetX: e.clientX - rect.left,
              offsetY: e.clientY - rect.top
            });
          }
        },
          React.createElement("h3", { className: "text-sm font-bold text-accent uppercase tracking-wider" }, `Ajustes: ${drawing.type.toUpperCase()}`),
          React.createElement("button", {
            onClick: () => setActiveSettingsId(null),
            className: "text-gray-400 hover:text-white transition-colors"
          }, React.createElement("i", { className: "fas fa-times" }))
        ),

        // Modal Scrollable Content
        React.createElement("div", { className: "flex-1 overflow-y-auto p-4 space-y-6 custom-scrollbar" },
          
          // Text Configuration (For all tools)
          React.createElement("div", { className: "space-y-4" },
            React.createElement("label", { className: "text-[10px] font-bold text-muted uppercase block" }, "Etiqueta / Texto"),
            React.createElement("textarea", {
              value: p.text || "",
              onChange: (e) => updateDrawing(drawing.id, { text: e.target.value }),
              className: "w-full bg-black/40 border border-white/10 rounded-lg p-3 text-sm text-white focus:border-accent/50 outline-none min-h-[80px] transition-colors",
              placeholder: "Escribe algo aquí..."
            }),
            
            // Text Style Row
            React.createElement("div", { className: "grid grid-cols-2 gap-4" },
              React.createElement("div", { className: "space-y-2" },
                React.createElement("label", { className: "text-[10px] font-bold text-muted uppercase block" }, "Tamaño Fuente"),
                React.createElement("select", {
                  value: p.fontSize || 12,
                  onChange: (e) => updateDrawing(drawing.id, { fontSize: parseInt(e.target.value) }),
                  className: "w-full bg-black border border-white/10 rounded p-1.5 text-xs text-white"
                },
                  [10, 12, 14, 16, 18, 20, 24, 32].map(sz => React.createElement("option", { key: sz, value: sz }, sz + "px"))
                )
              ),
              React.createElement("div", { className: "space-y-2" },
                React.createElement("label", { className: "text-[10px] font-bold text-muted uppercase block" }, "Color Texto"),
                React.createElement("div", { className: "flex gap-1" },
                  ["white", "#fbbf24", "#3b82f6", "#ef4444"].map(c => 
                    React.createElement("button", {
                      key: c,
                      onClick: () => updateDrawing(drawing.id, { textColor: c }),
                      className: `w-6 h-6 rounded border ${p.textColor === c ? 'border-accent' : 'border-transparent'}`,
                      style: { backgroundColor: c }
                    })
                  )
                )
              )
            ),

            // Posicionamiento
            React.createElement("div", { className: "space-y-2" },
              React.createElement("label", { className: "text-[10px] font-bold text-muted uppercase block" }, "Posición"),
              React.createElement("div", { className: "flex flex-col gap-2" },
                // Horiz
                React.createElement("div", { className: "flex gap-2" },
                  ["left", "center", "right"].map(pos => 
                    React.createElement("button", {
                      key: pos,
                      onClick: () => updateDrawing(drawing.id, { textAlign: pos }),
                      className: `flex-1 py-1 text-[10px] rounded border ${p.textAlign === pos ? 'bg-accent text-black font-bold' : 'bg-white/5 border-white/10 text-gray-400'}`
                    }, pos.toUpperCase())
                  )
                ),
                // Vert
                React.createElement("div", { className: "flex gap-2" },
                  ["top", "middle", "bottom"].map(pos => 
                    React.createElement("button", {
                      key: pos,
                      onClick: () => updateDrawing(drawing.id, { textVAlign: pos }),
                      className: `flex-1 py-1 text-[10px] rounded border ${p.textVAlign === pos ? 'bg-accent text-black font-bold' : 'bg-white/5 border-white/10 text-gray-400'}`
                    }, pos.toUpperCase())
                  )
                )
              )
            )
          ),

          // Fibonacci Specific Levels
          drawing.type === 'fib' && React.createElement("div", { className: "pt-6 border-t border-white/5 space-y-4" },
            React.createElement("label", { className: "text-[10px] font-bold text-muted uppercase block" }, "Niveles de Fibonacci"),
            React.createElement("div", { className: "grid grid-cols-2 gap-x-6 gap-y-2" },
              (p.fibLevels || defaultFibLevels).map((level, idx) => 
                React.createElement("div", { key: idx, className: "flex items-center justify-between gap-2 bg-white/[0.02] p-2 rounded" },
                  React.createElement("div", { className: "flex items-center gap-2" },
                    React.createElement("input", {
                      type: "checkbox",
                      checked: level.enabled,
                      onChange: () => {
                        const newLevels = [...(p.fibLevels || defaultFibLevels)];
                        newLevels[idx].enabled = !newLevels[idx].enabled;
                        updateDrawing(drawing.id, { fibLevels: newLevels });
                      },
                      className: "accent-accent"
                    }),
                    React.createElement("span", { className: "text-[10px] font-mono text-gray-300 w-10" }, level.level.toFixed(3))
                  ),
                  React.createElement("input", {
                    type: "color",
                    value: level.color || "#787b86",
                    onChange: (e) => {
                      const newLevels = [...(p.fibLevels || defaultFibLevels)];
                      newLevels[idx].color = e.target.value;
                      updateDrawing(drawing.id, { fibLevels: newLevels });
                    },
                    className: "w-6 h-6 bg-transparent border-none outline-none cursor-pointer"
                  })
                )
              )
            ),
            
            // Fib Options
            React.createElement("div", { className: "space-y-3 pt-4" },
               React.createElement("label", { className: "flex items-center gap-2 cursor-pointer" },
                 React.createElement("input", {
                   type: "checkbox",
                   checked: p.extendRight !== false,
                   onChange: () => updateDrawing(drawing.id, { extendRight: !p.extendRight }),
                   className: "accent-accent"
                 }),
                 React.createElement("span", { className: "text-[10px] font-bold text-gray-400 uppercase" }, "Extender Derecha")
               ),
               React.createElement("label", { className: "flex items-center gap-2 cursor-pointer" },
                 React.createElement("input", {
                   type: "checkbox",
                   checked: p.showPrices !== false,
                   onChange: () => updateDrawing(drawing.id, { showPrices: !p.showPrices }),
                   className: "accent-accent"
                 }),
                 React.createElement("span", { className: "text-[10px] font-bold text-gray-400 uppercase" }, "Mostrar Precios")
               )
            )
          )
        ),

        // Modal Footer
        React.createElement("div", { className: "p-4 border-t border-white/5 bg-white/5 flex gap-2" },
          React.createElement("button", {
            onClick: () => setActiveSettingsId(null),
            className: "flex-1 py-2 bg-accent text-black font-bold text-[10px] rounded-lg tracking-widest hover:scale-[1.02] transition-transform"
          }, "ACEPTAR")
        )
      )
    );
  };
  const baseContent = visible ?
  React.createElement("div", { ref: overlayRef, className: "absolute inset-0 z-[15] overflow-hidden",
    style: { pointerEvents: isCreating || dragTarget || (activeTool !== 'cursor' && activeTool !== 'crosshair' && activeTool !== 'ruler') ? 'all' : 'none', background: 'transparent', cursor: activeTool === 'cursor' || activeTool === 'crosshair' ? 'default' : 'crosshair', width: 'calc(100% + 100px)' },
    onMouseDown: handleOverlayMouseDown, onMouseMove: handleOverlayMouseMove, onMouseUp: handleOverlayMouseUp },
  React.createElement("canvas", { ref: canvasRef, className: "w-full h-full pointer-events-none" }),
  toolbar &&
  React.createElement("div", { 
    key: "drawing-toolbar-" + toolbar.id,
    style: { 
      position: 'fixed', 
      left: Math.max(150, Math.min(window.innerWidth - 150, toolbar.x)), 
      top: Math.max(10, toolbar.y), 
      zIndex: 99999, 
      pointerEvents: 'auto',
      transform: 'translateX(-50%)' 
    }, 
    className: "drawing-floating-toolbar flex items-center gap-1 bg-[#111] border border-[#333] rounded-lg p-1.5 shadow-2xl backdrop-blur-lg ring-1 ring-white/10" 
  },
    // Drag handle
    React.createElement("div", { className: "px-2 text-muted cursor-move toolbar-drag-handle" }, 
      React.createElement("i", { className: "fa-solid fa-grip-vertical text-[10px]" })
    ),
    // Color Picker
    React.createElement("div", { className: "flex items-center gap-0.5 border-r border-[#333] pr-1 mr-1" },
      ['#fbbf24', '#ef4444', '#10b981', '#3b82f6', '#ffffff'].map((c) =>
        React.createElement("button", { 
          key: c, 
          className: `w-5 h-5 rounded-md transition-all hover:scale-110 flex items-center justify-center ${toolbar.drawing.props?.color === c ? 'border border-white/50' : ''}`, 
          style: { backgroundColor: c }, 
          onMouseDown: (e) => {e.stopPropagation();updateDrawing(toolbar.id, { color: c });} 
        })
      )
    ),
    // Line Width
    React.createElement("div", { className: "flex items-center gap-1 border-r border-[#333] pr-2 mr-1 text-[11px] text-text px-1" },
      [1, 2, 3, 4].map((w) => 
        React.createElement("button", { 
          key: w, 
          className: `px-1.5 py-0.5 rounded transition-colors hover:bg-white/10 ${ (toolbar.drawing.props?.lineWidth || 1.5) === w ? 'text-accent font-bold' : ''}`,
          onMouseDown: (e) => {e.stopPropagation(); updateDrawing(toolbar.id, { lineWidth: w });}
        }, w + "px")
      )
    ),
    // Clone
    React.createElement("button", { 
      className: "w-8 h-8 flex items-center justify-center hover:bg-white/10 rounded-md text-text transition-colors", 
      title: "Clonar",
      onMouseDown: (e) => {e.stopPropagation(); cloneDrawing(toolbar.id);} 
    }, 
      React.createElement("i", { className: "fa-regular fa-copy" })
    ),
    // Settings (Unified Modal)
    React.createElement("button", { 
      className: "w-8 h-8 flex items-center justify-center hover:bg-white/10 rounded-md text-text transition-colors", 
      title: "Configuración",
      onMouseDown: (e) => {
        e.stopPropagation(); 
        setActiveSettingsId(toolbar.id === activeSettingsId ? null : toolbar.id);
      } 
    }, 
      React.createElement("i", { className: "fa-solid fa-cog" })
    ),
    // Text Label (Legacy, now opens settings)
    React.createElement("button", { 
      className: `w-8 h-8 flex items-center justify-center hover:bg-white/10 rounded-md transition-colors ${toolbar.drawing.props?.text ? 'text-accent' : 'text-text'}`, 
      title: "Add Label",
      onMouseDown: (e) => {
        e.stopPropagation(); 
        setActiveSettingsId(toolbar.id);
      } 
    }, 
      React.createElement("i", { className: "fa-solid fa-font" })
    ),
    // Lock (visual only for now as requested plan mentioned new property)
    React.createElement("button", { 
      className: `w-8 h-8 flex items-center justify-center hover:bg-white/10 rounded-md transition-colors ${toolbar.drawing.props?.locked ? 'text-accent' : 'text-text'}`, 
      title: toolbar.drawing.props?.locked ? "Desbloquear" : "Bloquear",
      onMouseDown: (e) => {e.stopPropagation(); updateDrawing(toolbar.id, { locked: !toolbar.drawing.props?.locked });} 
    }, 
      React.createElement("i", { className: toolbar.drawing.props?.locked ? "fa-solid fa-lock" : "fa-solid fa-lock-open" })
    ),
    // Delete
    React.createElement("button", { 
      className: "w-8 h-8 flex items-center justify-center hover:bg-red-900/30 text-red-400 hover:text-red-300 rounded-md transition-colors", 
      title: "Eliminar",
      onMouseDown: (e) => {e.stopPropagation(); deleteDrawing(toolbar.id); setToolbar(null);} 
    }, 
      React.createElement("i", { className: "fa-regular fa-trash-can" })
    )
    )
  ) : null;

  return React.createElement("div", { id: "drawing-overlay-root-" + chartId, style: { pointerEvents: 'none' } },
    baseContent,
    renderSettingsModal()
  );
};
window.UserDrawingOverlay = UserDrawingOverlay;