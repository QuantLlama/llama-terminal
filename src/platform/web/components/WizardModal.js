const { useState, useEffect, useRef } = React;
const WizardModal = ({ isOpen, onClose, title, steps, onComplete }) => {
  const [step, setStep] = useState(0);
  const [data, setData] = useState({});
  const [pos, setPos] = useState({ x: 0, y: 0 });
  const [isDragging, setIsDragging] = useState(false);
  const dragRef = useRef(null);
  const offsetRef = useRef({ x: 0, y: 0 });
  const handleMouseDown = (e) => {
    if (e.target.closest('.drag-handle')) {
      setIsDragging(true);
      const rect = dragRef.current.getBoundingClientRect();
      offsetRef.current = {
        x: e.clientX - rect.left,
        y: e.clientY - rect.top
      };
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
      setStep(0);
      setData({});
      setPos({ x: (window.innerWidth - 500) / 2, y: 120 });
    }
  }, [isOpen]);
  if (!isOpen) return null;
  const currentStep = steps[step];
  const isLast = step === steps.length - 1;
  const handleNext = () => {
    if (isLast) {
      onComplete(data);
      onClose();
    } else {
      setStep((s) => s + 1);
    }
  };
  return (
    React.createElement("div", { className: "fixed inset-0 z-[10000] pointer-events-none overflow-hidden font-sans" },
    React.createElement("div", {
      ref: dragRef,
      style: { position: 'absolute', left: `${pos.x}px`, top: `${pos.y}px`, width: '500px' },
      className: "bg-[#0b0b0d]/95 border border-white/10 rounded-2xl shadow-[0_40px_100px_rgba(0,0,0,0.8)] flex flex-col pointer-events-auto backdrop-blur-3xl animate-in fade-in zoom-in duration-300 overflow-hidden",
      onMouseDown: handleMouseDown },
    React.createElement("div", { className: "drag-handle flex items-center justify-between px-6 py-4 bg-white/5 cursor-move border-b border-white/5" },
    React.createElement("div", { className: "flex items-center gap-4" },
    React.createElement("div", { className: "w-2.5 h-2.5 rounded-full bg-amber-500/80 shadow-[0_0_10px_rgba(245,158,11,0.4)]" }),
    React.createElement("div", null,
    React.createElement("h3", { className: "text-[10px] font-black text-white tracking-[0.15em] uppercase" }, title),
    React.createElement("p", { className: "text-[9px] text-zinc-500 uppercase tracking-widest mt-0.5" }, "Step ",
    step + 1, " of ", steps.length, " \u2014 Synthesis Phase"
    )
    )
    ),
    React.createElement("button", { onClick: onClose, className: "w-8 h-8 flex items-center justify-center rounded-xl bg-white/5 hover:bg-white/10 text-zinc-400 hover:text-white transition-all" },
    React.createElement("i", { className: "fas fa-times text-xs" })
    )
    ),
    React.createElement("div", { className: "p-8 flex-1 min-h-[300px] bg-black/20" },
    React.createElement("div", { className: "mb-8" },
    React.createElement("h4", { className: "text-xl font-bold bg-clip-text text-transparent bg-gradient-to-r from-amber-200 to-zinc-400" },
    currentStep.label
    ),
    currentStep.description &&
    React.createElement("p", { className: "text-[11px] text-zinc-500 mt-2 leading-relaxed italic" },
    currentStep.description
    )
    ),
    React.createElement("div", { className: "animate-in fade-in slide-in-from-bottom-2 duration-500" },
    currentStep.render(data, (keyOrObj, val) => {
      if (typeof keyOrObj === 'object' && keyOrObj !== null) {
        setData((prev) => ({ ...prev, ...keyOrObj }));
      } else {
        setData((prev) => ({ ...prev, [keyOrObj]: val }));
      }
    })
    )
    ),
    React.createElement("div", { className: "p-6 bg-white/5 border-t border-white/5 flex gap-4" },
    React.createElement("button", {
      onClick: step === 0 ? onClose : () => setStep((s) => s - 1),
      className: "flex-1 py-3 text-[10px] font-black uppercase tracking-widest text-zinc-500 hover:text-white hover:bg-white/5 rounded-xl transition-all" },
    step === 0 ? 'Cancel Operation' : 'Reverse Step'
    ),
    React.createElement("button", {
      onClick: handleNext,
      className: "flex-[2] py-3 bg-amber-600/80 text-white text-[10px] font-black uppercase tracking-widest rounded-xl hover:bg-amber-500/80 hover:scale-[1.02] active:scale-95 transition-all shadow-[0_0_30px_rgba(245,158,11,0.2)] flex items-center justify-center gap-2" },
    isLast ?
    React.createElement(React.Fragment, null,
    React.createElement("i", { className: "fas fa-bolt" }), " Execute Matrix"
    ) :
    React.createElement(React.Fragment, null, "Proceed ",
    React.createElement("i", { className: "fas fa-chevron-right text-[8px]" })
    )
    )
    )
    )
    ));
};
window.WizardModal = WizardModal;