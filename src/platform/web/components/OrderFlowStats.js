const OrderFlowStats = ({ symbol, lastPrice, volume }) => {
  const { useState, useEffect, useRef, useMemo, useCallback } = React;
  const [stats, setStats] = useState({
    totalVolume: 0,
    buyVolume: 0,
    sellVolume: 0,
    delta: 0,
    cvd: 0,
    poc: 0,
    deltaPercent: 50
  });
  const volumeProfileRef = useRef(new Map());
  const historyRef = useRef([]);
  const MAX_TICKS = 20000;
  const lastPriceRef = useRef(lastPrice);
  const volumeRef = useRef(volume || 0);
  useEffect(() => {
    if (!lastPrice || volume === undefined || volume === null) return;
    if (lastPriceRef.current === null || volumeRef.current === null) {
      lastPriceRef.current = lastPrice;
      volumeRef.current = volume;
      return;
    }
    const prevPrice = lastPriceRef.current;
    const prevVol = volumeRef.current;
    const priceChange = lastPrice - prevPrice;
    let volumeChange = 0;
    if (volume < prevVol) {
      volumeChange = volume;
    } else {
      volumeChange = volume - prevVol;
    }
    if (volumeChange <= 0 && priceChange === 0) return;
    const isBuy = priceChange > 0 ? true : priceChange < 0 ? false : historyRef.current[historyRef.current.length - 1]?.isBuy ?? true;
    const priceKey = Math.round(lastPrice * 4) / 4;
    const currentLevelVol = (volumeProfileRef.current.get(priceKey) || 0) + volumeChange;
    volumeProfileRef.current.set(priceKey, currentLevelVol);
    historyRef.current.push({ price: priceKey, volume: volumeChange, isBuy });
    if (historyRef.current.length > MAX_TICKS) {
      const removed = historyRef.current.shift();
      const oldLevelVol = volumeProfileRef.current.get(removed.price) || 0;
      if (oldLevelVol - removed.volume <= 0) {
        volumeProfileRef.current.delete(removed.price);
      } else {
        volumeProfileRef.current.set(removed.price, oldLevelVol - removed.volume);
      }
    }
    const shouldUpdatePOC = historyRef.current.length % 5 === 0;
    setStats((prev) => {
      const newBuyVol = prev.buyVolume + (isBuy ? volumeChange : 0);
      const newSellVol = prev.sellVolume + (!isBuy ? volumeChange : 0);
      const newTotalVol = newBuyVol + newSellVol;
      const newDelta = newBuyVol - newSellVol;
      const tickDelta = isBuy ? volumeChange : -volumeChange;
      const newCvd = prev.cvd + tickDelta;
      let poc = prev.poc;
      if (shouldUpdatePOC) {
        let maxVol = 0;
        for (const [price, vol] of volumeProfileRef.current) {
          if (vol > maxVol) {
            maxVol = vol;
            poc = price;
          }
        }
      } else {
        if (currentLevelVol > (volumeProfileRef.current.get(prev.poc) || 0)) {
          poc = priceKey;
        }
      }
      const deltaPercent = newTotalVol > 0 ? newBuyVol / newTotalVol * 100 : 50;
      return {
        totalVolume: newTotalVol,
        buyVolume: newBuyVol,
        sellVolume: newSellVol,
        delta: newDelta,
        cvd: newCvd,
        poc: poc,
        deltaPercent: deltaPercent
      };
    });
    lastPriceRef.current = lastPrice;
    volumeRef.current = volume;
  }, [lastPrice, volume]);
  useEffect(() => {
    setStats({
      totalVolume: 0,
      buyVolume: 0,
      sellVolume: 0,
      delta: 0,
      cvd: 0,
      poc: 0,
      deltaPercent: 50
    });
    historyRef.current = [];
    volumeProfileRef.current.clear();
    lastPriceRef.current = null;
    volumeRef.current = null;
  }, [symbol]);
  useEffect(() => {
    const handleReset = () => {
      setStats({
        totalVolume: 0,
        buyVolume: 0,
        sellVolume: 0,
        delta: 0,
        cvd: 0,
        poc: 0,
        deltaPercent: 50
      });
      historyRef.current = [];
      volumeProfileRef.current.clear();
      lastPriceRef.current = 0;
      volumeRef.current = 0;
    };
    window.addEventListener("frontend_data_reset", handleReset);
    return () => window.removeEventListener("frontend_data_reset", handleReset);
  }, []);
  const formatNumber = (num) => {
    const absNum = Math.abs(num);
    if (absNum >= 1000000) return (num / 1000000).toFixed(1) + 'M';
    if (absNum >= 1000) return (num / 1000).toFixed(1) + 'K';
    if (absNum < 10 && absNum > 0) return num.toFixed(3);
    return num.toFixed(0);
  };
  return (
    React.createElement("div", { className: "flex-1 bg-panel flex flex-col shrink-0 p-2 border-t border-border" },
    React.createElement("h3", { className: "text-[10px] font-bold text-muted uppercase tracking-wider mb-2" }, "Order Flow Stats (", symbol, ")"),
    React.createElement("div", { className: "flex items-center gap-2 mb-1" },
    React.createElement("div", { className: "flex-1 h-2 bg-gray-800 rounded overflow-hidden flex" },
    React.createElement("div", { className: "h-full bg-success transition-all duration-300", style: { width: `${stats.deltaPercent}%` } }),
    React.createElement("div", { className: "h-full bg-danger transition-all duration-300", style: { width: `${100 - stats.deltaPercent}%` } })
    ),
    React.createElement("span", { className: `text-[10px] font-mono font-bold ${stats.delta >= 0 ? 'text-success' : 'text-danger'}` },
    stats.delta >= 0 ? '+' : '', formatNumber(stats.delta)
    )
    ),
    React.createElement("div", { className: "grid grid-cols-2 gap-2 text-[10px] font-mono mt-2 text-muted" },
    React.createElement("div", null, "Vol: ", React.createElement("span", { className: "text-white" }, formatNumber(stats.totalVolume))),
    React.createElement("div", null, "Delta: ", React.createElement("span", { className: stats.delta >= 0 ? 'text-success' : 'text-danger' },
    stats.delta >= 0 ? '+' : '', formatNumber(stats.delta)
    )),
    React.createElement("div", null, "CVD: ", React.createElement("span", { className: stats.cvd >= 0 ? 'text-success' : 'text-danger' },
    stats.cvd >= 0 ? '+' : '', formatNumber(stats.cvd)
    )),
    React.createElement("div", null, "POC: ", React.createElement("span", { className: "text-white" }, stats.poc?.toFixed(2)))
    ),
    React.createElement("div", { className: "flex justify-between text-[9px] font-mono mt-2 text-muted" },
    React.createElement("span", null, "Buy: ", React.createElement("span", { className: "text-success" }, formatNumber(stats.buyVolume))),
    React.createElement("span", null, "Sell: ", React.createElement("span", { className: "text-danger" }, formatNumber(stats.sellVolume)))
    ),
    React.createElement("div", { className: "mt-2 text-[9px] text-center text-muted" },
    lastPrice > stats.poc ?
    React.createElement("span", { className: "text-success" }, "Price above POC (+", (lastPrice - stats.poc).toFixed(2), ")") :
    lastPrice < stats.poc ?
    React.createElement("span", { className: "text-danger" }, "Price below POC (", (lastPrice - stats.poc).toFixed(2), ")") :
    React.createElement("span", { className: "text-accent" }, "Price at POC")
    )
    ));
};
window.OrderFlowStats = OrderFlowStats;