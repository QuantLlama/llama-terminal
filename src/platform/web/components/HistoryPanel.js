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
    const date = new Date(timestamp * 1000);
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
  useEffect(() => {
    const fetchDeals = async () => {
      try {
        const response = await fetch('/api/deals');
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
    const filtered = allDeals.filter((d) => {
      const matchesTime = d.time >= startTime;
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
    const sortedFilteredDeals = filtered.sort((a, b) => b.time - a.time);
    setDeals(sortedFilteredDeals);
    filtered.forEach((d) => {
      if (d.entry === 1 || d.entry === 2 || d.entry === 3) {
        let comm = d.commission || 0;
        if (comm >= 0) {
          comm = -calculateRoundTripCommission(d.symbol, d.volume || 1);
        }
        profitInPeriod += d.profit + comm + (d.swap || 0);
        commissionInPeriod += comm;
      }
    });
    setInitialBalance(accountBalance - profitInPeriod);
    setNetProfit(profitInPeriod);
    setTotalCommission(commissionInPeriod);
    let currentBalance = accountBalance - profitInPeriod;
    let peakBalance = currentBalance;
    let maxDD = 0;
    const balanceChartData = [];
    const drawdownChartData = [];
    const ascFilteredDeals = [...filtered].sort((a, b) => a.time - b.time);
    if (ascFilteredDeals.length > 0) {
      balanceChartData.push({ time: ascFilteredDeals[0].time, value: currentBalance });
      drawdownChartData.push({ time: ascFilteredDeals[0].time, value: 0 });
    }
    ascFilteredDeals.forEach((d) => {
      if (d.entry === 1 || d.entry === 2 || d.entry === 3) {
        currentBalance += d.profit + (d.commission || 0) + (d.swap || 0);
        balanceChartData.push({ time: d.time, value: currentBalance });
        if (currentBalance > peakBalance) peakBalance = currentBalance;
        const drawdown = peakBalance > 0 ? (peakBalance - currentBalance) / peakBalance * 100 : 0;
        maxDD = Math.max(maxDD, drawdown);
        drawdownChartData.push({ time: d.time, value: drawdown > 0 ? -drawdown : 0 });
      }
    });
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
        const markers = ascFilteredDeals.filter((d) => d.entry === 1 || d.entry === 2 || d.entry === 3).map((d) => {
          const p = d.profit + (d.commission || 0) + (d.swap || 0);
          return {
            time: d.time,
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
    deals.filter((d) => d.entry === 1 || d.entry === 2 || d.entry === 3).map((d) => {
      let comm = d.commission || 0;
      if (comm >= 0) {
        comm = -calculateRoundTripCommission(d.symbol, d.volume || 1);
      }
      const netP = d.profit + comm + (d.swap || 0);
      return (
        React.createElement("tr", { key: d.ticket, className: "hover:bg-white/5 transition-colors group" },
        React.createElement("td", { className: "px-3 py-1.5 text-white/40 group-hover:text-white/70" }, formatDate(d.time)),
        React.createElement("td", { className: "px-1 py-1.5 text-center" },
        React.createElement("span", { className: `px-1.5 py-0.5 rounded-xs font-black ${d.type === 0 ? 'bg-success/10 text-success' : 'bg-danger/10 text-danger'}` },
        d.type === 0 ? 'BUY' : 'SELL'
        )
        ),
        React.createElement("td", { className: "px-2 py-1.5 text-white/80 font-bold" }, d.symbol),
        React.createElement("td", { className: "px-2 py-1.5 text-right text-white/30 font-mono" }, d.ticket),
        React.createElement("td", { className: "px-2 py-1.5 text-right text-white/30 font-mono" }, comm.toFixed(2)),
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