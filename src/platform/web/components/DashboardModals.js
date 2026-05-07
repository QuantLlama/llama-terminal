const DashboardModal = ({ isOpen, onClose }) => {
  const [html, setHtml] = React.useState("");
  React.useEffect(() => {
    if (isOpen) {
      fetch('/api/dashboard').
      then((r) => r.text()).
      then((d) => setHtml(d)).
      catch((e) => console.error(e));
    }
  }, [isOpen]);
  if (!isOpen) return null;
  return (
    React.createElement("div", { className: "fixed inset-0 bg-black/40 z-[10000] flex items-center justify-center backdrop-blur-2xl animate-in fade-in duration-300" },
    React.createElement("div", { className: "bg-[#0b0b0d]/95 w-[96vw] h-[96vh] rounded-2xl shadow-[0_40px_100px_rgba(0,0,0,0.8)] flex flex-col overflow-hidden relative border border-white/10" },
    React.createElement("div", { className: "flex items-center justify-between px-6 py-4 bg-white/5 border-b border-white/5" },
    React.createElement("div", { className: "flex items-center gap-4" },
    React.createElement("div", { className: "w-2.5 h-2.5 rounded-full bg-zinc-500" }),
    React.createElement("h2", { className: "text-[10px] font-black text-white uppercase tracking-[0.2em]" }, "Static Dashboard View")
    ),
    React.createElement("button", { onClick: onClose, className: "w-8 h-8 flex items-center justify-center rounded-xl bg-white/5 hover:bg-white/10 text-zinc-400 hover:text-white transition-all" },
    React.createElement("i", { className: "fas fa-times text-xs" })
    )
    ),
    React.createElement("div", { className: "flex-1 bg-black/20" },
    React.createElement("iframe", { srcDoc: html, className: "w-full h-full border-none", title: "Dashboard" })
    )
    )
    ));
};
const LiveDashboardModal = ({ isOpen, onClose }) => {
  if (!isOpen) return null;
  return (
    React.createElement("div", { className: "fixed inset-0 bg-black/40 z-[10000] flex items-center justify-center backdrop-blur-3xl animate-in fade-in duration-300" },
    React.createElement("div", { className: "bg-[#0b0b0d]/95 w-[96vw] h-[96vh] rounded-2xl shadow-[0_40px_100px_rgba(0,0,0,0.8)] flex flex-col overflow-hidden relative border border-white/10" },
    React.createElement("div", { className: "flex items-center justify-between px-6 py-4 bg-white/5 border-b border-white/5 backdrop-blur-md" },
    React.createElement("div", { className: "flex items-center gap-4" },
    React.createElement("div", { className: "w-2.5 h-2.5 rounded-full bg-amber-500/80 animate-pulse shadow-[0_0_15px_rgba(245,158,11,0.5)]" }),
    React.createElement("div", null,
    React.createElement("h2", { className: "text-[11px] font-black text-white uppercase tracking-[0.25em]" }, "Quantum Live Intelligence"),
    React.createElement("p", { className: "text-[9px] text-zinc-500 font-mono uppercase tracking-widest mt-0.5" }, "Real-Time Core Stream Active")
    )
    ),
    React.createElement("div", { className: "flex items-center gap-4" },
    React.createElement("div", { className: "hidden md:flex items-center gap-2 px-4 py-1.5 rounded-full bg-amber-500/10 border border-amber-500/20" },
    React.createElement("span", { className: "w-1.5 h-1.5 rounded-full bg-amber-400 animate-ping" }),
    React.createElement("span", { className: "text-[9px] font-black text-amber-500/80 uppercase tracking-widest" }, "Neural Link Active")
    ),
    React.createElement("button", {
      onClick: onClose,
      className: "w-10 h-10 flex items-center justify-center rounded-2xl bg-white/5 hover:bg-white/10 text-zinc-400 hover:text-white transition-all border border-white/5" },
    React.createElement("i", { className: "fas fa-times text-sm" })
    )
    )
    ),
    React.createElement("div", { className: "flex-1 bg-black/20" },
    React.createElement("iframe", {
      src: "/src/live/live_dashboard.html",
      className: "w-full h-full border-none",
      title: "Live Dashboard" }
    )
    )
    )
    ));
};
const DashboardModals = ({
  dashOpen, setDashOpen,
  liveDashOpen, setLiveDashOpen,
  mappingOpen, setMappingOpen,
  cleanConfirmOpen, setCleanConfirmOpen
}) => {
  return (
    React.createElement(React.Fragment, null,
    React.createElement(DashboardModal, { isOpen: dashOpen, onClose: () => setDashOpen(false) }),
    React.createElement(LiveDashboardModal, { isOpen: liveDashOpen, onClose: () => setLiveDashOpen(false) }),
    window.MappingEditor && React.createElement(window.MappingEditor, { isOpen: mappingOpen, onClose: () => setMappingOpen(false) })
    ));
};
window.DashboardModal = DashboardModal;
window.LiveDashboardModal = LiveDashboardModal;
window.DashboardModals = DashboardModals;