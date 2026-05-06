const Footer = ({ connected, latency, dataSource, platform }) => {
  const [aboutOpen, setAboutOpen] = React.useState(false);
  const connectionStatus = connected ? 'CONNECTED' : 'DISCONNECTED';
  const connectionColor = connected ? 'text-success' : 'text-danger';
  const latencyText = latency !== null ? `${latency}ms` : '--';
  const latencyColor = latency === null ? 'text-muted' :
  latency < 50 ? 'text-success' :
  latency < 150 ? 'text-yellow-400' : 'text-danger';
  const source = dataSource || (connected ? 'REAL-TIME' : 'OFFLINE');
  const platformName = (platform || 'MT5').toUpperCase();
  return (
    React.createElement(React.Fragment, null,
    React.createElement(AboutModal, { isOpen: aboutOpen, onClose: () => setAboutOpen(false) }),
    React.createElement("div", { className: "h-8 border-t border-border bg-panel flex items-center justify-between px-4 shrink-0 text-[10px] text-muted font-mono" },
    React.createElement("div", { className: "flex items-center gap-4" },
    React.createElement("span", { className: connectionColor },
    React.createElement("i", { className: "fas fa-server mr-1" }), " ", platformName, ": ", connectionStatus
    ),
    React.createElement("span", { className: latencyColor },
    React.createElement("i", { className: "fas fa-bolt mr-1" }), " LATENCY: ", latencyText
    ),
    React.createElement("span", null,
    React.createElement("i", { className: "fas fa-database mr-1" }), " DATA: ", source
    )
    ),
    React.createElement("div", { className: "flex items-center gap-4" },
    React.createElement("button", {
      onClick: () => setAboutOpen(true),
      className: "text-muted hover:text-accent transition-colors cursor-pointer hover:underline" },
    "1.8.1 PROFESSIONAL"
    ),
    React.createElement("a", { href: "https://llamaterminal.nbmsystemas.com", target: "_blank", rel: "noopener noreferrer", className: "text-accent hover:text-yellow-300 transition-colors cursor-pointer" }, "QUANTUM LLAMA SYSTEMS"
    )
    )
    )
    ));
};
window.Footer = Footer;