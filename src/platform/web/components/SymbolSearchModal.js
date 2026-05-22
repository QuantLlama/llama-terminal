const SymbolSearchModal = ({ isOpen, onClose, onSelect, currentPlatform: initialPlatform }) => {
  const [query, setQuery] = React.useState("");
  const [symbols, setSymbols] = React.useState([]);
  const [loading, setLoading] = React.useState(false);
  const [filtered, setFiltered] = React.useState([]);
  const [activeTab, setActiveTab] = React.useState(
    initialPlatform === 'crypto' ? 'crypto' :
    initialPlatform === 'tradovate' ? 'tradovate' : 'mt5'
  );
  const fetchSymbols = async (tab, isForced = false) => {
    setLoading(true);
    setSymbols([]);
    setFiltered([]);
    try {
      const url = `/api/symbols?platform=${tab}${isForced ? '&force=true' : ''}${query ? '&query=' + encodeURIComponent(query) : ''}`;
      // console.log(`[SYMBOL-SEARCH] Fetching platform=${tab} forced=${isForced}`);
      const res = await fetch(url);
      const data = await res.json();
      if (data.length === 0 && isForced === false && !query) {
        console.warn(`[SYMBOL-SEARCH] No symbols for ${tab}.`);
      } else {
        setSymbols(data);
        setFiltered(data);
      }
      if (isForced) {
        window.notify && window.notify("Symbols Synced Successfully", "success");
      }
    } catch (e) {
      console.error("Fetch symbols failed:", e);
      setSymbols([]);
      setFiltered([]);
      if (isForced) {
        window.notify && window.notify("Failed to sync symbols", "error");
      }
    } finally {
      setLoading(false);
    }
  };
  React.useEffect(() => {
    if (isOpen) {
      fetchSymbols(activeTab, false);
    }
  }, [isOpen, activeTab]);
  React.useEffect(() => {
    const handleKeyDown = (e) => {
      if (isOpen && e.altKey && e.key.toLowerCase() === 's') {
        e.preventDefault();
        fetchSymbols(activeTab, true);
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isOpen, activeTab]);
  React.useEffect(() => {
    let list = [];
    if (!query) {
      list = [...symbols];
    } else {
      const lower = query.toLowerCase();
      list = symbols.filter((s) =>
      s.symbol.toLowerCase().includes(lower) ||
      s.description && s.description.toLowerCase().includes(lower)
      );
    }
    list.sort((a, b) => {
      const groupA = (a.group || "").toUpperCase();
      const groupB = (b.group || "").toUpperCase();
      const isMajorA = groupA.includes("MAJOR") || groupA.includes("INDEX") || groupA.includes("INDICES");
      const isMajorB = groupB.includes("MAJOR") || groupB.includes("INDEX") || groupB.includes("INDICES");
      if (isMajorA && !isMajorB) return -1;
      if (!isMajorA && isMajorB) return 1;
      const isCryptoA = groupA.includes("CRYPTO") || groupA.includes("COIN");
      const isCryptoB = groupB.includes("CRYPTO") || groupB.includes("COIN");
      if (isCryptoA && !isCryptoB) return 1;
      if (!isCryptoA && isCryptoB) return -1;
      return a.symbol.localeCompare(b.symbol);
    });
    setFiltered(list);
  }, [query, symbols]);
  if (!isOpen) return null;
  const getPlatformDisplayName = (platform) => {
    if (platform === 'mt5') return 'MetaTrader 5';
    if (platform === 'tradovate') return 'Tradovate';
    return 'Crypto Exchange';
  };
  return (
    React.createElement("div", { className: "fixed inset-0 bg-black/40 z-[9999] backdrop-blur-md animate-in fade-in duration-300 grid place-items-center" },
    React.createElement("div", { className: "w-[600px] h-[550px] bg-[#111] border border-white/10 rounded-2xl shadow-2xl flex flex-col overflow-hidden scale-in-center" },
    React.createElement("div", { className: "p-4 border-b border-white/5 flex flex-col gap-4 bg-black/20" },
    React.createElement("div", { className: "flex items-center gap-3" },
    React.createElement("div", { className: "relative flex-1" },
    React.createElement("i", { className: "fas fa-search absolute left-4 top-1/2 -translate-y-1/2 text-muted" }),
    React.createElement("input", {
      id: "symbol-search-input",
      autoFocus: true,
      type: "text",
      placeholder: "SEARCH SYMBOL (E.G. MNQ, NQ, EURUSD, XAUUSD)...",
      className: "w-full bg-[#1a1a1a] border border-white/5 rounded-xl py-3 pl-12 pr-4 text-sm text-white focus:border-accent/50 outline-none transition-all uppercase font-mono",
      value: query,
      onChange: (e) => setQuery(e.target.value),
      autoComplete: "off" }
    )
    ),
    React.createElement("button", {
      onClick: () => fetchSymbols(activeTab, true),
      className: `w-10 h-10 flex items-center justify-center text-muted hover:text-accent transition-all rounded-full hover:bg-white/5 ${loading ? 'animate-spin' : ''}`,
      title: "Sync Broker Symbols",
      disabled: loading },
    React.createElement("i", { className: "fas fa-sync-alt" })
    ),
    React.createElement("button", { onClick: onClose, className: "w-10 h-10 flex items-center justify-center text-muted hover:text-white transition-colors" },
    React.createElement("i", { className: "fas fa-times" })
    )
    ),
    React.createElement("div", { className: "flex items-center gap-1 bg-black/40 p-1 rounded-xl border border-white/5" },
    React.createElement("button", {
      onClick: () => setActiveTab('mt5'),
      className: `flex-1 py-1.5 text-[9px] font-black uppercase tracking-widest rounded-lg transition-all ${activeTab === 'mt5' ? 'bg-accent text-black shadow-lg shadow-accent/20' : 'text-muted hover:text-white hover:bg-white/5'}` },
    "MT5"
    ),
    React.createElement("button", {
      onClick: () => setActiveTab('tradovate'),
      className: `flex-1 py-1.5 text-[9px] font-black uppercase tracking-widest rounded-lg transition-all ${activeTab === 'tradovate' ? 'bg-accent text-black shadow-lg shadow-accent/20' : 'text-muted hover:text-white hover:bg-white/5'}` },
    "TRADOVATE"
    ),
    React.createElement("button", {
      onClick: () => setActiveTab('crypto'),
      className: `flex-1 py-1.5 text-[9px] font-black uppercase tracking-widest rounded-lg transition-all ${activeTab === 'crypto' ? 'bg-accent text-black shadow-lg shadow-accent/20' : 'text-muted hover:text-white hover:bg-white/5'}` },
    "CRYPTO"
    )
    )
    ),
    React.createElement("div", { className: "flex-1 overflow-y-auto custom-scrollbar bg-[#050505] flex flex-col" },
    loading ?
    React.createElement("div", { className: "flex-1 flex flex-col items-center justify-center gap-6 p-12" },
    React.createElement("div", { className: "relative" },
    React.createElement("div", { className: "w-16 h-16 border-4 border-accent/20 border-t-accent rounded-full animate-spin" }),
    React.createElement("div", { className: "absolute inset-0 flex items-center justify-center" },
    React.createElement("i", { className: "fas fa-sync-alt text-accent animate-pulse" })
    )
    ),
    React.createElement("div", { className: "text-center" },
    React.createElement("h3", { className: "text-white font-bold mb-1" }, "Scanning Symbols"),
    React.createElement("p", { className: "text-[10px] text-muted uppercase tracking-widest" },
    activeTab === 'mt5' ? 'Fetching Assets from MT5 Gateway...' : 'Fetching Markets from Exchange API...'
    )
    )
    ) :
    filtered.length > 0 ?
    React.createElement("table", { className: "w-full text-left border-collapse" },
    React.createElement("thead", { className: "sticky top-0 bg-[#151515] text-[10px] font-bold text-muted uppercase tracking-wider shadow-sm z-10" },
    React.createElement("tr", null,
    React.createElement("th", { className: "p-3 border-b border-white/5" }, "Symbol"),
    React.createElement("th", { className: "p-3 border-b border-white/5" }, "Description"),
    React.createElement("th", { className: "p-3 border-b border-white/5 text-right" }, "Group")
    )
    ),
    React.createElement("tbody", null,
    filtered.map((s) =>
    React.createElement("tr", {
      key: s.symbol,
      onClick: (e) => {
        e.preventDefault();
        e.stopPropagation();
        if (typeof s.symbol === 'string') {
          onSelect(s.symbol, activeTab);
        } else {
          console.error('[SymbolSearchModal] CRITICAL ERROR: Symbol is not a string!', s.symbol, s);
          if (s.symbol && s.symbol.toString) {
            console.warn('[SymbolSearchModal] Attempting string conversion...');
            onSelect(s.symbol.toString(), activeTab);
          } else {
            console.error('[SymbolSearchModal] Cannot recover. Ignoring selection.');
            return;
          }
        }
        onClose();
      },
      className: "border-b border-white/5 hover:bg-accent/10 cursor-pointer transition-colors group" },
    React.createElement("td", { className: "p-3" },
    React.createElement("div", { className: "flex items-center gap-2" },
    React.createElement("span", { className: "font-bold text-white group-hover:text-accent font-mono text-xs" },
    window.cleanSymbol(s.symbol)
    ),
    s.market_type && s.market_type !== 'UNKNOWN' &&
    React.createElement("span", { className: `px-1.5 py-0.5 rounded text-[8px] font-black tracking-wider ${s.market_type === 'SPOT' ? 'bg-blue-500/20 text-blue-400 border border-blue-500/30' :
      s.market_type === 'SWAP' ? 'bg-purple-500/20 text-purple-400 border border-purple-500/30' :
      s.market_type === 'FUTURE' ? 'bg-orange-500/20 text-orange-400 border border-orange-500/30' :
      'bg-gray-500/20 text-gray-400 border border-gray-500/30'}` },
    s.market_type
    )
    )
    ),
    React.createElement("td", { className: "p-3 text-[11px] text-gray-400 group-hover:text-white truncate max-w-[280px]" },
    s.description
    ),
    React.createElement("td", { className: "p-3 text-[10px] text-muted font-mono text-right uppercase" },
    s.group
    )
    )
    )
    )
    ) :
    React.createElement("div", { className: "flex-1 flex flex-col items-center justify-center p-12 text-center" },
    React.createElement("div", { className: "w-20 h-20 bg-red-500/5 rounded-full flex items-center justify-center mb-6 border border-red-500/10" },
    React.createElement("i", { className: "fas fa-exclamation-circle text-red-500/40 text-3xl" })
    ),
    React.createElement("h3", { className: "text-white font-bold mb-2" }, "No symbols detected"),
    React.createElement("p", { className: "text-xs text-muted max-w-[320px] mb-8 leading-relaxed" }, "Couldn't find any symbols for ",
    React.createElement("b", null, getPlatformDisplayName(activeTab)), ".", React.createElement("br", null),
    activeTab === 'mt5' ? 'Check if MetaTrader 5 is connected.' : activeTab === 'tradovate' ? 'Check if Tradovate API is connected.' : 'Check your API credentials in Settings.'
    ),
    React.createElement("button", {
      onClick: () => fetchSymbols(activeTab, true),
      className: "px-8 py-3 bg-accent text-black text-xs font-bold rounded hover:bg-white transition-all transform hover:scale-105 flex items-center gap-3 shadow-lg shadow-accent/20" },
    React.createElement("i", { className: "fas fa-sync-alt" }), "FORCE DEEP SYNC"
    )
    )
    ),
    React.createElement("div", { className: "p-2 bg-[#1a1a1a] border-t border-white/5 text-[10px] text-muted flex justify-between font-mono" },
    React.createElement("span", null, "MODE: ", getPlatformDisplayName(activeTab)),
    React.createElement("span", null, filtered.length, " SYMBOLS AVAILABLE")
    )
    )
    ));
};
window.SymbolSearchModal = SymbolSearchModal;