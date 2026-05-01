const useTradeStream = (
symbol,
lastPrice,
volume,
timestamp,
onTrade,
isCumulative = false,
providedSide = null,
aggregationMs = 100,
streamId = "default") =>
{
  const { useEffect, useRef } = React;
  const prevVol = useRef(null);
  const prevPrice = useRef(null);
  const prevTime = useRef(null);
  const lastSideRef = useRef('buy');
  const formatTime = (ts) => {
    if (!ts) return "--:--:--";
    const dateObj = new Date(ts < 1e10 ? ts * 1000 : ts);
    const h = String(dateObj.getHours()).padStart(2, '0');
    const m = String(dateObj.getMinutes()).padStart(2, '0');
    const s = String(dateObj.getSeconds()).padStart(2, '0');
    const ms = String(dateObj.getMilliseconds()).padStart(3, '0');
    return `${h}:${m}:${s}.${ms}`;
  };
  const bufferRef = useRef({
    price: null,
    side: null,
    size: 0,
    totalVolume: 0,
    firstTime: 0,
    firstTimeFormatted: null,
    count: 0
  });
  const wsActive = useRef(false);
  const wsTimer = useRef(null);
  const flushTimer = useRef(null);
  const lastProcessedKey = useRef("");
  useEffect(() => {
    prevVol.current = null;
    prevPrice.current = null;
    prevTime.current = null;
    bufferRef.current = { price: null, side: null, size: 0, totalVolume: 0, firstTime: 0, firstTimeFormatted: null, count: 0 };
    wsActive.current = false;
    lastProcessedKey.current = "";
    if (wsTimer.current) clearTimeout(wsTimer.current);
    if (flushTimer.current) clearTimeout(flushTimer.current);
  }, [symbol]);
  const flushBuffer = useRef(() => {
    const b = bufferRef.current;
    if (b.size > 0 && b.price !== null) {
      onTrade({
        id: Date.now() + Math.random(),
        price: b.price,
        size: b.size,
        side: b.side,
        time: b.firstTimeFormatted || b.firstTime,
        timestamp: b.firstTime,
        volume: b.totalVolume,
        count: b.count
      });
      b.size = 0;
      b.count = 0;
      b.price = null;
    }
  }).current;
  useEffect(() => {
    const handleMarketTick = (e) => {
      const detail = e.detail || {};
      if (!detail.symbol) return;
      
      // Try multiple symbol variations for matching
      const rawSymbol = detail.symbol;
      const detSym = window.getUniversalSymbol ? window.getUniversalSymbol(rawSymbol) : rawSymbol;
      const detSymUpper = detSym.toUpperCase();
      
      const targetRaw = symbol;
      const targetSym = window.getUniversalSymbol ? window.getUniversalSymbol(targetRaw) : targetRaw;
      const targetSymUpper = targetSym.toUpperCase();
      
      // Match if normalized symbols match OR raw symbols match (case insensitive)
      const symbolMatch = (
        detSym === targetSym || 
        detSymUpper === targetSymUpper ||
        rawSymbol.toUpperCase() === targetRaw.toUpperCase()
      );
      
      if (!symbolMatch) return;
      const eventType = detail.eventType || "";
      // Accept TICK, TRADE, TAPE, QUOTE events for the tape display
      // QUOTE is dispatched by App.jsx for crypto TICK events
      // TAPE is used for crypto trades with size, TRADE for MT5
      if (eventType && !["TICK", "TRADE", "TAPE", "QUOTE", "trade", "tick", "tape", "quote"].includes(eventType)) return;
      const px = Number(detail.price) || 0;
      // FIX: For crypto, prefer size but fall back to last_size then volume
      const tradeSize = Number(detail.size) > 0 ? Number(detail.size) :
      Number(detail.last_size) > 0 ? Number(detail.last_size) :
      Number(detail.volume) > 0 ? Number(detail.volume) :
      0;
      const tickTime = Number(detail.timestamp) || 0;
      const tickVol = Number(detail.volume) || 0;
      if (!px || tradeSize <= 0 || !tickTime) return;
      const tickKey = `${tickTime}_${px}_${tradeSize}`;
      if (lastProcessedKey.current === tickKey) return;
      lastProcessedKey.current = tickKey;
      wsActive.current = true;
      if (wsTimer.current) clearTimeout(wsTimer.current);
      wsTimer.current = setTimeout(() => {wsActive.current = false;}, 3000);
      const sideUp = (detail.side || "").toUpperCase();
      let side = sideUp === "BUY" ? "buy" :
      sideUp === "SELL" ? "sell" :
      px > (prevPrice.current || px) ? "buy" :
      px < (prevPrice.current || px) ? "sell" :
      lastSideRef.current || "buy";
      lastSideRef.current = side;
      prevPrice.current = px;
      const b = bufferRef.current;
      const now = Date.now();
      if (aggregationMs <= 0) {
        onTrade({
          id: now + Math.random(),
          price: px,
          size: tradeSize,
          side: side,
          time: detail.time || tickTime,
          timestamp: tickTime,
          volume: tickVol,
          count: 1
        });
        return;
      }
      const canMerge = b.size > 0 && b.price === px && b.side === side;
      if (canMerge) {
        b.size += tradeSize;
        b.totalVolume = tickVol;
        b.count++;
      } else {
        if (b.size > 0) flushBuffer();
        b.price = px;
        b.side = side;
        b.size = tradeSize;
        b.totalVolume = tickVol;
        b.firstTime = tickTime;
        b.firstTimeFormatted = detail.time;
        b.count = 1;
        if (flushTimer.current) clearTimeout(flushTimer.current);
        flushTimer.current = setTimeout(flushBuffer, aggregationMs);
      }
    };
    window.addEventListener('market_tick', handleMarketTick);
    return () => {
      window.removeEventListener('market_tick', handleMarketTick);
      if (flushTimer.current) clearTimeout(flushTimer.current);
    };
  }, [symbol, onTrade, aggregationMs]);
  useEffect(() => {
    if (wsActive.current || !isCumulative) return;
    const px = Number(lastPrice);
    const vol = Number(volume);
    const time = Number(timestamp);
    if (!px || vol < 0 || !time) return;
    if (prevPrice.current === null) {
      prevVol.current = vol;
      prevPrice.current = px;
      prevTime.current = time;
      return;
    }
    if (vol === prevVol.current) {prevPrice.current = px;return;}
    let delta = vol - (prevVol.current || 0);
    if (delta < 0) delta = vol;
    prevVol.current = vol;
    prevTime.current = time;
    prevPrice.current = px;
    if (delta <= 0) return;
    const sideUp = (providedSide || "").toUpperCase();
    let side = sideUp === "BUY" ? "buy" :
    sideUp === "SELL" ? "sell" :
    px > prevPrice.current ? "buy" :
    px < prevPrice.current ? "sell" :
    lastSideRef.current || "buy";
    lastSideRef.current = side;
    onTrade({
      id: Date.now() + Math.random(),
      price: px,
      size: delta,
      side: side,
      time: formatTime(time),
      timestamp: time,
      volume: vol
    });
  }, [lastPrice, volume, timestamp, symbol, isCumulative, onTrade, providedSide]);
};
window.useTradeStream = useTradeStream;