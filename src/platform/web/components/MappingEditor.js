const { useState, useEffect, useRef } = React;
const MappingEditor = ({ isOpen, onClose }) => {
  const [platform, setPlatform] = useState("mt5");
  const [data, setData] = useState({});
  const [loading, setLoading] = useState(false);
  const [editKey, setEditKey] = useState(null);
  const [newCat, setNewCat] = useState("Futures");
  const [newSys, setNewSys] = useState("");
  const [newBroker, setNewBroker] = useState("");
  const [pos, setPos] = useState({ x: 100, y: 100 });
  const [isDragging, setIsDragging] = useState(false);
  const dragRef = useRef(null);
  const offsetRef = useRef({ x: 0, y: 0 });
  const handleMouseDown = (e) => {
    if (e.target.closest('.drag-handle')) {
      setIsDragging(true);
      const rect = dragRef.current.getBoundingClientRect();
      offsetRef.current = { x: e.clientX - rect.left, y: e.clientY - rect.top };
    }
  };
  useEffect(() => {
    if (!isDragging) return;
    const move = (e) => setPos({ x: e.clientX - offsetRef.current.x, y: e.clientY - offsetRef.current.y });
    const stop = () => setIsDragging(false);
    window.addEventListener('mousemove', move);
    window.addEventListener('mouseup', stop);
    return () => {window.removeEventListener('mousemove', move);window.removeEventListener('mouseup', stop);};
  }, [isDragging]);
  useEffect(() => {
    if (isOpen) {
      setPos({ x: (window.innerWidth - 650) / 2, y: 150 });
      load();
    }
  }, [isOpen]);
  const load = (silent = false) => {
    if (!silent) setLoading(true);
    fetch(`/api/mapping?platform=${platform}`).
    then((r) => r.json()).
    then((d) => {setData(d.mapping || d);setLoading(false);}).
    catch((e) => {console.error(e);setLoading(false);});
  };
  useEffect(() => {if (isOpen) load();}, [platform]);
  const save = async (newData) => {
    await fetch(`/api/mapping?platform=${platform}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(newData || data)
    });
    load(true);
  };
  const handleUpdate = (cat, ticker, val) => {
    const newData = { ...data };
    newData[cat][ticker] = val;
    setData(newData);
    save(newData);
    setEditKey(null);
  };
  const handleAdd = () => {
    if (!newSys || !newBroker) return;
    const newData = { ...data };
    if (!newData[newCat]) newData[newCat] = {};
    newData[newCat][newSys] = newBroker;
    setData(newData);
    save(newData);
    setNewSys("");setNewBroker("");
  };
  const handleDelete = (cat, ticker) => {
    if (!confirm(`Delete mapping for ${ticker}?`)) return;
    const newData = { ...data };
    delete newData[cat][ticker];
    setData(newData);
    save(newData);
  };
  if (!isOpen) return null;
  return (
    React.createElement("div", { className: "fixed inset-0 z-[10000] pointer-events-none overflow-hidden font-sans" },
    React.createElement("div", {
      ref: dragRef,
      style: { position: 'absolute', left: `${pos.x}px`, top: `${pos.y}px`, width: '650px', maxHeight: '75vh' },
      className: "bg-[#0b0b0d]/95 border border-white/10 rounded-2xl shadow-[0_30px_80px_rgba(0,0,0,0.7)] overflow-hidden flex flex-col pointer-events-auto backdrop-blur-3xl animate-in fade-in zoom-in duration-300",
      onMouseDown: handleMouseDown },
    React.createElement("div", { className: "drag-handle flex items-center justify-between px-6 py-4 bg-white/5 cursor-move border-b border-white/5" },
    React.createElement("div", { className: "flex items-center gap-4" },
    React.createElement("div", { className: "w-2.5 h-2.5 rounded-full bg-amber-500/80 shadow-[0_0_10px_rgba(245,158,11,0.4)]" }),
    React.createElement("div", null,
    React.createElement("h3", { className: "text-[10px] font-black text-white tracking-[0.15em] uppercase" }, "Symbol Architecture"),
    React.createElement("p", { className: "text-[9px] text-zinc-500 uppercase tracking-widest mt-0.5" }, "Asset Mapping Console")
    )
    ),
    React.createElement("button", { onClick: onClose, className: "w-8 h-8 flex items-center justify-center rounded-xl bg-white/5 hover:bg-white/10 text-zinc-400 hover:text-white transition-all" },
    React.createElement("i", { className: "fas fa-times text-xs" })
    )
    ),
    React.createElement("div", { className: "flex bg-white/5 p-1 mx-6 mb-2 rounded-xl border border-white/5" },
    ['mt5', 'tradovate', 'nt8', 'crypto'].map((p) =>
    React.createElement("button", {
      key: p,
      onClick: () => setPlatform(p),
      className: `flex-1 py-1.5 text-[9px] font-black uppercase tracking-[0.2em] rounded-lg transition-all ${platform === p ? 'bg-amber-500 text-black shadow-lg shadow-amber-500/20' : 'text-zinc-500 hover:text-white hover:bg-white/5'}` },
    p === 'mt5' ? 'MT5' : p === 'tradovate' ? 'TRADOVATE' : p === 'nt8' ? 'NINJATRADER' : 'CRYPTO'
    )
    )
    ),
    React.createElement("div", { className: "flex-1 overflow-y-auto p-6 no-scrollbar bg-black/20", style: { maxHeight: '50vh' } },
    loading && Object.keys(data).length === 0 ?
    React.createElement("div", { className: "flex items-center justify-center h-48" },
    React.createElement("div", { className: "w-6 h-6 border-2 border-amber-500/20 border-t-amber-500/80 rounded-full animate-spin" })
    ) :
    Object.keys(data).length === 0 ?
    React.createElement("div", { className: "text-center py-12 text-zinc-600 text-[10px] uppercase tracking-[0.2em] italic" }, "No active mappings") :
    Object.keys(data).map((cat) =>
    React.createElement("div", { key: cat, className: `mb-8 animate-in fade-in slide-in-from-bottom-2 duration-500 ${loading ? 'opacity-50' : ''}` },
    React.createElement("div", { className: "flex items-center gap-4 mb-4" },
    React.createElement("h4", { className: "text-[9px] font-black text-amber-500/70 uppercase tracking-[0.25em] whitespace-nowrap" }, cat),
    React.createElement("div", { className: "h-px flex-1 bg-white/[0.05]" })
    ),
    React.createElement("div", { className: "grid gap-1.5" },
    React.createElement("div", { className: "flex text-[9px] font-black text-zinc-600 uppercase tracking-widest px-4 pb-1" },
    React.createElement("span", { className: "w-[45%]" }, "Source System"),
    React.createElement("span", { className: "w-[45%]" }, "Broker Destination")
    ),
    Object.entries(data[cat]).map(([ticker, val]) =>
    React.createElement("div", { key: ticker, className: "flex items-center px-4 py-2.5 bg-white/[0.02] border border-white/5 rounded-xl hover:border-white/10 hover:bg-white/[0.04] transition-all group" },
    React.createElement("span", { className: "w-[45%] font-mono text-[11px] text-zinc-300" }, ticker),
    React.createElement("div", { className: "w-[45%] font-mono text-[11px] text-amber-400/90" },
    editKey?.cat === cat && editKey?.ticker === ticker ?
    React.createElement("input", {
      autoFocus: true,
      className: "bg-black/60 border border-amber-500/30 text-amber-400 px-3 py-1 w-full rounded-lg outline-none focus:border-amber-500/50",
      defaultValue: val,
      onBlur: (e) => handleUpdate(cat, ticker, e.target.value),
      onKeyDown: (e) => {if (e.key === 'Enter') handleUpdate(cat, ticker, e.currentTarget.value);} }
    ) :
    React.createElement("span", { onClick: () => setEditKey({ cat, ticker }), className: "cursor-pointer hover:text-white transition-colors border-b border-amber-500/20 border-dashed" },
    typeof val === 'object' ? JSON.stringify(val) : val
    )
    ),
    React.createElement("div", { className: "w-[10%] text-right opacity-0 group-hover:opacity-100 transition-opacity" },
    React.createElement("button", { onClick: () => handleDelete(cat, ticker), className: "text-zinc-600 hover:text-red-400 transition-colors p-1.5" },
    React.createElement("i", { className: "fas fa-trash-alt text-[10px]" })
    )
    )
    )
    )
    )
    )
    )
    ),
    React.createElement("div", { className: "p-6 bg-white/5 border-t border-white/5" },
    React.createElement("h4", { className: "text-[9px] font-black text-zinc-500 uppercase tracking-[0.2em] mb-4" }, "Establish New Linkage"),
    React.createElement("div", { className: "flex gap-2.5 h-10" },
    React.createElement("select", {
      value: newCat,
      onChange: (e) => setNewCat(e.target.value),
      className: "bg-black/40 border border-white/10 text-zinc-300 text-[10px] font-bold tracking-tight rounded-xl px-4 outline-none focus:border-amber-500/50 hover:bg-white/5 transition-all w-32" },
    ['Futures', 'Stocks', 'ETF', 'Crypto', 'Forex'].map((c) => React.createElement("option", { key: c, value: c }, c))
    ),
    React.createElement("input", {
      placeholder: "SOURCE TICKER",
      value: newSys,
      onChange: (e) => setNewSys(e.target.value),
      className: "bg-black/40 border border-white/10 text-white text-[10px] font-mono rounded-xl px-4 outline-none focus:border-amber-500/50 flex-1 placeholder:text-zinc-700 transition-all" }
    ),
    React.createElement("input", {
      placeholder: "DEST TICKER",
      value: newBroker,
      onChange: (e) => setNewBroker(e.target.value),
      className: "bg-black/40 border border-white/10 text-white text-[10px] font-mono rounded-xl px-4 outline-none focus:border-amber-500/50 flex-1 placeholder:text-zinc-700 transition-all" }
    ),
    React.createElement("button", {
      onClick: handleAdd,
      className: "bg-amber-600/80 text-white font-black text-[10px] tracking-[0.1em] px-6 rounded-xl hover:bg-amber-500/80 hover:scale-[1.02] active:scale-95 transition-all shadow-[0_0_20px_rgba(245,158,11,0.2)]" },
    "LINK"
    )
    )
    )
    )
    ));
};
window.MappingEditor = MappingEditor;