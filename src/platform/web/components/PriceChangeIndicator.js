const PriceChangeIndicator = ({ symbol, allBars = [], tickData, indicatorPanelTop = 0.75, settings }) => {
  const { useMemo } = React;

  const stats = settings?.stats || { enabled: true, type: 'percent', position: 'above-timer', fontSize: 14 };
  if (!stats.enabled) return null;

  const data = useMemo(() => {
    if (!allBars || allBars.length === 0) return { pts: 0, pct: 0, color: '#9ca3af', price: 0 };
    
    const lastBar = allBars[allBars.length - 1];
    const currentPrice = tickData?.last || lastBar.close;
    
    // Find the first bar of the current UTC day
    const now = new Date();
    const todayStart = new Date(Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate())).getTime() / 1000;
    
    let dayOpen = allBars[0].open;
    for (let i = allBars.length - 1; i >= 0; i--) {
        if (allBars[i].time < todayStart) {
            if (i + 1 < allBars.length) {
                dayOpen = allBars[i+1].open;
            } else {
                dayOpen = allBars[i].close;
            }
            break;
        }
    }

    const pts = currentPrice - dayOpen;
    const pct = (pts / dayOpen) * 100;
    const color = pts > 0 ? '#10b981' : pts < 0 ? '#ef4444' : '#9ca3af';
    
    return { pts, pct, color, price: currentPrice };
  }, [allBars, tickData, symbol]);

  const fontSize = stats.fontSize || 14;
  
  const getPositionStyle = () => {
    const margin = '12px';
    const timerRight = '90px'; // Matching CandleTimer.js
    
    switch (stats.position) {
      case 'above-timer':
        const isAxisOnMain = indicatorPanelTop >= 0.95;
        const timerBottom = isAxisOnMain ? 60 : (1 - indicatorPanelTop) * 100;
        const statsBottom = isAxisOnMain ? (60 + 35) : `calc(${(1 - indicatorPanelTop) * 100}% + 47px)`;
        return { bottom: statsBottom, right: timerRight };
      case 'top-left':
        return { top: '60px', left: margin };
      case 'top-right':
        return { top: '60px', right: timerRight };
      case 'bottom-left':
        return { bottom: '20px', left: margin };
      case 'bottom-right':
        return { bottom: '20px', right: timerRight };
      default:
        return { bottom: '100px', right: timerRight };
    }
  };

  const displayText = useMemo(() => {
    const ptsStr = (data.pts >= 0 ? '+' : '') + data.pts.toFixed(symbol?.includes('JPY') ? 3 : 2);
    const pctStr = (data.pct >= 0 ? '+' : '') + data.pct.toFixed(2) + '%';
    
    if (stats.type === 'points') return ptsStr;
    if (stats.type === 'both') return `${ptsStr} (${pctStr})`;
    return pctStr;
  }, [data, stats.type]);

  return (
    React.createElement("div", {
      className: "absolute z-[100] pointer-events-none flex flex-col items-end",
      style: {
        ...getPositionStyle(),
        transition: 'all 0.3s ease-in-out'
      }
    },
      React.createElement("div", {
        className: "flex items-center gap-2 px-3 py-1.5 rounded-lg backdrop-blur-md bg-black/60 border border-white/5 shadow-2xl",
        style: {
           borderLeft: `3px solid ${data.color}`
        }
      },
        React.createElement("span", {
          style: {
            color: data.color,
            fontSize: `${fontSize}px`,
            fontWeight: '900',
            fontFamily: 'Inter, sans-serif',
            textShadow: `0 0 10px ${data.color}40`,
            letterSpacing: '-0.02em'
          }
        }, displayText)
      )
    )
  );
};

window.PriceChangeIndicator = PriceChangeIndicator;
