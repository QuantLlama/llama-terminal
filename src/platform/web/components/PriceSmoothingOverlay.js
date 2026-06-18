(function () {
  const { useEffect, useRef, useState } = React;
  const PriceSmoothingOverlay = React.memo(({
    chart,
    series,
    lastPrice,
    symbol,
    precision = 2,
    enabled = true
  }) => {
    const targetPriceRef = useRef(lastPrice);
    const rafRef = useRef(null);
    useEffect(() => {
      if (lastPrice !== undefined && lastPrice !== null) {
        targetPriceRef.current = lastPrice;
      }
    }, [lastPrice]);
    useEffect(() => {
      if (!enabled || !chart || !lastPrice) return;
      try {
        if (!window.smoothedPrices) window.smoothedPrices = {};
        window.smoothedPrices[symbol] = targetPriceRef.current;
      } catch (e) {}
      return () => {
        if (rafRef.current) cancelAnimationFrame(rafRef.current);
      };
    }, [enabled, chart, symbol, lastPrice]);
    return null;
  });
  window.PriceSmoothingOverlay = PriceSmoothingOverlay;
})();