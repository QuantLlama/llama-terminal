const Modal = ({ isOpen, onClose, title, children }) => {
  if (!isOpen) return null;
  return (
    React.createElement("div", { className: "fixed inset-0 bg-black/25 z-[9999] backdrop-blur-lg animate-[fadeIn_0.2s_ease-out] grid place-items-center" },
    React.createElement("div", { className: "w-[400px] h-fit bg-[#111] border border-border p-5 rounded-lg shadow-2xl" },
    React.createElement("div", { className: "flex justify-between items-center mb-4 border-b border-gray-800 pb-2" },
    React.createElement("h3", { className: "text-sm font-bold text-white uppercase tracking-wider" }, title),
    React.createElement("button", { onClick: onClose, className: "text-gray-500 hover:text-white" },
    React.createElement("i", { className: "fas fa-times" })
    )
    ),
    children
    )
    ));
};