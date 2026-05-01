const NotificationContext = React.createContext();
const NotificationProvider = ({ children }) => {
  const { useState, useEffect, useRef, useMemo, useCallback } = React;
  const [notifications, setNotifications] = useState([]);
  const addNotification = (type, title, message) => {
    const id = Date.now();
    setNotifications((prev) => [...prev, { id, type, title, message }]);
    setTimeout(() => {
      setNotifications((prev) => prev.filter((n) => n.id !== id));
    }, 5000);
  };
  const removeNotification = (id) => {
    setNotifications((prev) => prev.filter((n) => n.id !== id));
  };
  useEffect(() => {
    const handler = (e) => {
      const { type, title, message } = e.detail;
      const muteSave = localStorage.getItem('muteSaveNotifications') === 'true';
      const muteTrading = localStorage.getItem('muteTradingNotifications') === 'true';
      const lowerTitle = (title || "").toLowerCase();
      const lowerMsg = (message || "").toLowerCase();
      if (muteSave && (lowerTitle.includes('save') || lowerMsg.includes('save') || lowerTitle.includes('workspace'))) {
        return;
      }
      if (muteTrading && (lowerTitle.includes('order') || lowerMsg.includes('order') || lowerTitle.includes('entry') || lowerTitle.includes('stop') || lowerTitle.includes('profit'))) {
        return;
      }
      addNotification(type, title, message);
    };
    window.addEventListener('notify', handler);
    return () => window.removeEventListener('notify', handler);
  }, []);
  return (
    React.createElement(NotificationContext.Provider, { value: { addNotification } },
    children,
    React.createElement("div", { className: "fixed bottom-4 right-4 z-[10001] flex flex-col gap-2 pointer-events-none" },
    notifications.map((n) =>
    React.createElement("div", { key: n.id, className: `pointer-events-auto min-w-[300px] max-w-md bg-[#1a1a1a] border-l-4 ${n.type === 'success' ? 'border-green-500' : n.type === 'error' ? 'border-red-500' : 'border-blue-500'} p-3 rounded shadow-2xl flex flex-col animate-[slideIn_0.3s_ease-out]` },
    React.createElement("div", { className: "flex justify-between items-start" },
    React.createElement("span", { className: `text-xs font-bold uppercase tracking-wider ${n.type === 'success' ? 'text-green-400' : n.type === 'error' ? 'text-red-400' : 'text-blue-400'}` },
    n.title
    ),
    React.createElement("button", { onClick: () => removeNotification(n.id), className: "text-gray-500 hover:text-white" },
    React.createElement("i", { className: "fas fa-times" })
    )
    ),
    React.createElement("p", { className: "text-xs text-gray-300 mt-1 font-mono break-words leading-relaxed" },
    n.message
    )
    )
    )
    )
    ));
};
const useNotification = () => React.useContext(NotificationContext);
window.NotificationProvider = NotificationProvider;
window.useNotification = useNotification;
window.Notification = { NotificationProvider, useNotification };