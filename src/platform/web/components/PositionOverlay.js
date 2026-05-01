const PositionOverlay = ({
  chart, series, status, activeSymbol,
  mt5Positions = [], mt5PendingOrders = [], visible = true,
  tickData
}) => {
  const { useState, useEffect, useRef, useCallback } = React;
  const [positions, setPositions] = useState([]);
  const [dragItem, setDragItem] = useState(null);
  const overlayRef = useRef(null);
  const animFrameRef = useRef(null);
  const dragItemRef = useRef(null);
  const [displayMode, setDisplayMode] = useState("USD");
  const [axisWidth, setAxisWidth] = useState(72);
  const [badgeWidths, setBadgeWidths] = useState({});
  const badgeGroupRefs = useRef({});
  const [ghost, setGhost] = useState(null);
  let addNotification = () => {};
  try {const n = useNotification();addNotification = n.addNotification;} catch (_) {}
  useEffect(() => {
    if (!chart) return;
    const measure = () => {
      try {
        const chartEl = chart.chartElement ? chart.chartElement() : overlayRef.current?.parentElement;
        if (!chartEl) return;
        const candidates = [
        chartEl.querySelector('td:last-child canvas'),
        chartEl.querySelector('[class*="price-axis"]'),
        chartEl.querySelector('[class*="priceAxis"]'),
        chartEl.querySelector('td:last-child')];
        for (const el of candidates) {
          if (!el) continue;
          const w = el.getBoundingClientRect().width;
          if (w > 10) {setAxisWidth(Math.ceil(w));return;}
        }
      } catch (_) {}
    };
    measure();
    const t1 = setTimeout(measure, 300);
    const t2 = setTimeout(measure, 1000);
    return () => {clearTimeout(t1);clearTimeout(t2);};
  }, [chart]);
  const getPointValue = (pos, sym) => {
    if (pos?.point_value > 0) return pos.point_value;
    if (pos?.tick_value > 0 && pos?.tick_size > 0)
    return pos.tick_value / pos.tick_size;
    if (pos?.tick_value > 0) return pos.tick_value;
    const s = (sym || pos?.symbol || activeSymbol || "").toUpperCase();
    if (s === "NQ" || s === "NQ1!" || s === "NQUSDT") return 20;
    if (s === "MNQ" || s.startsWith("MNQ")) return 2;
    if (s === "ES" || s === "ES1!") return 50;
    if (s === "MES" || s.startsWith("MES")) return 5;
    if (s === "RTY" || s.startsWith("RTY")) return 50;
    if (s === "YM" || s.startsWith("YM")) return 5;
    if (s.includes("CL") || s.includes("OIL")) return 1000;
    if (s.includes("JPY")) return 1000;
    if (s.includes("BTC") || s.includes("ETH")) return 1;
    return 1;
  };
  const getPrecision = useCallback((sym) => {
    if (window.getSymbolPrecision) return window.getSymbolPrecision(sym || activeSymbol || "").digits ?? 2;
    return 2;
  }, [activeSymbol]);
  const toggleDisplayMode = useCallback((e) => {
    e.stopPropagation();
    setDisplayMode((prev) => prev === "USD" ? "POINTS" : prev === "POINTS" ? "PRICE" : "USD");
  }, []);
  useEffect(() => {dragItemRef.current = dragItem;}, [dragItem]);
  useEffect(() => {
    if (!chart || !series) {setPositions([]);return;}
    const updatePos = () => {
      if (dragItemRef.current) {
        animFrameRef.current = requestAnimationFrame(updatePos);
        return;
      }
      const items = [];
      mt5Positions.forEach((pos) => {
        if (activeSymbol && activeSymbol.split(":")[0] !== (pos.symbol || "").split(":")[0]) return;
        const entryY = series.priceToCoordinate(pos.entry_price);
        const slY = pos.sl > 0 ? series.priceToCoordinate(pos.sl) : null;
        const tpY = pos.tp > 0 ? series.priceToCoordinate(pos.tp) : null;
        const isBuy = pos.type === "BUY";
        const posColor = isBuy ? "#2962FF" : "#FF6D00";
        if (entryY !== null) {
          const pv = getPointValue(pos, pos.symbol);
          const currentPx = pos.current_price || tickData?.last || pos.entry_price;
          items.push({
            type: isBuy ? "LONG" : "SHORT",
            id: `entry-${pos.ticket}`,
            price: pos.entry_price, y: entryY, color: posColor,
            editable: true, isEntry: true,
            ticket: pos.ticket, volume: pos.volume,
            profitUSD: pos.profit ?? (isBuy ? currentPx - pos.entry_price : pos.entry_price - currentPx) * pv * pos.volume,
            profitPts: isBuy ? currentPx - pos.entry_price : pos.entry_price - currentPx,
            hasSL: pos.sl > 0, hasTP: pos.tp > 0,
            sl: pos.sl, tp: pos.tp,
            entry_price: pos.entry_price, pos_type: pos.type,
            symbol: pos.symbol, pointValue: pv
          });
        }
        if (slY !== null) {
          const pv = getPointValue(pos, pos.symbol);
          const slPts = isBuy ? pos.sl - pos.entry_price : pos.entry_price - pos.sl;
          items.push({
            type: "SL", id: `sl-${pos.ticket}`, price: pos.sl, y: slY, color: "#F23645",
            editable: true, ticket: pos.ticket, volume: pos.volume,
            profitPts: slPts,
            profitUSD: slPts * pv * pos.volume,
            symbol: pos.symbol
          });
        }
        if (tpY !== null) {
          const pv = getPointValue(pos, pos.symbol);
          const tpPts = isBuy ? pos.tp - pos.entry_price : pos.entry_price - pos.tp;
          items.push({
            type: "TP", id: `tp-${pos.ticket}`, price: pos.tp, y: tpY, color: "#089981",
            editable: true, ticket: pos.ticket, volume: pos.volume,
            profitPts: tpPts,
            profitUSD: tpPts * pv * pos.volume,
            symbol: pos.symbol
          });
        }
      });
      mt5PendingOrders.forEach((o) => {
        if (activeSymbol && activeSymbol.split(":")[0] !== (o.symbol || "").split(":")[0]) return;
        const orderPrice = o.price || o.price_open || 0;
        const priceY = series.priceToCoordinate(orderPrice);
        if (priceY === null) return;
        const typeCode = String(o.type ?? "").toUpperCase();
        const side = (o.side || "buy").toLowerCase();
        const isBuy = side === "buy";
        let label, color;
        if (typeCode === "PENDING_BUY_STP" || typeCode === "PENDING_SELL_STP") {
          label = isBuy ? "BUY STP" : "SELL STP";
          color = isBuy ? "#2962FF" : "#FF6D00";
        } else {
          label = isBuy ? "BUY LMT" : "SELL LMT";
          color = isBuy ? "#2962FF" : "#FF6D00";
        }
        const vol = o.volume_current || o.volume || 0;
        const pv = getPointValue(o, o.symbol);
        const sym0 = (o.symbol || "").split(":")[0];
        const relatedPos = mt5Positions.find((p) =>
        (p.symbol || "").split(":")[0] === sym0
        );
        let distPts;
        if (relatedPos) {
          const ep = relatedPos.entry_price;
          const posIsBuy = relatedPos.type === "BUY";
          if (isBuy) {
            distPts = ep - orderPrice;
          } else {
            distPts = orderPrice - ep;
          }
        } else {
          const livePrice = tickData?.last || tickData?.bid || tickData?.ask || status?.current_price || status?.price || orderPrice;
          distPts = isBuy ? livePrice - orderPrice : orderPrice - livePrice;
        }
        items.push({
          type: typeCode, id: `pending-${o.ticket}`, label, price: orderPrice, y: priceY,
          color, editable: true, ticket: o.ticket,
          volume: vol,
          profitUSD: distPts * pv * vol,
          profitPts: distPts,
          symbol: o.symbol
        });
      });
      if (overlayRef.current) {
        items.forEach((item) => {
          const el = overlayRef.current.querySelector(`[data-pos-id="${item.id}"]`);
          if (el) {
            el.style.top = `${item.y}px`;
          }
        });
      }
      const dataOnlyForCompare = items.map((it) => ({ ...it, y: 0 }));
      const newState = JSON.stringify(dataOnlyForCompare);
      if (overlayRef.current && overlayRef.current.__lastDataState !== newState) {
        overlayRef.current.__lastDataState = newState;
        setPositions(items);
      }
    };
    const animate = () => {
      updatePos();
      animFrameRef.current = requestAnimationFrame(animate);
    };

    animate();

    return () => {
      if (animFrameRef.current) cancelAnimationFrame(animFrameRef.current);
    };
  }, [chart, series, mt5Positions, mt5PendingOrders, activeSymbol, displayMode, tickData]);
  useEffect(() => {
    if (!overlayRef.current || positions.length === 0) return;
    const timer = setTimeout(() => {
      const next = {};
      const groups = overlayRef.current.querySelectorAll('.ats-pos-group');
      groups.forEach((el) => {
        const id = el.dataset.posId;
        if (id) {
          const w = el.getBoundingClientRect().width;
          if (w > 0) next[id] = Math.ceil(w);
        }
      });
      if (Object.keys(next).length > 0) {
        setBadgeWidths((prev) => {
          const changed = Object.keys(next).some((k) => prev[k] !== next[k]);
          return changed ? { ...prev, ...next } : prev;
        });
      }
    }, 50);
    return () => clearTimeout(timer);
  }, [positions.length]);
  useEffect(() => {
    if (!dragItem) return;
    const onMove = (e) => {
      if (!overlayRef.current || !series) return;
      if (animFrameRef.current) cancelAnimationFrame(animFrameRef.current);
      animFrameRef.current = requestAnimationFrame(() => {
        const cur = dragItemRef.current;
        if (!cur) return;
        const rect = overlayRef.current.getBoundingClientRect();
        const newY = e.clientY - rect.top;
        const newPrice = series.coordinateToPrice(newY);
        if (newPrice == null) return;
        try {
          const range = series.priceScale().getVisiblePriceRange();
          if (range && (newPrice < range.minValue || newPrice > range.maxValue)) return;
        } catch (_) {}
        dragItemRef.current = { ...cur, currentPrice: newPrice, currentY: newY };
        if (cur.isEntry) {
          const isBuy = cur.pos_type === "BUY";
          const isAboveEntry = newPrice > cur.originalPrice;
          const kind = (isBuy ? isAboveEntry : !isAboveEntry) ? "TP" : "SL";
          const color = kind === "TP" ? "#089981" : "#F23645";
          setGhost({ y: newY, price: newPrice, kind, color });
          setDragItem((prev) => prev ? { ...prev, currentPrice: newPrice, currentY: newY, ghostKind: kind } : null);
        } else {
          setDragItem((prev) => prev ? { ...prev, currentPrice: newPrice, currentY: newY } : null);
          setPositions((prev) => prev.map((p) =>
          p.ticket === cur.ticket && p.type === cur.type ? { ...p, price: newPrice, y: newY } : p
          ));
        }
      });
    };
    const onUp = async () => {
      if (animFrameRef.current) cancelAnimationFrame(animFrameRef.current);
      const snap = dragItemRef.current;
      setDragItem(null);
      dragItemRef.current = null;
      setGhost(null);
      if (!snap?.currentPrice) return;
      const { ticket, type, currentPrice, originalPrice, isEntry, ghostKind, pos_type, symbol: itemSymbol } = snap;
      const prec = getPrecision(activeSymbol);
      const platform = status?.platform || "mt5";
      if (isEntry) {
        if (Math.abs(currentPrice - originalPrice) < 0.00001) return;
        const which = ghostKind;
        const payload = {
          platform,
          symbol: itemSymbol || activeSymbol,
          ticket,
          sl: snap.sl || 0,
          tp: snap.tp || 0,
          order_type: "MKT"
        };
        if (which === "SL") payload.sl = currentPrice;else
        payload.tp = currentPrice;
        try {
          const res = await fetch("/api/modify", {
            method: "POST", headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload)
          });
          const data = await res.json();
          if (data.status === "success" || data.status === "modified") {
          } else {
            addNotification("error", "Failed", data.message || data.detail || `Cannot set ${which}`);
          }
        } catch (err) {
          addNotification("error", "Error", err.message);
        }
        return;
      }
      if (Math.abs(currentPrice - originalPrice) < 0.00001) return;
      const payload = {
        platform,
        symbol: itemSymbol || activeSymbol,
        ticket,
        order_type: type.startsWith("PENDING_") ? type.replace("PENDING_", "") : "MKT"
      };
      if (type === "SL") payload.sl = currentPrice;else
      if (type === "TP") payload.tp = currentPrice;else
      if (type.startsWith("PENDING_")) {
        payload.price = currentPrice;
        payload.is_pending = true;
      }
      // Add SL/TP to payload if they exist in the snap
      if (snap.sl) payload.sl = snap.sl;
      if (snap.tp) payload.tp = snap.tp;
      try {
        const res = await fetch("/api/modify", {
          method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload)
        });
        const data = await res.json();
        if (data.status !== "success" && data.status !== "modified") {
          addNotification("error", "Failed", data.message || data.detail || `Cannot update ${type}`);
          setPositions((prev) => prev.map((p) => p.ticket === ticket && p.type === type ?
          { ...p, price: originalPrice, y: series.priceToCoordinate(originalPrice) } : p));
        }
      } catch (err) {
        addNotification("error", "Error", err.message);
        setPositions((prev) => prev.map((p) => p.ticket === ticket && p.type === type ?
        { ...p, price: originalPrice, y: series.priceToCoordinate(originalPrice) } : p));
      }
    };
    document.addEventListener("mousemove", onMove, { passive: true });
    document.addEventListener("mouseup", onUp);
    return () => {
      document.removeEventListener("mousemove", onMove);
      document.removeEventListener("mouseup", onUp);
      if (animFrameRef.current) cancelAnimationFrame(animFrameRef.current);
    };
  }, [dragItem, series, activeSymbol, status]);
  const modifyVolume = useCallback(async (e, p, delta) => {
    e.stopPropagation();e.preventDefault();
    const platform = status?.platform || "mt5";
    const newVol = Math.max(0, (parseFloat(p.volume) || 0) + delta);
    const action = newVol === 0 || delta < 0 ? "CLOSE" : "OPEN";
    const vol = newVol === 0 ? p.volume : Math.abs(delta);
    try {
      const res = await fetch("/api/order", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ platform, action, symbol: activeSymbol || p.symbol, volume: vol, ticket: p.ticket, type: p.type, account_id: status?.selected_account_id || null })
      });
      const data = await res.json();
      if (data.status !== "executed" && data.status !== "success" && data.status !== "modified")
      addNotification("error", "Failed", data.detail || data.message || "Cannot modify");
    } catch (err) {addNotification("error", "Error", err.message);}
  }, [status, activeSymbol]);
  const handleClose = useCallback(async (e, p) => {
    e.stopPropagation();e.preventDefault();
    const platform = status?.platform || "mt5";
    const isPending = p.type === "PENDING_BUY" || p.type === "PENDING_SELL";
    if (p.type === "SL" || p.type === "TP") {
      const payload = { platform, symbol: activeSymbol || p.symbol, ticket: p.ticket };
      if (p.type === "SL") payload.sl = 0;else payload.tp = 0;
      try {
        const res = await fetch("/api/modify", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) });
        const data = await res.json();
        if (data.status !== "success" && data.status !== "modified")
        addNotification("error", "Failed", data.message);
      } catch (err) {addNotification("error", "Error", err.message);}
      return;
    }
    try {
      const res = await fetch("/api/order", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ platform, action: "CLOSE", symbol: activeSymbol || p.symbol, volume: p.volume || 0, ticket: p.ticket, account_id: status?.selected_account_id || null })
      });
      const data = await res.json();
      if (data.status !== "executed" && data.status !== "cancelled")
      addNotification("error", "Failed", data.detail || "Cannot close");
    } catch (err) {addNotification("error", "Error", err.message);}
  }, [status, activeSymbol]);
  const addSlTp = useCallback(async (e, p, which) => {
    e.stopPropagation();e.preventDefault();
    const platform = status?.platform || "mt5";
    const prec = getPrecision(activeSymbol);
    const isBuy = p.pos_type === "BUY";
    const defaultDist = Math.pow(10, -prec) * 100;
    const payload = { platform, symbol: activeSymbol, ticket: p.ticket, sl: p.sl || 0, tp: p.tp || 0 };
    if (which === "SL") payload.sl = isBuy ? p.entry_price - defaultDist : p.entry_price + defaultDist;
    if (which === "TP") payload.tp = isBuy ? p.entry_price + defaultDist : p.entry_price - defaultDist;
    try {
      const res = await fetch("/api/modify", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) });
      const data = await res.json();
      if (data.status !== "success" && data.status !== "modified")
      addNotification("error", "Failed", data.message);
    } catch (err) {addNotification("error", "Error", err.message);}
  }, [status, activeSymbol]);
  if (!visible) return null;
  const BADGE_RIGHT = axisWidth + 4;
  return (
    React.createElement("div", { ref: overlayRef, style: { position: "absolute", inset: 0, pointerEvents: "none", overflow: "hidden", zIndex: 100 } },
    ghost &&
    React.createElement("div", { style: {
        position: "absolute",
        top: ghost.y,
        left: 0,
        right: axisWidth,
        height: 0,
        transform: "translateY(-50%)",
        borderTop: `1px solid ${ghost.color}88`,
        opacity: 0.9,
        pointerEvents: "none",
        zIndex: 24,
        transition: "none"
      } },
    React.createElement("div", { style: {
        position: "absolute", right: -axisWidth, top: "50%", transform: "translateY(-50%)",
        width: axisWidth, height: 18, background: ghost.color,
        display: "flex", alignItems: "center", justifyContent: "center",
        fontFamily: "'JetBrains Mono','Roboto Mono',monospace",
        fontSize: 11, fontWeight: 700, color: "#fff",
        pointerEvents: "none"
      } },
    ghost.price.toFixed(getPrecision(activeSymbol))
    ),
    React.createElement("div", { style: {
        position: "absolute", right: BADGE_RIGHT, top: "50%", transform: "translateY(-50%)",
        height: 20, padding: "0 10px",
        background: ghost.color + "33",
        border: `1.5px dashed ${ghost.color}`,
        borderRadius: 2,
        color: ghost.color,
        fontFamily: "'JetBrains Mono','Roboto Mono',monospace",
        fontSize: 11, fontWeight: 700,
        display: "flex", alignItems: "center",
        pointerEvents: "none"
      } },
    ghost.kind === "SL" ? "Set SL" : "Set TP"
    )
    ),
    positions.map((p, i) => {
      const isDragging = dragItem?.ticket === p.ticket && dragItem?.type === p.type;
      const isEntryDragging = isDragging && p.isEntry;
      const isPending = p.type.startsWith("PENDING_");
      const isEntry = p.type === "LONG" || p.type === "SHORT";
      const isSL = p.type === "SL";
      const isTP = p.type === "TP";
      const prec = getPrecision(activeSymbol || p.symbol);
      const pnlUSD = p.profitUSD || 0;
      const pnlPts = p.profitPts || 0;
      const pnlPos = pnlUSD >= 0;
      const pnlText = displayMode === "USD" ?
      `$${pnlPos ? "+" : ""}${pnlUSD.toFixed(2)}` :
      displayMode === "POINTS" ?
      `${pnlPts >= 0 ? "+" : ""}${pnlPts.toFixed(prec)}pts` :
      p.price.toFixed(prec);
      const labelText = (() => {
        if (p.label) return p.label;
        if (p.type === "SL") return p.pos_type === "BUY" ? "SELL STP" : "BUY STP";
        if (p.type === "TP") return p.pos_type === "BUY" ? "SELL LMT" : "BUY LMT";
        return {
          LONG: "Buy (long)", SHORT: "Sell (short)",
          PENDING_BUY: "BUY LMT", PENDING_SELL: "SELL LMT",
          PENDING_BUY_STP: "BUY STP", PENDING_SELL_STP: "SELL STP"
        }[p.type] || p.type;
      })();
      const lineColor = p.color + '8C';
      const lineBorder = `0.5px solid ${lineColor}`;
      const badgeW = badgeWidths[p.id] || 0;
      const lineRight = BADGE_RIGHT + (badgeW > 0 ? badgeW + 2 : 180);
      const BTN_BASE = {
        height: 20, border: "none", borderLeft: "1px solid #2a2a2a",
        fontFamily: "'JetBrains Mono','Roboto Mono',monospace",
        fontSize: 11, fontWeight: 700, cursor: "pointer",
        display: "flex", alignItems: "center", padding: "0 6px",
        whiteSpace: "nowrap", flexShrink: 0
      };
      return (
        React.createElement("div", {
          key: `${p.ticket}-${p.type}-${i}`,
          "data-pos-id": p.id,
          style: {
            position: "absolute", top: p.y, left: 0, right: 0, height: 0,
            transform: "translateY(-50%)", pointerEvents: "none"
          } },
        !isEntry &&
        React.createElement("div", { style: {
            position: "absolute", left: 0, right: lineRight, top: 0, height: 0,
            borderTop: lineBorder,
            opacity: isDragging ? 1 : 1,
            pointerEvents: "none"
          } }),
        React.createElement("div", { style: {
            position: "absolute", right: 0, top: "50%", transform: "translateY(-50%)",
            width: axisWidth, height: 18, background: p.color,
            display: "flex", alignItems: "center", justifyContent: "center",
            fontFamily: "'JetBrains Mono','Roboto Mono',monospace",
            fontSize: 11, fontWeight: 700, color: "#fff", letterSpacing: "0.3px",
            pointerEvents: "none", zIndex: 28,
            opacity: isEntryDragging ? 0.4 : 1,
            boxShadow: isDragging && !isEntryDragging ? `0 0 8px ${p.color}99` : "none"
          } },
        p.price.toFixed(prec)
        ),
        React.createElement("div", {
          className: "ats-pos-group",
          "data-pos-id": p.id,
          style: {
            position: "absolute",
            right: BADGE_RIGHT,
            top: "50%", transform: "translateY(-50%)",
            display: "flex", alignItems: "center", gap: 0,
            pointerEvents: "auto",
            cursor: p.editable ? isDragging ? "grabbing" : "ns-resize" : "default",
            zIndex: 30, userSelect: "none",
            opacity: isEntryDragging ? 0.4 : 1
          },
          onMouseDown: (e) => {
            if (e.target.tagName === "BUTTON" || e.target.closest?.("button")) return;
            if (!p.editable) return;
            e.stopPropagation();e.preventDefault();
            const item = {
              ticket: p.ticket,
              type: p.type,
              symbol: p.symbol,
              originalPrice: p.price,
              currentPrice: p.price,
              currentY: p.y,
              isEntry: !!p.isEntry,
              pos_type: p.pos_type,
              sl: p.sl || 0,
              tp: p.tp || 0
            };
            dragItemRef.current = item;
            setDragItem(item);
          },
          onDoubleClick: toggleDisplayMode },
        React.createElement("button", {
          className: "ats-close-btn",
          onClick: (e) => handleClose(e, p),
          onMouseDown: (e) => e.stopPropagation(),
          title: isSL || isTP ? `Remove ${p.type}` : `Close #${p.ticket}`,
          style: {
            ...BTN_BASE, width: 18, padding: 0,
            background: "#c0392b", borderLeft: "none",
            borderRadius: "2px 0 0 2px",
            color: "#fff", fontSize: 13, justifyContent: "center"
          } },
        "\xD7"),
        isEntry ?
        React.createElement(React.Fragment, null,
        React.createElement("button", { onMouseDown: (e) => e.stopPropagation(), onClick: (e) => modifyVolume(e, p, -1),
          title: "Remove 1 contract",
          style: { ...BTN_BASE, background: "#1e1e1e", color: "#fff", gap: 4, padding: "0 8px" } },
        React.createElement("span", { style: { color: "#666", fontSize: 12 } }, "\u2212"),
        React.createElement("span", null, p.volume)
        ),
        React.createElement("div", { onClick: toggleDisplayMode, style: { ...BTN_BASE, cursor: "pointer", padding: "0 8px", background: pnlPos ? "#162a1e" : "#2a1616", color: pnlPos ? "#4caf82" : "#ef5350" } },
        displayMode === "USD" ? `$${pnlPos ? "+" : ""}${pnlUSD.toFixed(2)}` :
        displayMode === "POINTS" ? `${pnlPts >= 0 ? "+" : ""}${pnlPts.toFixed(prec)}pts` :
        p.price.toFixed(prec)
        ),
        React.createElement("button", { onMouseDown: (e) => e.stopPropagation(), onClick: (e) => !p.hasSL && addSlTp(e, p, "SL"),
          title: p.hasSL ? `SL @ ${(p.sl || 0).toFixed(prec)}` : "Drag line or click to add SL",
          style: { ...BTN_BASE, background: p.hasSL ? "#2a1212" : "#1e1e1e", color: p.hasSL ? "#F23645" : "#555" } }, "SL"),
        React.createElement("button", { onMouseDown: (e) => e.stopPropagation(), onClick: (e) => !p.hasTP && addSlTp(e, p, "TP"),
          title: p.hasTP ? `TP @ ${(p.tp || 0).toFixed(prec)}` : "Drag line or click to add TP",
          style: { ...BTN_BASE, background: p.hasTP ? "#0d2318" : "#1e1e1e", color: p.hasTP ? "#089981" : "#555", borderRadius: "0 2px 2px 0" } }, "TP")
        ) :
        React.createElement(React.Fragment, null,
        React.createElement("div", { style: {
            ...BTN_BASE, cursor: p.editable ? "ns-resize" : "default",
            background: p.color + "20", borderLeft: `2px solid ${p.color}`,
            color: p.color, gap: 5, padding: "0 8px",
            boxShadow: isDragging ? `0 0 8px ${p.color}55` : "none",
            transform: isDragging ? "scaleY(1.08)" : "scaleY(1)",
            transition: "transform 0.1s, box-shadow 0.1s"
          } },
        isPending && React.createElement("span", { style: { color: "#ccc" } }, p.volume),
        React.createElement("span", null, labelText),
        isPending &&
        React.createElement("span", { style: { fontSize: 9, color: "#666", border: "1px solid #444", borderRadius: 2, padding: "0 3px" } }, "A/C"),
        p.editable &&
        React.createElement("span", { style: { color: isDragging ? p.color : "rgba(255,255,255,0.2)", fontSize: 9 } }, "\u21C5")
        ),
        (isSL || isTP || isPending) &&
        React.createElement("div", { onClick: toggleDisplayMode, style: {
            ...BTN_BASE, cursor: "pointer", padding: "0 8px",
            background: isSL ? "#2a1212" : isTP ? "#0d2318" : "#1e1e1e",
            color: isSL ? "#F23645" : isTP ? "#089981" : pnlPos ? "#4caf82" : "#ef5350",
            borderRadius: "0 2px 2px 0"
          } }, pnlText),
        isPending &&
        React.createElement("div", { style: { ...BTN_BASE, background: "#1e1e1e", color: "#888", borderRadius: "0 2px 2px 0", padding: "0 8px" } },
        p.price.toFixed(prec)
        )
        )
        )
        ));
    }),
    React.createElement("style", null, `
        .ats-close-btn:hover { background: #e74c3c !important; }
      `)
    ));
};
window.PositionOverlay = PositionOverlay;