const CandleTimer = ({ symbol = 'SPY', timeframe, timerConfig, indicatorPanelTop = 0.75, lastCandleTime = null }) => {
  const { useState, useEffect } = React;
  const [timeLeft, setTimeLeft] = useState('');
  const [progress, setProgress] = useState(100);
  const [isMarketOpen, setIsMarketOpen] = useState(true);
  const checkMarketOpen = async () => {
    try {
      if (typeof getMarketSession === 'function') {
        const session = await getMarketSession(symbol);
        return session.isOpen || false;
      }
      const now = new Date();
      const utcHour = now.getUTCHours();
      const utcMinutes = now.getUTCMinutes();
      const utcTime = utcHour + utcMinutes / 60;
      const dayOfWeek = now.getUTCDay();
      if (dayOfWeek === 0 || dayOfWeek === 6) {
        return false;
      }
      const isOpen = utcTime >= 0 && utcTime < 9 ||
      utcTime >= 8 && utcTime < 16.5 ||
      utcTime >= 13.5 && utcTime < 21;
      return isOpen;
    } catch (error) {
      console.warn('Error checking market status:', error);
      return true;
    }
  };
  const lastMarketCheckRef = React.useRef(0);
  const getIntervalSeconds = (tf) => {
    if (!tf) return 60;
    const numMatch = tf.match(/\d+/);
    const num = numMatch ? parseInt(numMatch[0]) : 1;
    const unit = tf.replace(/\d+/g, '').toLowerCase();
    switch (unit) {
      case 'm':return num * 60;
      case 'h':return num * 3600;
      case 'd':return num * 86400;
      case 'w':return num * 604800;
      default:return num * 60;
    }
  };
  useEffect(() => {
    const intervalSeconds = getIntervalSeconds(timeframe);
    const updateTimer = async () => {
      const nowMs = Date.now();
      if (nowMs - lastMarketCheckRef.current > 10000) {
        const marketOpen = await checkMarketOpen();
        setIsMarketOpen(marketOpen);
        lastMarketCheckRef.current = nowMs;
      }
      if (!isMarketOpen) {
        setTimeLeft('CLOSED');
        setProgress(0);
        return;
      }
      if (!lastCandleTime || lastCandleTime === 0) {
        setTimeLeft('WAITING');
        setProgress(0);
        return;
      }
      const now = Date.now() / 1000;
      let timeSinceLastCandle = now - lastCandleTime;
      let offset = 0;
      // Relaxed bounds for offset correction to prevent false pauses
      if (timeSinceLastCandle < -60 || timeSinceLastCandle > intervalSeconds + 60) {
        const diff = lastCandleTime - now;
        offset = Math.round(diff / 1800) * 1800;
      }
      const adjustedNow = now + offset;
      const effectiveTimeSince = adjustedNow - lastCandleTime;
      let candleStart = lastCandleTime;
      
      if (effectiveTimeSince >= intervalSeconds) {
        const rotations = Math.floor(effectiveTimeSince / intervalSeconds);
        candleStart = lastCandleTime + rotations * intervalSeconds;
      } else if (effectiveTimeSince < 0) {
        renderTimer(Math.abs(effectiveTimeSince) * 1000, intervalSeconds, adjustedNow, lastCandleTime - intervalSeconds);
        return;
      }
      
      const nextCandleStart = candleStart + intervalSeconds;
      const remaining = (nextCandleStart - adjustedNow) * 1000;
      renderTimer(remaining, intervalSeconds, adjustedNow, candleStart);
    };
    
    const renderTimer = (remaining, intervalSeconds, nowRef, candleStartRef) => {
      if (remaining < 0) remaining = 0;
      if (remaining > intervalSeconds * 1000) {
        remaining = remaining % (intervalSeconds * 1000);
      }
      const seconds = Math.floor(remaining / 1000 % 60);
      const minutes = Math.floor(remaining / (1000 * 60) % 60);
      const hours = Math.floor(remaining / (1000 * 60 * 60) % 24);
      let display = '';
      if (hours > 0) {
        display = `${hours}:${minutes.toString().padStart(2, '0')}:${seconds.toString().padStart(2, '0')}`;
      } else if (minutes > 0) {
        display = `${minutes}:${seconds.toString().padStart(2, '0')}`;
      } else {
        display = `0:${seconds.toString().padStart(2, '0')}`;
      }
      setTimeLeft(display);
      const elapsed = (nowRef - candleStartRef) * 1000;
      const progressPercent = elapsed / (intervalSeconds * 1000) * 100;
      setProgress(Math.max(0, Math.min(100, 100 - progressPercent)));
    };
    updateTimer();
    const interval = setInterval(updateTimer, 1000);
    return () => clearInterval(interval);
  }, [timeframe, lastCandleTime, symbol]);
  const config = timerConfig || {
    position: 'bottom',
    size: 'medium',
    color: '#fbbf24',
    showProgress: true,
    enabled: true
  };
  if (!config.enabled) return null;
  const sizeConfig = {
    small: { fontSize: '10px', padding: '4px 8px', height: '3px' },
    medium: { fontSize: '12px', padding: '6px 12px', height: '4px' },
    large: { fontSize: '14px', padding: '8px 16px', height: '5px' }
  };
  const size = sizeConfig[config.size] || sizeConfig.medium;
  const isAxisOnMain = indicatorPanelTop >= 0.95;
  const bottomPosition = config.position === 'top' ?
    null :
    isAxisOnMain ?
      '60px' :
      `calc(${(1 - indicatorPanelTop) * 100}% + 12px)`;
  const positionStyle = config.position === 'top' ?
    { top: '60px', right: '90px' } :
    { bottom: bottomPosition, right: '90px' };
  return (
    React.createElement("div", {
      className: "absolute z-[100] pointer-events-none",
      style: {
        ...positionStyle,
        backgroundColor: 'rgba(0, 0, 0, 0.8)',
        backdropFilter: 'blur(8px)',
        border: `1px solid ${isMarketOpen ? config.color : '#ef4444'}40`,
        borderRadius: '6px',
        padding: size.padding,
        minWidth: '80px',
        textAlign: 'center'
      } },
    React.createElement("div", {
      style: {
        fontSize: size.fontSize,
        fontWeight: 'bold',
        color: isMarketOpen ? config.color : '#ef4444',
        fontFamily: 'monospace',
        letterSpacing: '0.5px'
      } },
    timeLeft
    ),
    config.showProgress && isMarketOpen &&
    React.createElement("div", {
      style: {
        width: '100%',
        height: size.height,
        backgroundColor: 'rgba(255, 255, 255, 0.1)',
        borderRadius: '2px',
        marginTop: '4px',
        overflow: 'hidden'
      } },
    React.createElement("div", {
      style: {
        width: `${progress}%`,
        height: '100%',
        backgroundColor: config.color,
        transition: 'width 0.1s linear',
        borderRadius: '2px'
      } }
    )
    )
    ));
};
window.CandleTimer = CandleTimer;