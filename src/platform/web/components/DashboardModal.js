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
    React.createElement("div", { className: "fixed inset-0 bg-black/90 z-[9999] flex items-center justify-center backdrop-blur-md" },
    React.createElement("div", { className: "bg-white w-[95vw] h-[95vh] rounded-lg shadow-2xl flex flex-col overflow-hidden relative" },
    React.createElement("button", { onClick: onClose, className: "absolute top-4 right-4 text-black z-50 bg-white/50 p-2 rounded-full hover:bg-white" },
    React.createElement("i", { className: "fas fa-times text-xl" })
    ),
    React.createElement("iframe", {
      srcDoc: html,
      className: "w-full h-full border-0",
      sandbox: "allow-scripts allow-same-origin" }
    )
    )
    ));
};
window.DashboardModal = DashboardModal;