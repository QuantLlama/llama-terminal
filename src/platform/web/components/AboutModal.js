const AboutModal = ({ isOpen, onClose }) => {
  if (!isOpen) return null;
  return (
    React.createElement("div", { className: "fixed inset-0 z-[9999] flex items-center justify-center animate-[fadeIn_0.15s_ease-out]", onClick: onClose },
    React.createElement("div", { className: "absolute inset-0 bg-black/20 backdrop-blur-md" }),
    React.createElement("div", {
      className: "relative bg-[#0a0a0a] border border-white/10 rounded-lg w-[700px] max-h-[85vh] overflow-hidden shadow-2xl animate-[slideUp_0.2s_ease-out]",
      onClick: (e) => e.stopPropagation() },
    React.createElement("div", { className: "bg-gradient-to-r from-accent/10 to-transparent p-4 border-b border-white/5 flex items-center justify-between" },
    React.createElement("div", { className: "flex items-center gap-3" },
    React.createElement("img", { src: "/images/QuantumLLama.png", alt: "Quantum Llama", className: "w-8 h-8 opacity-90" }),
    React.createElement("div", null,
    React.createElement("h2", { className: "text-lg font-bold text-white" }, "Quantum Llama"),
    React.createElement("p", { className: "text-[10px] text-muted uppercase tracking-wider" }, "Professional Trading Platform")
    )
    ),
    React.createElement("button", {
      onClick: onClose,
      className: "w-8 h-8 flex items-center justify-center rounded hover:bg-white/5 text-muted hover:text-white transition-colors" },
    React.createElement("i", { className: "fas fa-times" })
    )
    ),
    React.createElement("div", { className: "p-6 overflow-y-auto max-h-[calc(85vh-80px)]" },
    React.createElement("div", { className: "grid grid-cols-[1fr_300px] gap-6" },
    React.createElement("div", { className: "space-y-5" },
    React.createElement("div", null,
    React.createElement("h3", { className: "text-sm font-bold text-white mb-2 flex items-center gap-2" },
    React.createElement("i", { className: "fas fa-info-circle text-accent text-xs" }), "About the Platform"
    ),
    React.createElement("p", { className: "text-xs text-muted leading-relaxed" }, "High-performance trading interface designed for professional use. Real-time Python backend with reactive frontend, WebSockets for low-latency streaming, and advanced tools for market analysis and execution."
    )
    ),
    React.createElement("div", null,
    React.createElement("h3", { className: "text-sm font-bold text-white mb-2 flex items-center gap-2" },
    React.createElement("i", { className: "fas fa-code text-accent text-xs" }), "Technologies"
    ),
    React.createElement("div", { className: "flex flex-wrap gap-1.5" },
    React.createElement("span", { className: "bg-blue-500/10 text-blue-400 text-[10px] font-bold px-2 py-1 rounded border border-blue-500/20" }, "Python"),
    React.createElement("span", { className: "bg-green-500/10 text-green-400 text-[10px] font-bold px-2 py-1 rounded border border-green-500/20" }, "FastAPI"),
    React.createElement("span", { className: "bg-purple-500/10 text-purple-400 text-[10px] font-bold px-2 py-1 rounded border border-purple-500/20" }, "WebSockets"),
    React.createElement("span", { className: "bg-sky-500/10 text-sky-400 text-[10px] font-bold px-2 py-1 rounded border border-sky-500/20" }, "React"),
    React.createElement("span", { className: "bg-teal-500/10 text-teal-400 text-[10px] font-bold px-2 py-1 rounded border border-teal-500/20" }, "TailwindCSS"),
    React.createElement("span", { className: "bg-yellow-500/10 text-yellow-400 text-[10px] font-bold px-2 py-1 rounded border border-yellow-500/20" }, "LightweightCharts"),
    React.createElement("span", { className: "bg-orange-500/10 text-orange-400 text-[10px] font-bold px-2 py-1 rounded border border-orange-500/20" }, "MT5")
    )
    ),
    React.createElement("div", null,
    React.createElement("h3", { className: "text-sm font-bold text-white mb-2 flex items-center gap-2" },
    React.createElement("i", { className: "fas fa-star text-accent text-xs" }), "Key Features"
    ),
    React.createElement("div", { className: "grid grid-cols-2 gap-2 text-[11px]" },
    React.createElement("div", { className: "flex items-center gap-2 text-muted" },
    React.createElement("i", { className: "fas fa-check text-green-500 text-[8px]" }), "Real-time market data"
    ),
    React.createElement("div", { className: "flex items-center gap-2 text-muted" },
    React.createElement("i", { className: "fas fa-check text-green-500 text-[8px]" }), "Advanced charting"
    ),
    React.createElement("div", { className: "flex items-center gap-2 text-muted" },
    React.createElement("i", { className: "fas fa-check text-green-500 text-[8px]" }), "Order flow analysis"
    ),
    React.createElement("div", { className: "flex items-center gap-2 text-muted" },
    React.createElement("i", { className: "fas fa-check text-green-500 text-[8px]" }), "Single Unified Connector (MT5)"
    ),
    React.createElement("div", { className: "flex items-center gap-2 text-muted" },
    React.createElement("i", { className: "fas fa-check text-green-500 text-[8px]" }), "Custom indicators"
    ),
    React.createElement("div", { className: "flex items-center gap-2 text-muted" },
    React.createElement("i", { className: "fas fa-check text-green-500 text-[8px]" }), "Algorithmic trading"
    )
    )
    )
    ),
    React.createElement("div", { className: "space-y-5" },
    React.createElement("div", { className: "bg-white/5 rounded-lg p-4 border border-white/10" },
    React.createElement("div", { className: "flex items-center gap-3 mb-3" },
    React.createElement("img", {
      src: "/images/MiAvatar.png",
      alt: "Developer",
      className: "w-12 h-12 rounded-full border-2 border-accent/30" }
    ),
    React.createElement("div", null,
    React.createElement("h3", { className: "text-sm font-bold text-white" }, "Developer"),
    React.createElement("p", { className: "text-[10px] text-accent" }, "Lead Architect")
    )
    ),
    React.createElement("p", { className: "text-[11px] text-muted leading-relaxed" }, "Specialized in quantitative trading systems, algorithmic strategies, and high-performance financial platforms."
    )
    ),
    React.createElement("div", null,
    React.createElement("h3", { className: "text-sm font-bold text-white mb-3 flex items-center gap-2" },
    React.createElement("i", { className: "fas fa-envelope text-accent text-xs" }), "Contact"
    ),
    React.createElement("div", { className: "space-y-2 text-[11px]" },
    React.createElement("a", {
      href: "https://llamaterminal.nbmsystemas.com",
      target: "_blank",
      rel: "noopener noreferrer",
      className: "flex items-center gap-2 text-muted hover:text-accent transition-colors group" },
    React.createElement("i", { className: "fas fa-globe w-4 text-center group-hover:scale-110 transition-transform" }),
    React.createElement("span", null, "llamaterminal.nbmsystemas.com")
    ),
    React.createElement("a", {
      href: "mailto:info@nbmsystemas.com",
      className: "flex items-center gap-2 text-muted hover:text-accent transition-colors group" },
    React.createElement("i", { className: "fas fa-envelope w-4 text-center group-hover:scale-110 transition-transform" }),
    React.createElement("span", null, "info@nbmsystemas.com")
    )
    )
    ),
    React.createElement("div", { className: "pt-3 border-t border-white/5" },
    React.createElement("div", { className: "flex items-center justify-between text-[10px]" },
    React.createElement("span", { className: "text-muted" }, "Version"),
    React.createElement("span", { className: "text-accent font-mono font-bold" }, "v2.0.0")
    ),
    React.createElement("div", { className: "flex items-center justify-between text-[10px] mt-1" },
    React.createElement("span", { className: "text-muted" }, "Build"),
    React.createElement("span", { className: "text-white/50 font-mono" }, "2026.02.05")
    )
    )
    )
    )
    ),
    React.createElement("div", { className: "bg-white/5 border-t border-white/5 px-6 py-3 flex items-center justify-between" },
    React.createElement("p", { className: "text-[10px] text-muted" }, "\xA9 2024-2026 Quantum Llama Systems"),
    React.createElement("div", { className: "flex items-center gap-2" },
    React.createElement("span", { className: "text-[10px] text-muted" }, "Made with"),
    React.createElement("i", { className: "fas fa-heart text-red-500 text-[10px] animate-pulse" }),
    React.createElement("span", { className: "text-[10px] text-muted" }, "for traders")
    )
    )
    )
    ));
};
window.AboutModal = AboutModal;