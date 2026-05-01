const TCM_TOKENS = {
  BG_MODAL: 'rgba(11, 11, 13, 0.95)',
  BG_INPUT: 'rgba(255, 255, 255, 0.02)',
  BG_TAB_ACTIVE: 'rgba(245, 158, 11, 0.05)',
  BORDER: 'rgba(255, 255, 255, 0.06)',
  TEXT_PRI: '#ffffff',
  TEXT_SEC: '#a1a1aa',
  TEXT_DIM: '#71717a',
  ACCENT: '#d97706',
  ACCENT_HOVER: '#b45309'
};
const FULL_DEFAULTS = {
  minSize: 0,
  buyColor: '#10b981',
  sellColor: '#f43f5e',
  neutralColor: '#71717a',
  whaleColor: '#f59e0b',
  showTime: true,
  showDelta: true,
  showTotal: true,
  showDeltaBar: true,
  totalMode: 'exchange',
  fontSize: '10px',
  rowHeight: '20px',
  maxRows: 200,
  whaleThreshold: 50,
  aggregationMs: 0,
  forceWindowMs: 30000
};
const TCM_Label = ({ children }) =>
React.createElement("label", { className: "text-[9px] font-black text-zinc-500 uppercase tracking-[0.2em] mb-2 block ml-1" },
children
);
const TCM_Hint = ({ children }) =>
React.createElement("p", { className: "text-[10px] text-zinc-600 mt-1.5 ml-1 leading-relaxed italic" },
children
);
const TCM_NumInput = ({ value, onChange, min, max, step, unit = '' }) => {
  return (
    React.createElement("div", { className: "relative group" },
    React.createElement("input", {
      type: "number",
      value: value,
      min: min, max: max, step: step,
      onChange: (e) => onChange(parseFloat(e.target.value)),
      className: "w-full bg-white/[0.02] border border-white/[0.06] rounded-xl px-4 py-2.5 text-[11px] font-mono text-zinc-200 outline-none focus:border-amber-500/40 focus:bg-white/[0.05] transition-all" }
    ),
    unit && React.createElement("span", { className: "absolute right-4 top-1/2 -translate-y-1/2 text-[8px] font-bold text-zinc-600 pointer-events-none uppercase tracking-widest" }, unit)
    ));
};
const TCM_Slider = ({ value, onChange, min, max, step }) => {
  return (
    React.createElement("div", { className: "relative pt-1" },
    React.createElement("input", {
      type: "range",
      min: min, max: max, step: step, value: value,
      onChange: (e) => onChange(Number(e.target.value)),
      className: "w-full h-1.5 bg-white/5 rounded-full appearance-none cursor-pointer accent-amber-500/80" }
    )
    ));
};
const TCM_Toggle = ({ label, value, onChange }) =>
React.createElement("div", {
  onClick: () => onChange(!value),
  className: `flex items-center justify-between p-3 rounded-xl border transition-all cursor-pointer select-none ${value ? 'bg-amber-500/5 border-amber-500/20' : 'bg-white/[0.02] border-white/[0.05] hover:bg-white/[0.04]'}` },
React.createElement("span", { className: `text-[10px] font-bold uppercase tracking-widest ${value ? 'text-amber-500/80' : 'text-zinc-500'}` }, label),
React.createElement("div", { className: `w-8 h-4 rounded-full relative transition-colors ${value ? 'bg-amber-500/80' : 'bg-white/10'}` },
React.createElement("div", { className: `absolute top-1 w-2 h-2 rounded-full bg-white transition-all ${value ? 'left-5' : 'left-1'}` })
)
);
const TCM_Segment = ({ value, onChange, options }) =>
React.createElement("div", { className: "flex bg-black/40 border border-white/5 rounded-xl p-1 gap-1" },
options.map((opt) =>
React.createElement("button", {
  key: opt.value,
  onClick: () => onChange(opt.value),
  className: `flex-1 py-1.5 text-[9px] font-black uppercase tracking-widest rounded-lg transition-all ${value === opt.value ? 'bg-white/10 text-white shadow-lg' : 'text-zinc-500 hover:text-zinc-300'}` },
opt.label
)
)
);
const TCM_ColorPicker = ({ label, value, onChange }) =>
React.createElement("div", { className: "space-y-2" },
React.createElement(TCM_Label, null, label),
React.createElement("div", { className: "flex items-center gap-3 bg-white/[0.02] border border-white/[0.06] rounded-xl p-2.5 group hover:border-white/20 transition-all" },
React.createElement("div", { className: "relative w-6 h-6 rounded-lg overflow-hidden border border-white/10 shadow-inner group-hover:scale-105 transition-transform" },
React.createElement("input", {
  type: "color", value: value,
  onChange: (e) => onChange(e.target.value),
  className: "absolute inset-[-4px] w-[calc(100%+8px)] h-[calc(100%+8px)] cursor-pointer" }
)
),
React.createElement("span", { className: "text-[10px] font-mono text-zinc-400 uppercase tracking-tighter" }, value)
)
);
const TCM_Section = ({ label, children }) =>
React.createElement("div", { className: "space-y-5" },
React.createElement("div", { className: "flex items-center gap-4" },
React.createElement("span", { className: "text-[9px] font-black text-amber-500/70 tracking-[0.25em] uppercase whitespace-nowrap" }, label),
React.createElement("div", { className: "h-px flex-1 bg-white/[0.05]" })
),
React.createElement("div", { className: "space-y-5" },
children
)
);
const TapeConfigModal = ({ isOpen, onClose, config, onUpdate, title }) => {
  const { useState, useEffect, useCallback, useRef } = React;
  const [local, setLocal] = useState(() => ({ ...FULL_DEFAULTS, ...config }));
  const [activeTab, setActiveTab] = useState('FILTER');
  const [pos, setPos] = useState({ x: 0, y: 0 });
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
      setPos({ x: (window.innerWidth - 450) / 2, y: 150 });
      setLocal({ ...FULL_DEFAULTS, ...config });
    }
  }, [isOpen]);
  const updateValue = (key, val) => setLocal((prev) => ({ ...prev, [key]: val }));
  if (!isOpen) return null;
  const handleSave = () => {onUpdate(local);onClose();};
  return (
    React.createElement("div", { className: "fixed inset-0 z-[10000] pointer-events-none overflow-hidden font-sans" },
    React.createElement("div", {
      ref: dragRef,
      style: { position: 'absolute', left: `${pos.x}px`, top: `${pos.y}px`, width: '450px', maxHeight: '80vh' },
      className: "bg-[#0b0b0d]/95 border border-white/10 rounded-2xl shadow-[0_40px_100px_rgba(0,0,0,0.8)] flex flex-col pointer-events-auto backdrop-blur-3xl animate-in fade-in zoom-in duration-300 overflow-hidden",
      onMouseDown: handleMouseDown },
    React.createElement("div", { className: "drag-handle flex items-center justify-between px-6 py-4 bg-white/5 cursor-move border-b border-white/5" },
    React.createElement("div", { className: "flex items-center gap-4" },
    React.createElement("div", { className: "w-2.5 h-2.5 rounded-full bg-amber-500/80 shadow-[0_0_10px_rgba(245,158,11,0.4)]" }),
    React.createElement("div", null,
    React.createElement("h3", { className: "text-[10px] font-black text-white tracking-[0.15em] uppercase" }, "Tape Architecture"),
    React.createElement("p", { className: "text-[9px] text-zinc-500 uppercase tracking-widest mt-0.5" }, title)
    )
    ),
    React.createElement("button", { onClick: onClose, className: "w-8 h-8 flex items-center justify-center rounded-xl bg-white/5 hover:bg-white/10 text-zinc-400 hover:text-white transition-all" },
    React.createElement("i", { className: "fas fa-times text-xs" })
    )
    ),
    React.createElement("div", { className: "flex px-4 bg-black/40 border-b border-white/5" },
    ['FILTER', 'DISPLAY', 'COLORS', 'ADVANCED'].map((tab) =>
    React.createElement("button", {
      key: tab,
      onClick: () => setActiveTab(tab),
      className: `flex-1 py-4 text-[10px] font-black uppercase tracking-widest transition-all ${activeTab === tab ? 'text-amber-500/80 border-b-2 border-amber-500/50 bg-amber-500/5' : 'text-zinc-500 border-b-2 border-transparent hover:text-zinc-300'}` },
    tab
    )
    )
    ),
    React.createElement("div", { className: "flex-1 overflow-y-auto p-7 space-y-9 bg-black/20 custom-scrollbar", style: { maxHeight: '55vh' } },
    activeTab === 'FILTER' &&
    React.createElement("div", { className: "space-y-9 animate-in fade-in slide-in-from-left-2 duration-300" },
    React.createElement(TCM_Section, { label: "Liquidity Analysis" },
    React.createElement("div", null,
    React.createElement(TCM_Label, null, "Minimum Execution Size"),
    React.createElement(TCM_NumInput, { value: local.minSize, onChange: (v) => updateValue('minSize', v), min: 0, step: 1, unit: "Lots" }),
    React.createElement(TCM_Hint, null, "Filters out background noise. Higher values isolate institutional flow.")
    ),
    React.createElement("div", null,
    React.createElement(TCM_Label, null, "Institutional Threshold"),
    React.createElement(TCM_NumInput, { value: local.whaleThreshold, onChange: (v) => updateValue('whaleThreshold', v), min: 1, step: 1, unit: "Lots" }),
    React.createElement(TCM_Hint, null, "Threshold for visual alerts on high-conviction prints.")
    )
    ),
    React.createElement(TCM_Section, { label: "Data Synthesis" },
    React.createElement("div", null,
    React.createElement("div", { className: "flex justify-between items-center mb-3" },
    React.createElement(TCM_Label, null, "Aggregation Window"),
    React.createElement("span", { className: "text-[10px] font-mono text-white/40 bg-white/5 px-2 py-0.5 rounded-lg border border-white/5" }, local.aggregationMs, "ms")
    ),
    React.createElement(TCM_Slider, { value: local.aggregationMs, onChange: (v) => updateValue('aggregationMs', v), min: 0, max: 1000, step: 50 }),
    React.createElement(TCM_Hint, null, "Merges rapid consecutive trades at the same price into a simplified block.")
    )
    )
    ),
    activeTab === 'DISPLAY' &&
    React.createElement("div", { className: "space-y-9 animate-in fade-in slide-in-from-left-2 duration-300" },
    React.createElement(TCM_Section, { label: "Visual Structure" },
    React.createElement("div", { className: "grid grid-cols-2 gap-3" },
    React.createElement(TCM_Toggle, { label: "Timestamp", value: local.showTime, onChange: (v) => updateValue('showTime', v) }),
    React.createElement(TCM_Toggle, { label: "Session \u0394", value: local.showDelta, onChange: (v) => updateValue('showDelta', v) }),
    React.createElement(TCM_Toggle, { label: "Total Vol", value: local.showTotal, onChange: (v) => updateValue('showTotal', v) }),
    React.createElement(TCM_Toggle, { label: "Bias Bar", value: local.showDeltaBar, onChange: (v) => updateValue('showDeltaBar', v) })
    )
    ),
    React.createElement(TCM_Section, { label: "Typography" },
    React.createElement("div", { className: "grid grid-cols-2 gap-5" },
    React.createElement("div", null,
    React.createElement(TCM_Label, null, "Font Precision"),
    React.createElement(TCM_Segment, {
      value: local.fontSize,
      onChange: (v) => updateValue('fontSize', v),
      options: [{ label: '9px', value: '9px' }, { label: '10px', value: '10px' }, { label: '11px', value: '11px' }, { label: '12px', value: '12px' }] }
    )
    ),
    React.createElement("div", null,
    React.createElement(TCM_Label, null, "Row Spacing"),
    React.createElement(TCM_Segment, {
      value: local.rowHeight,
      onChange: (v) => updateValue('rowHeight', v),
      options: [{ label: 'S', value: '18px' }, { label: 'M', value: '20px' }, { label: 'L', value: '24px' }] }
    )
    )
    )
    )
    ),
    activeTab === 'COLORS' &&
    React.createElement("div", { className: "space-y-9 animate-in fade-in slide-in-from-left-2 duration-300" },
    React.createElement(TCM_Section, { label: "Auction Side Matrix" },
    React.createElement("div", { className: "grid grid-cols-2 gap-x-8 gap-y-5" },
    React.createElement(TCM_ColorPicker, { label: "Auction (Buy)", value: local.buyColor, onChange: (v) => updateValue('buyColor', v) }),
    React.createElement(TCM_ColorPicker, { label: "Auction (Sell)", value: local.sellColor, onChange: (v) => updateValue('sellColor', v) }),
    React.createElement(TCM_ColorPicker, { label: "Neutral / Cross", value: local.neutralColor, onChange: (v) => updateValue('neutralColor', v) }),
    React.createElement(TCM_ColorPicker, { label: "Institutional", value: local.whaleColor, onChange: (v) => updateValue('whaleColor', v) })
    )
    )
    ),
    activeTab === 'ADVANCED' &&
    React.createElement("div", { className: "space-y-9 animate-in fade-in slide-in-from-left-2 duration-300" },
    React.createElement(TCM_Section, { label: "Volume Metrics" },
    React.createElement(TCM_Segment, {
      value: local.totalMode, onChange: (v) => updateValue('totalMode', v),
      options: [
      { value: 'exchange', label: 'Daily' },
      { value: 'session', label: 'Local' },
      { value: 'delta', label: 'Delta' }] }
    ),
    React.createElement(TCM_Hint, null, "Controls how cumulative volume is computed across the session.")
    ),
    React.createElement(TCM_Section, { label: "Execution Pipeline" },
    React.createElement("div", null,
    React.createElement(TCM_Label, null, "Buffer Depth"),
    React.createElement(TCM_NumInput, { value: local.maxRows, onChange: (v) => updateValue('maxRows', v), min: 50, max: 1000, step: 50, unit: "Entries" })
    ),
    React.createElement("div", null,
    React.createElement(TCM_Label, null, "P95 Statistical Window"),
    React.createElement(TCM_NumInput, { value: local.forceWindowMs, onChange: (v) => updateValue('forceWindowMs', v), min: 1000, max: 60000, step: 1000, unit: "ms" }),
    React.createElement(TCM_Hint, null, "Statistical window for computing relative trade force.")
    )
    )
    )
    ),
    React.createElement("div", { className: "p-6 bg-white/5 border-t border-white/5 flex gap-4" },
    React.createElement("button", { onClick: onClose, className: "flex-1 py-3 text-[10px] font-black uppercase tracking-widest text-zinc-500 hover:text-white hover:bg-white/5 rounded-xl transition-all" }, "Cancel"),
    React.createElement("button", { onClick: handleSave, className: "flex-[2] py-3 bg-amber-600/80 text-white text-[10px] font-black uppercase tracking-widest rounded-xl hover:bg-amber-500/80 hover:scale-[1.02] active:scale-95 transition-all shadow-[0_0_30px_rgba(245,158,11,0.2)]" }, "Apply Strategy")
    )
    )
    ));
};
window.TapeConfigModal = TapeConfigModal;