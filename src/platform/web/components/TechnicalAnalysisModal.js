const TechnicalAnalysisModal = ({ isOpen, onClose }) => {
  const [articles, setArticles] = React.useState([]);
  const [loading, setLoading] = React.useState(true);
  const [refreshing, setRefreshing] = React.useState(false);

  // --- Dragging Logic ---
  const width = 820;
  const height = 580;
  const clampPos = (p) => {
    if (typeof window === 'undefined') return p;
    const maxX = Math.max(0, window.innerWidth - width);
    const maxY = Math.max(0, window.innerHeight - 50);
    return { x: Math.min(Math.max(0, p.x), maxX), y: Math.min(Math.max(0, p.y), maxY) };
  };
  const [pos, setPos] = React.useState(() => {
    if (typeof window === 'undefined') return { x: 100, y: 100 };
    const defaultPos = {
      x: Math.max(24, (window.innerWidth - width) / 2),
      y: Math.max(24, (window.innerHeight - height) / 2)
    };
    try {
      const saved = localStorage.getItem('technical_modal_pos');
      if (saved) return clampPos(JSON.parse(saved));
    } catch (e) { }
    return clampPos(defaultPos);
  });
  const [dragging, setDragging] = React.useState(false);
  const dragRef = React.useRef(null);
  const offsetRef = React.useRef({ x: 0, y: 0 });
  const initializedRef = React.useRef(false);

  React.useLayoutEffect(() => {
    if (!isOpen) return;
    if (initializedRef.current) return;
    try {
      const saved = localStorage.getItem('technical_modal_pos');
      if (saved) {
        setPos(clampPos(JSON.parse(saved)));
        initializedRef.current = true;
        return;
      }
    } catch (e) { }
    setPos(clampPos({
      x: Math.max(24, (window.innerWidth - width) / 2),
      y: Math.max(24, (window.innerHeight - height) / 2)
    }));
    initializedRef.current = true;
  }, [isOpen]);

  const handleMouseDown = (e) => {
    if (!e.target.closest('.drag-handle')) return;
    const targetTag = e.target.tagName.toLowerCase();
    if (targetTag !== 'button' && targetTag !== 'a') {
      e.preventDefault();
    }
    setDragging(true);
    const rect = dragRef.current.getBoundingClientRect();
    offsetRef.current = { x: e.clientX - rect.left, y: e.clientY - rect.top };
  };

  React.useEffect(() => {
    if (!dragging) return;
    const move = (e) => {
      setPos(clampPos({
        x: e.clientX - offsetRef.current.x,
        y: e.clientY - offsetRef.current.y
      }));
    };
    const stop = () => setDragging(false);
    window.addEventListener('mousemove', move, true);
    window.addEventListener('mouseup', stop, true);
    return () => {
      window.removeEventListener('mousemove', move, true);
      window.removeEventListener('mouseup', stop, true);
    };
  }, [dragging]);

  React.useEffect(() => {
    if (!dragging && initializedRef.current) {
      try { localStorage.setItem('technical_modal_pos', JSON.stringify(pos)); } catch (e) { }
    }
  }, [dragging, pos]);
  
  // --- Data Fetching ---
  const fetchAnalysis = async () => {
    try {
      const res = await fetch(`/api/analysis/technical`);
      const data = await res.json();
      if (data.status === 'ok') {
        setArticles(data.articles || []);
      }
    } catch (e) {
      console.error("Failed to fetch technical analysis", e);
    } finally {
      setLoading(false);
    }
  };

  React.useEffect(() => {
    if (isOpen) {
      fetchAnalysis();
    }
  }, [isOpen]);

  const handleManualRefresh = async () => {
    setRefreshing(true);
    await fetchAnalysis();
    setTimeout(() => setRefreshing(false), 800);
  };

  if (!isOpen) return null;

  return (
    React.createElement("div", { className: "fixed inset-0 z-[9999] pointer-events-none overflow-hidden font-sans" },
      React.createElement("div", {
        ref: dragRef,
        onMouseDown: handleMouseDown,
        style: { position: 'absolute', left: `${pos.x}px`, top: `${pos.y}px`, width: '820px', height: '580px' },
        className: "pointer-events-auto bg-panel border border-border rounded-xl shadow-2xl flex flex-col overflow-hidden animate-in fade-in zoom-in duration-200"
      },
        React.createElement("div", { className: "drag-handle cursor-move h-12 border-b border-border bg-black/20 flex items-center justify-between px-6 flex-shrink-0" },
          React.createElement("div", { className: "flex items-center gap-3" },
            React.createElement("div", { className: "flex bg-white/5 rounded-lg p-1 border border-white/5 items-center gap-2 px-3 py-1" },
              React.createElement("i", { className: "fas fa-chart-line text-accent text-[12px]" }),
              React.createElement("span", { className: "text-[10px] font-bold tracking-widest text-white uppercase" }, "QUANTUM TECHNICAL INSIGHTS")
            ),
            React.createElement("div", { className: "w-[1px] h-4 bg-white/10 mx-2" }),
            React.createElement("button", {
              onClick: handleManualRefresh,
              className: `p-2 text-muted hover:text-accent transition-all ${refreshing ? 'pointer-events-none' : ''}`,
              title: "Refrescar datos"
            },
              React.createElement("i", { className: `fas fa-sync-alt ${refreshing ? 'fa-spin' : ''} text-[12px]` })
            )
          ),
          React.createElement("div", { className: "flex items-center gap-2" },
            React.createElement("button", { onClick: onClose, className: "p-1.5 text-muted hover:text-white transition-colors" },
              React.createElement("i", { className: "fas fa-times text-xs" })
            )
          )
        ),
        
        React.createElement("div", { className: "flex-1 overflow-y-auto no-scrollbar divide-y divide-white/5 bg-[#0a0a0c]" },
          loading ?
            React.createElement("div", { className: "flex flex-col items-center justify-center h-full gap-4" },
              React.createElement("div", { className: "w-6 h-6 border border-accent/30 border-t-accent rounded-full animate-spin" }),
              React.createElement("span", { className: "text-[8px] text-muted font-bold tracking-[0.2em] animate-pulse" }, "GATHERING MARKET INTELLIGENCE...")
            ) :
            React.createElement("div", { className: "flex flex-col divide-y divide-white/[0.03]" },
              articles.length > 0 ? articles.map((item, idx) => {
                
                // Determinamos el mercado en base al titulo para añadir un estilo sutil
                let market = "GENERAL";
                let icon = "fa-chart-pie";
                const titleLower = item.title.toLowerCase();
                if (titleLower.includes("sp500") || titleLower.includes("s&p")) { market = "S&P 500"; icon = "fa-chart-area"; }
                else if (titleLower.includes("nasdaq")) { market = "NASDAQ"; icon = "fa-microchip"; }
                else if (titleLower.includes("wti") || titleLower.includes("petróleo") || titleLower.includes("crudo")) { market = "WTI CRUDE"; icon = "fa-oil-can"; }
                else if (titleLower.includes("oro") || titleLower.includes("gold")) { market = "GOLD"; icon = "fa-coins"; }

                return (
                  React.createElement("div", { key: idx, className: "p-5 hover:bg-white/[0.02] transition-all group relative overflow-hidden" },
                    React.createElement("div", { className: "flex gap-5 relative z-10" },
                      React.createElement("div", { className: "flex-1 min-w-0" },
                        React.createElement("div", { className: "flex items-center justify-between mb-2" },
                          React.createElement("div", { className: "flex items-center gap-2" },
                            React.createElement("span", { className: "px-2 py-0.5 bg-accent/10 border border-accent/20 rounded text-[7px] font-bold text-accent uppercase tracking-wider flex items-center gap-1.5" },
                              React.createElement("i", { className: `fas ${icon}` }), market
                            ),
                            React.createElement("span", { className: "text-[8px] text-gray-500 font-medium" },
                              item.date
                            ),
                            React.createElement("span", { className: "text-[8px] text-gray-600 font-mono border-l border-white/10 pl-2 ml-1" },
                              "By " + item.author
                            )
                          )
                        ),
                        React.createElement("h3", { className: "text-[12px] font-bold text-white mb-2 group-hover:text-accent transition-colors leading-snug" },
                          item.title
                        ),
                        React.createElement("p", { className: "text-[10.5px] text-gray-400 line-clamp-3 leading-relaxed mb-4 border-l-2 border-white/5 pl-3" },
                          item.snippet || "Click para leer el análisis técnico completo de esta sesión."
                        ),
                        React.createElement("div", { className: "flex items-center justify-between" },
                          React.createElement("a", {
                            href: item.url,
                            target: "_blank",
                            rel: "noopener noreferrer",
                            className: "px-4 py-1.5 bg-white/5 hover:bg-white/10 border border-white/10 rounded text-[8px] font-bold text-white flex items-center gap-2 transition-all group-hover:border-accent/30 group-hover:text-accent"
                          },
                            "LEER INFORME COMPLETO", React.createElement("i", { className: "fas fa-arrow-right text-[7px] opacity-50 group-hover:opacity-100 group-hover:translate-x-1 transition-all" })
                          )
                        )
                      )
                    )
                  ));
              }) :
                React.createElement("div", { className: "flex flex-col items-center justify-center p-24 gap-5" },
                  React.createElement("div", { className: "w-16 h-16 rounded-full bg-white/5 flex items-center justify-center border border-white/5" },
                    React.createElement("i", { className: "fas fa-chart-line text-white/10 text-2xl" })
                  ),
                  React.createElement("div", { className: "text-center" },
                    React.createElement("span", { className: "text-[10px] text-muted font-black uppercase tracking-[0.3em] block mb-1" }, "NO HAY ANÁLISIS RECIENTES"),
                    React.createElement("span", { className: "text-[8px] text-gray-600 font-medium" }, "Intenta más tarde para leer los nuevos informes del mercado.")
                  )
                )
            )
        ),
        React.createElement("div", { className: "h-10 bg-black/40 border-t border-white/5 flex items-center justify-between px-6 flex-shrink-0" },
          React.createElement("span", { className: "text-[9px] text-muted font-bold tracking-[0.2em] flex items-center gap-2" },
            React.createElement("div", { className: "w-1 h-1 bg-green-500 rounded-full" }), " DATA SOURCED & ANALYZED"
          ),
          React.createElement("span", { className: "text-[8px] text-gray-600 font-mono uppercase" },
            "Powered by Quantum Llama"
          )
        )
      )
    ));
};
window.TechnicalAnalysisModal = TechnicalAnalysisModal;
