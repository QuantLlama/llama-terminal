const { useMemo, useEffect, useState, useRef } = React;
const OrderFlowOverlay = ({ chart, series, data, visible, color = "#3b82f6", width = 2 }) => {
  const pathRef = useRef(null);
  useEffect(() => {
    if (!chart || !series || !data || data.length === 0 || !visible) {
      if (pathRef.current) pathRef.current.setAttribute('d', '');
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
      const newPathData = newPoints.reduce((acc, p, i) => {
        return acc + (i === 0 ? `M ${p.x} ${p.y}` : ` L ${p.x} ${p.y}`);
      }, "");
      if (pathRef.current) {
        pathRef.current.setAttribute('d', newPathData);
      }
    };
        let _isDrawing = false;
        let _needsRedraw = false;
        const onRangeChange = () => {
            if (_isDrawing) {
                _needsRedraw = true;
                return;
            }
            _isDrawing = true;
            try { updatePoints(); } catch(e) {}
            requestAnimationFrame(() => {
                _isDrawing = false;
                if (_needsRedraw) {
                    _needsRedraw = false;
                    onRangeChange();
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
                        onRangeChange();
                    }
                } catch(e) {}
            }
            _monitorRaf = requestAnimationFrame(monitorScale);
        };
        _monitorRaf = requestAnimationFrame(monitorScale);
        
    chart.timeScale().subscribeVisibleLogicalRangeChange(onRangeChange);
    chart.timeScale().subscribeVisibleTimeRangeChange(onRangeChange);
    chart.subscribeCrosshairMove(onRangeChange);
    updatePoints();
    return () => {
      chart.timeScale().unsubscribeVisibleLogicalRangeChange(onRangeChange);
      chart.timeScale().unsubscribeVisibleTimeRangeChange(onRangeChange);
      chart.unsubscribeCrosshairMove(onRangeChange);
      if (_monitorRaf) cancelAnimationFrame(_monitorRaf);
    };
  }, [chart, series, data, visible]);
  if (!visible) return null;
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
      ref: pathRef,
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