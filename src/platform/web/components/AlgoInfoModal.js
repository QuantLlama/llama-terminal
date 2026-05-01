window.AlgoHelpers = {
  "FourierCycle": {
    title: "Interpretación: Fourier Cycle",
    desc: "Este algoritmo descompone el precio en ondas cíclicas para proyectar movimientos futuros.",
    items: [
    { icon: "fa-water", color: "text-cyan-400", label: "Línea Cyan (Reconstrucción)", text: "Muestra qué tan bien el algoritmo 'entiende' el mercado actual. Si sigue de cerca al precio real, la confianza es alta." },
    { icon: "fa-bolt", color: "text-yellow-400", label: "Línea Amarilla (Proyección)", text: "La predicción futura del precio basada en la suma de ciclos activos. Úsala para anticipar giros." },
    { icon: "fa-wave-square", color: "text-green-400", label: "Bandas Armónicas", text: "Zonas de soporte/resistencia dinámicas. El precio tiende a rebotar en estas bandas." }]
  },
  "EvolutionaryGAN": {
    title: "Interpretación: Evolutionary GAN",
    desc: "Red Neuronal Profunda entrenada para detectar patrones secuenciales complejos.",
    items: [
    { icon: "fa-brain", color: "text-purple-400", label: "Señal AI", text: "Basada en probabilidad. BUY > 0.6, SELL < 0.4." },
    { icon: "fa-chart-line", color: "text-blue-400", label: "Predicción de Precio", text: "El modelo intenta predecir el cierre de la siguiente vela." }]
  }
};
const AlgoInfoModal = () => {
  const { useState, useEffect, useRef, useMemo, useCallback } = React;
  const [isOpen, setIsOpen] = useState(false);
  const [content, setContent] = useState(null);
  useEffect(() => {
    const handleOpen = (e) => {
      setContent(e.detail);
      setIsOpen(true);
    };
    window.addEventListener('open_algo_info', handleOpen);
    return () => window.removeEventListener('open_algo_info', handleOpen);
  }, []);
  if (!isOpen || !content) return null;
  return (
    React.createElement("div", { className: "fixed inset-0 z-[9999] flex items-center justify-center bg-black/80 backdrop-blur-sm animate-in fade-in duration-200" },
    React.createElement("div", { className: "bg-[#111] border border-white/10 rounded-xl w-[500px] max-w-[90vw] shadow-2xl relative overflow-hidden animate-in zoom-in-95 duration-200" },
    React.createElement("div", { className: "p-5 border-b border-white/5 bg-gradient-to-r from-white/5 to-transparent" },
    React.createElement("div", { className: "flex justify-between items-start" },
    React.createElement("div", null,
    React.createElement("h3", { className: "text-lg font-bold text-white mb-1 flex items-center gap-2" },
    React.createElement("i", { className: "fas fa-info-circle text-accent" }),
    content.title
    ),
    React.createElement("p", { className: "text-xs text-muted leading-relaxed" }, content.desc)
    ),
    React.createElement("button", { onClick: () => setIsOpen(false), className: "text-white/50 hover:text-white transition-colors" },
    React.createElement("i", { className: "fas fa-times text-lg" })
    )
    )
    ),
    React.createElement("div", { className: "p-5 space-y-4" },
    React.createElement("div", { className: "text-[10px] font-bold text-muted uppercase tracking-widest mb-3" }, "Gu\xEDa Visual de Interpretaci\xF3n"),
    content.items && content.items.map((item, idx) =>
    React.createElement("div", { key: idx, className: "flex gap-4 items-start group" },
    React.createElement("div", { className: `mt-1 w-8 h-8 rounded-lg bg-white/5 flex items-center justify-center border border-white/5 text-lg ${item.color} group-hover:scale-110 transition-transform` },
    item.icon.includes('fa-') ?
    React.createElement("i", { className: `fas ${item.icon}` }) :
    React.createElement("span", null, item.icon)
    ),
    React.createElement("div", { className: "flex-1" },
    React.createElement("div", { className: `text-sm font-bold ${item.color} mb-0.5` }, item.label),
    React.createElement("div", { className: "text-xs text-gray-400 leading-snug" }, item.text)
    )
    )
    )
    ),
    React.createElement("div", { className: "p-4 bg-white/5 border-t border-white/5 text-center flex gap-3 justify-center" },
    content.onActivate &&
    React.createElement("button", { onClick: () => {
        content.onActivate();
        setIsOpen(false);
      }, className: "px-6 py-2 bg-green-900/20 border border-green-500/30 text-green-400 rounded hover:bg-green-900/40 transition-colors text-xs font-bold uppercase tracking-wider flex items-center gap-2" },
    React.createElement("i", { className: "fas fa-play" }), " Activar Estrategia"
    ),
    React.createElement("button", { onClick: () => setIsOpen(false), className: "px-6 py-2 bg-white/5 border border-white/10 text-gray-300 rounded hover:bg-white/10 transition-colors text-xs font-bold uppercase tracking-wider" }, "Cerrar"
    )
    )
    )
    ));
};
window.AlgoInfoModal = AlgoInfoModal;