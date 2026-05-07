const LiveDashboardModal = ({ isOpen, onClose }) => {
  if (!isOpen) return null;
  return (
    React.createElement("div", { className: "fixed inset-0 bg-black/25 z-[9999] flex items-center justify-center backdrop-blur-lg" },
    React.createElement("div", { className: "bg-[#0a0a0a] w-[95vw] h-[95vh] rounded-lg shadow-2xl flex flex-col overflow-hidden relative border border-purple-500/30" },
    React.createElement("div", { className: "absolute top-2 right-2 z-50 flex gap-2" },
    React.createElement("button", { onClick: onClose, className: "text-white/80 hover:text-white bg-red-600/40 hover:bg-red-600/80 w-6 h-6 flex items-center justify-center rounded-full transition-all shadow-lg border border-red-500/30" },
    React.createElement("i", { className: "fas fa-times text-xs" })
    )
    ),
    React.createElement("iframe", {
      src: "/src/live/live_dashboard.html",
      className: "w-full h-full border-none",
      title: "Live Dashboard" }
    )
    )
    ));
};
window.LiveDashboardModal = LiveDashboardModal;