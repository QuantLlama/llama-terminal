import React from 'react';
const HistoryPanel = ({ activeSymbol }) => {
  const { useState, useEffect, useRef, useMemo } = React;
  const calculateRoundTripCommission = (symbol, volume) => {
    if (typeof window.calculateCommission === 'function') {
      return window.calculateCommission(symbol, volume);
    }
    return volume * 5.0;
  };
  const [allDeals, setAllDeals] = useState([]);
  const [deals, setDeals] = useState([]);
  const [days, setDays] = useState(30);
  const [accountBalance, setAccountBalance] = useState(0);
  const [initialBalance, setInitialBalance] = useState(0);
  const [maxDrawdown, setMaxDrawdown] = useState(0);
  const [netProfit, setNetProfit] = useState(0);
  const [totalCommission, setTotalCommission] = useState(0);
  const [chartMode, setChartMode] = useState(localStorage.getItem('history_chart_mode') || 'area');
  const [chartBg, setChartBg] = useState(localStorage.getItem('history_chart_bg') || '#111111');
  const [showSettings, setShowSettings] = useState(false);
  const chartContainerRef = useRef();
  const chartRef = useRef();
  const balanceSeriesRef = useRef();
  const drawdownSeriesRef = useRef();
  const formatDate = (timestamp) => {
    const seconds = Number(timestamp);
    // Some payloads carry milliseconds; without this the panel would render 1970.
    const safeSeconds = Number.isFinite(seconds) ? (seconds > 1e11 ? seconds / 1000 : seconds) : 0;
    const date = new Date(safeSeconds * 1000);
    return date.toLocaleDateString() + ' ' + date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  };
  useEffect(() => {
    localStorage.setItem('history_chart_mode', chartMode);
    localStorage.setItem('history_chart_bg', chartBg);
    if (chartRef.current) {
      chartRef.current.applyOptions({
        layout: { background: { color: chartBg } }
      });
    }
  }, [chartMode, chartBg]);
  const getDealCommission = (d) => {
    // Si viene la comisión del deal en MT5/CFD/Crypto, la usamos directamente (suele ser negativa)
    if (d.commission !== undefined && d.commission !== null) {
      return d.commission;
    }
    return 0;
  };

  // The bridge serialises MT5 records, and a field that arrives as "0" instead of 0
  // makes every strict comparison below fail silently: the deal is neither a trade
  // nor a balance move, so it is filtered out and the panel looks empty.
  const dealType = (d) => Number(d.type);

  const isTradingDeal = (d) => {
    const type = dealType(d);
    return type === 0 || type === 1;
  };

  const isBalanceTransaction = (d) => {
    return dealType(d) === 2;
  };

  const isClosingTradingDeal = (d) => {
    // Un deal de trading es de cierre si tiene impacto financiero (profit, swap o comisión no nulos)
    // Esto es mucho más seguro que depender de 'entry', que puede variar según la cuenta de netting/hedging
    // o el broker, asegurando que el 100% de las ganancias y pérdidas reales se sumen siempre correctamente.
    return isTradingDeal(d) && ((d.profit || 0) !== 0 || (d.swap || 0) !== 0 || getDealCommission(d) !== 0);
  };

  const isClosingOrBalanceDeal = (d) => {
    return isClosingTradingDeal(d) || isBalanceTransaction(d);
  };

  const getDealBalanceImpact = (d) => {
    if (isBalanceTransaction(d)) {
      return d.profit || 0;
    }
    if (isClosingTradingDeal(d)) {
      return (d.profit || 0) + getDealCommission(d) + (d.swap || 0);
    }
    return 0;
  };

  const isClosingDeal = (d) => {
    return isClosingOrBalanceDeal(d);
  };

  useEffect(() => {
    const fetchDeals = async () => {
      try {
        // BUG FIX: se pasa days=9999 para traer todo el historial disponible;
        // el filtrado por período se hace en el cliente según el selector.
        const response = await window.authFetch('/api/deals?days=9999');
        if (response.ok) {
          const data = await response.json();
          const fetchedDeals = Array.isArray(data) ? data : data.deals || [];
          setAllDeals(fetchedDeals);
          setAccountBalance(data.account_balance || 0);
        }
      } catch (error) {
        console.error('Error fetching deals:', error);
      }
    };
    fetchDeals();
    const interval = setInterval(fetchDeals, 10000);
    return () => clearInterval(interval);
  }, []);

  useEffect(() => {
    if (allDeals.length === 0) return;
    let profitInPeriod = 0;
    let commissionInPeriod = 0;
    const now = Date.now() / 1000;
    const startTime = now - days * 24 * 60 * 60;

    // 1. Filtrar los deals para el periodo y el símbolo actual
    const filtered = allDeals.filter((d) => {
      // Same trap as `type`, worse: a string timestamp compared against a number
      // goes through a lexicographic comparison and quietly drops every deal.
      const dealTime = Number(d.time);
      const matchesTime = Number.isFinite(dealTime) && dealTime >= startTime;

      // Si es una transacción de balance, sólo incluir si no hay un símbolo activo (vista global de la cuenta)
      if (isBalanceTransaction(d)) {
        return matchesTime && !activeSymbol;
      }

      let matchesSymbol = !activeSymbol;
      if (activeSymbol && d.symbol) {
        const s1 = activeSymbol.toUpperCase().replace(/[^A-Z0-9]/g, '');
        const s2 = d.symbol.toUpperCase().replace(/[^A-Z0-9]/g, '');
        matchesSymbol = s2 === s1 || s2.includes(s1) || s1.includes(s2);
        if (!matchesSymbol && s1.length >= 2 && s2.length >= 2) {
          const prefix1 = s1.substring(0, 2);
          const prefix2 = s2.substring(0, 2);
          matchesSymbol = prefix1 === prefix2;
        }
      }
      return matchesTime && matchesSymbol;
    });

    const sortedFilteredDeals = [...filtered].sort((a, b) => b.time - a.time);
    setDeals(sortedFilteredDeals);

    // 2. Calcular PnL y Comisiones sólo de operaciones de trading cerradas en el periodo
    filtered.forEach((d) => {
      if (isClosingTradingDeal(d)) {
        const comm = getDealCommission(d);
        profitInPeriod += (d.profit || 0) + comm + (d.swap || 0);
        commissionInPeriod += comm;
      }
    });

    setNetProfit(profitInPeriod);
    setTotalCommission(commissionInPeriod);

    // 3. Reconstruir el Balance Inicial de forma matemática exacta
    let initialBalanceCalculated = 0;
    if (activeSymbol) {
      // Si hay un símbolo activo, el balance de partida es 0 y muestra el PnL acumulado
      initialBalanceCalculated = 0;
    } else {
      // Si es la cuenta completa, retrocedemos desde el balance actual restando todos los impactos
      // de todos los deals de la cuenta que ocurrieron desde el inicio del período hasta el momento actual.
      // Así el balance final del gráfico calzará al centavo con el balance actual de la cuenta.
      let tempBalance = accountBalance;
      const dealsForReconstruction = allDeals.filter((d) => d.time >= startTime);
      const descDeals = [...dealsForReconstruction].sort((a, b) => {
        if (b.time !== a.time) return b.time - a.time;
        return (b.ticket || 0) - (a.ticket || 0);
      });
      
      descDeals.forEach((d) => {
        tempBalance -= getDealBalanceImpact(d);
      });
      initialBalanceCalculated = tempBalance;
    }

    setInitialBalance(initialBalanceCalculated);

    // 4. Construir curva de balance y drawdown en orden cronológico (ascendente)
    let currentBalance = initialBalanceCalculated;
    let peakBalance = currentBalance;
    let maxDD = 0;
    const balanceChartData = [];
    const drawdownChartData = [];

    const ascFilteredDeals = [...filtered].sort((a, b) => {
      if (a.time !== b.time) return a.time - b.time;
      return (a.ticket || 0) - (b.ticket || 0);
    });

    if (ascFilteredDeals.length > 0) {
      balanceChartData.push({ time: ascFilteredDeals[0].time, value: currentBalance });
      drawdownChartData.push({ time: ascFilteredDeals[0].time, value: 0 });
    }

    ascFilteredDeals.forEach((d, idx) => {
      if (isClosingOrBalanceDeal(d)) {
        currentBalance += getDealBalanceImpact(d);
        let adjustedTime = d.time;
        if (idx > 0 && adjustedTime <= balanceChartData[balanceChartData.length - 1].time) {
          adjustedTime = balanceChartData[balanceChartData.length - 1].time + 1;
        }
        d._adjustedTime = adjustedTime;
        balanceChartData.push({ time: adjustedTime, value: currentBalance });

        if (currentBalance > peakBalance) peakBalance = currentBalance;
        const drawdown = peakBalance > 0 ? ((peakBalance - currentBalance) / peakBalance) * 100 : 0;
        maxDD = Math.max(maxDD, drawdown);
        drawdownChartData.push({ time: adjustedTime, value: drawdown > 0 ? -drawdown : 0 });
      }
    });

    // 5. Dibujar en el gráfico
    if (chartRef.current) {
      if (balanceSeriesRef.current) {
        chartRef.current.removeSeries(balanceSeriesRef.current);
        balanceSeriesRef.current = null;
      }
      if (drawdownSeriesRef.current) {
        chartRef.current.removeSeries(drawdownSeriesRef.current);
        drawdownSeriesRef.current = null;
      }
      if (chartMode === 'area') {
        balanceSeriesRef.current = chartRef.current.addAreaSeries({
          lineColor: '#fbbf24', topColor: 'rgba(251, 191, 36, 0.4)', bottomColor: 'rgba(251, 191, 36, 0.0)',
          lineWidth: 2, priceScaleId: 'balance_scale'
        });
      } else {
        balanceSeriesRef.current = chartRef.current.addLineSeries({
          color: '#fbbf24', lineWidth: 2, priceScaleId: 'balance_scale'
        });
      }
      drawdownSeriesRef.current = chartRef.current.addAreaSeries({
        lineColor: '#ef4444', topColor: 'rgba(239, 68, 68, 0.4)', bottomColor: 'rgba(239, 68, 68, 0.0)',
        lineWidth: 2, priceScaleId: 'drawdown_scale'
      });
      chartRef.current.priceScale('balance_scale').applyOptions({ autoScale: true, visible: true, borderColor: '#fbbf24' });
      chartRef.current.priceScale('drawdown_scale').applyOptions({ autoScale: true, visible: true, borderColor: '#ef4444' });

      if (balanceChartData.length > 0) {
        balanceSeriesRef.current.setData(balanceChartData);
        drawdownSeriesRef.current.setData(drawdownChartData);
        
        // Marcadores de ganancias/pérdidas (sólo para operaciones de trading cerradas)
        const markers = ascFilteredDeals
          .filter((d) => isClosingTradingDeal(d))
          .map((d) => {
            const p = (d.profit || 0) + getDealCommission(d) + (d.swap || 0);
            return {
              time: d._adjustedTime || d.time,
              position: 'aboveBar',
              color: p >= 0 ? '#10b981' : '#ef4444',
              shape: p >= 0 ? 'arrowUp' : 'arrowDown',
              size: 0.4,
              text: (p >= 0 ? '+' : '') + p.toFixed(2)
            };
          });
        balanceSeriesRef.current.setMarkers(markers);
        chartRef.current.timeScale().fitContent();
      }
    }
    setMaxDrawdown(maxDD);
  }, [days, activeSymbol, allDeals, accountBalance, chartMode]);
  useEffect(() => {
    if (!chartContainerRef.current) return;
    const chart = LightweightCharts.createChart(chartContainerRef.current, {
      layout: {
        background: { type: 'solid', color: chartBg },
        textColor: '#64748b',
        fontSize: 10
      },
      grid: { vertLines: { visible: false }, horzLines: { color: '#222' } },
      width: chartContainerRef.current.clientWidth,
      height: 150,
      timeScale: { timeVisible: true, borderVisible: false }
    });
    chartRef.current = chart;
    const resizeObserver = new ResizeObserver((entries) => {
      if (entries.length > 0 && chartRef.current) {
        const { width, height } = entries[0].contentRect;
        chartRef.current.resize(width, height);
      }
    });
    resizeObserver.observe(chartContainerRef.current);
    return () => {
      resizeObserver.disconnect();
      if (chartRef.current) {
        chartRef.current.remove();
        chartRef.current = null;
      }
    };
  }, []);
  return (
    React.createElement("div", { className: "flex flex-col h-full min-h-0 bg-[#0a0a0a] relative overflow-hidden" },
    React.createElement("div", { className: "p-2 border-b border-border flex items-center justify-between bg-black/30 shrink-0" },
    React.createElement("div", { className: "flex gap-1.5 overflow-x-hidden no-scrollbar" },
    [1, 7, 30, 90, 365, 9999].map((d) =>
    React.createElement("button", {
      key: d,
      onClick: () => setDays(d),
      className: `px-2.5 py-1 text-[9px] font-black tracking-tighter rounded-sm transition-all ${days === d ? 'bg-accent text-black shadow-[0_0_10px_rgba(251,191,36,0.2)]' : 'bg-white/5 text-muted hover:text-white'}` },
    d === 365 ? '1Y' : d === 9999 ? 'ALL' : d + 'D'
    )
    )
    )
    ),
    React.createElement("div", { className: "h-44 w-full relative border-b border-border bg-black/20" },
    React.createElement("div", { ref: chartContainerRef, className: "w-full h-full" }),
    React.createElement("div", { className: "absolute top-2 left-2 flex flex-col gap-1 pointer-events-none bg-black/60 p-1.5 rounded-sm border border-white/5 backdrop-blur-sm z-20" },
    React.createElement("div", { className: "flex items-center gap-2" },
    React.createElement("div", { className: "w-2 h-2 rounded-full bg-[#fbbf24]" }),
    React.createElement("span", { className: "text-[8px] text-white/50 uppercase font-bold tracking-widest" }, "Balance")
    ),
    React.createElement("div", { className: "flex items-center gap-2" },
    React.createElement("div", { className: "w-2 h-2 rounded-full bg-[#ef4444]" }),
    React.createElement("span", { className: "text-[8px] text-white/50 uppercase font-bold tracking-widest" }, "Drawdown")
    )
    ),
    deals.length === 0 &&
    React.createElement("div", { className: "absolute inset-0 flex items-center justify-center pointer-events-none" },
    React.createElement("span", { className: "text-muted text-[10px] font-mono italic opacity-30" }, "NO DATA FOUND FOR THIS PERIOD")
    )
    ),
    React.createElement("div", { className: "p-4 border-b border-border text-[9px] grid grid-cols-4 gap-4 bg-black/40 shrink-0 font-mono" },
    React.createElement("div", { className: "flex flex-col" },
    React.createElement("span", { className: "text-white/40 uppercase font-black text-[7px] tracking-widest mb-0.5" }, "Startup"),
    React.createElement("span", { className: "text-white font-bold" }, "$", initialBalance.toLocaleString(undefined, { minimumFractionDigits: 2 }))
    ),
    React.createElement("div", { className: "flex flex-col items-center" },
    React.createElement("span", { className: "text-white/40 uppercase font-black text-[7px] tracking-widest mb-0.5 text-center w-full" }, "Net PnL"),
    React.createElement("span", { className: `font-black text-[10px] ${netProfit >= 0 ? 'text-success' : 'text-danger'}` },
    netProfit >= 0 ? '+' : '', "$", netProfit.toLocaleString(undefined, { minimumFractionDigits: 2 })
    )
    ),
    React.createElement("div", { className: "flex flex-col items-center" },
    React.createElement("span", { className: "text-white/40 uppercase font-black text-[7px] tracking-widest mb-0.5 text-center w-full" }, "Max DD"),
    React.createElement("span", { className: "text-danger font-bold text-[10px]" }, maxDrawdown.toFixed(2), "%")
    ),
    React.createElement("div", { className: "flex flex-col items-end" },
    React.createElement("span", { className: "text-white/40 uppercase font-black text-[7px] tracking-widest mb-0.5" }, "Total Com"),
    React.createElement("span", { className: "text-white/70 font-bold text-[10px]" }, "$", Math.abs(totalCommission).toFixed(2))
    )
    ),
    React.createElement("div", { className: "flex-1 min-h-0 overflow-y-auto overflow-x-hidden no-scrollbar" },
    React.createElement("table", { className: "w-full text-[9px] font-mono border-separate border-spacing-0" },
    React.createElement("thead", { className: "bg-[#050505] sticky top-0 z-10" },
    React.createElement("tr", { className: "border-b border-white/5" },
    React.createElement("th", { className: "text-left px-3 py-2 text-[7px] text-white/40 uppercase font-black tracking-widest" }, "TIME"),
    React.createElement("th", { className: "text-center px-1 py-2 text-[7px] text-white/40 uppercase font-black tracking-widest" }, "TYPE"),
    React.createElement("th", { className: "text-left px-2 py-2 text-[7px] text-white/40 uppercase font-black tracking-widest" }, "SYMBOL"),
    React.createElement("th", { className: "text-right px-2 py-2 text-[7px] text-white/40 uppercase font-black tracking-widest" }, "REF"),
    React.createElement("th", { className: "text-right px-2 py-2 text-[7px] text-white/40 uppercase font-black tracking-widest" }, "COM"),
    React.createElement("th", { className: "text-right px-3 py-2 text-[7px] text-white/40 uppercase font-black tracking-widest" }, "NET PROFIT")
    )
    ),
    React.createElement("tbody", { className: "divide-y divide-white/5" },
    deals.filter((d) => isClosingOrBalanceDeal(d)).map((d) => {
      const isBal = isBalanceTransaction(d);
      let comm = 0;
      let netP = 0;
      if (isBal) {
        netP = d.profit || 0;
      } else {
        comm = getDealCommission(d);
        netP = (d.profit || 0) + comm + (d.swap || 0);
      }
      return (
        React.createElement("tr", { key: d.ticket, className: "hover:bg-white/5 transition-colors group" },
        React.createElement("td", { className: "px-3 py-1.5 text-white/40 group-hover:text-white/70" }, formatDate(d.time)),
        React.createElement("td", { className: "px-1 py-1.5 text-center" },
        isBal ? 
          React.createElement("span", { className: "px-1.5 py-0.5 rounded-xs font-black bg-blue-500/10 text-blue-400 text-[8px]" }, "BALANCE") :
          React.createElement("span", { className: `px-1.5 py-0.5 rounded-xs font-black ${d.type === 0 ? 'bg-success/10 text-success' : 'bg-danger/10 text-danger'}` },
          d.type === 0 ? 'BUY' : 'SELL'
          )
        ),
        React.createElement("td", { className: `px-2 py-1.5 font-bold ${isBal ? 'text-white/30 font-normal italic' : 'text-white/80'}` }, isBal ? 'Balance' : d.symbol),
        React.createElement("td", { className: "px-2 py-1.5 text-right text-white/30 font-mono" }, d.ticket),
        React.createElement("td", { className: "px-2 py-1.5 text-right text-white/30 font-mono" }, isBal ? '—' : comm.toFixed(2)),
        React.createElement("td", { className: `px-3 py-1.5 text-right font-black ${netP >= 0 ? 'text-success' : 'text-danger'}` },
        netP >= 0 ? '+' : '', netP.toFixed(2)
        )
        ));
    })
    )
    ),
    deals.length === 0 &&
    React.createElement("div", { className: "py-10 text-center text-white/40 text-sm" }, "No se encontraron operaciones en este periodo."
    )
    )
    ));
};
export default HistoryPanel;