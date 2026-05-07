const { useMemo, useEffect, useState, useRef } = React;
const OrderFlowOverlay = ({ chart, series, data, visible, color = "#3b82f6", width = 2 }) => {
  const [points, setPoints] = useState([]);
  const rafId = useRef(null);
  const lastRangeRef = useRef(null);
  useEffect(() => {
    if (!chart || !series || !data || data.length === 0 || !visible) {
      setPoints([]);
      return;
    }
    const updatePoints = () => {
      if (!chart || !series || !data) return;
      const timeScale = chart.timeScale();
      let visiblePriceRange = null;
      try {
        const pScale = series.priceScale();
        if (pScale && typeof pScale.getVisiblePriceRange === 'function') {
          visiblePriceRange = pScale.getVisiblePriceRange();
        } else {
          const rightScale = chart.priceScale('right');
          if (rightScale && typeof rightScale.getVisiblePriceRange === 'function') {
            visiblePriceRange = rightScale.getVisiblePriceRange();
          }
        }
      } catch (e) {
        console.warn("Could not get visible price range directly", e);
      }
      if (!visiblePriceRange) {
        try {
          const range = chart.priceScale('right').getRange();
          if (range) visiblePriceRange = { from: range.minValue, to: range.maxValue };
        } catch (e) {}
      }
      const visibleLogicalRange = timeScale.getVisibleLogicalRange();
      if (!visiblePriceRange || !visibleLogicalRange) return;
      const visibleData = data.filter((d) => {
        const logical = timeScale.timeToCoordinate(d.time);
        return true;
      });
      if (visibleData.length === 0) return;
      const deltas = data.map((d) => d.value);
      const minD = Math.min(...deltas);
      const maxD = Math.max(...deltas);
      const dRange = maxD - minD || 1;
      const minP = visiblePriceRange.from;
      const maxP = visiblePriceRange.to;
      const pRange = maxP - minP || 1;
      const midP = (minP + maxP) / 2;
      const midD = (minD + maxD) / 2;
      const factor = pRange / dRange * 0.4;
      const newPoints = data.map((d) => {
        const x = timeScale.timeToCoordinate(d.time);
        if (x === null) return null;
        const valAsPrice = midP + (d.value - midD) * factor;
        const y = series.priceToCoordinate(valAsPrice);
        return { x, y };
      }).filter((p) => p !== null && p.x !== null && p.y !== null);
      setPoints(newPoints);
    };
    const onRangeChange = () => {
      const range = chart.timeScale().getVisibleLogicalRange();
      if (lastRangeRef.current &&
      Math.abs(lastRangeRef.current.from - range.from) < 0.01 &&
      Math.abs(lastRangeRef.current.to - range.to) < 0.01) {
        return;
      }
      lastRangeRef.current = range;
      if (rafId.current) cancelAnimationFrame(rafId.current);
      rafId.current = requestAnimationFrame(updatePoints);
    };
    chart.timeScale().subscribeVisibleLogicalRangeChange(onRangeChange);
    const interval = setInterval(updatePoints, 100);
    updatePoints();
    return () => {
      chart.timeScale().unsubscribeVisibleLogicalRangeChange(onRangeChange);
      if (rafId.current) cancelAnimationFrame(rafId.current);
      clearInterval(interval);
    };
  }, [chart, series, data, visible]);
  if (!visible || points.length < 2) return null;
  const pathData = points.reduce((acc, p, i) => {
    return acc + (i === 0 ? `M ${p.x} ${p.y}` : ` L ${p.x} ${p.y}`);
  }, "");
  return (
    React.createElement("div", { style: {
        position: 'absolute',
        top: 0,
        left: 0,
        width: '100%',
        height: '100%',
        pointerEvents: 'none',
        zIndex: 5,
        overflow: 'hidden'
      } },
    React.createElement("svg", {
      width: "100%",
      height: "100%",
      style: { overflow: 'visible' } },
    React.createElement("path", {
      d: pathData,
      fill: "none",
      stroke: color,
      strokeWidth: width,
      strokeLinejoin: "round",
      strokeLinecap: "round",
      style: {
        opacity: 0.8,
        transition: 'none'
      } }
    )
    )
    ));
};
window.OrderFlowOverlay = OrderFlowOverlay;