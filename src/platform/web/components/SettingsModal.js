const { useState, useEffect, useRef } = React;
const SETTINGS_TABS = [
{ id: "general", label: "General", icon: "fa-cog" },
{ id: "risk", label: "Risk Management", icon: "fa-shield-alt" },
{ id: "commissions", label: "Commissions", icon: "fa-percentage" },
{ id: "history", label: "History", icon: "fa-database" },
{ id: "accounts", label: "Accounts", icon: "fa-users-cog" }];
const ConfirmDialog = ({ isOpen, onConfirm, onCancel, title, message }) => {
  if (!isOpen) return null;
  return (
    React.createElement("div", { className: "fixed inset-0 bg-black/60 z-[10000] backdrop-blur-sm animate-in fade-in duration-200 pointer-events-auto grid place-items-center" },
    React.createElement("div", { className: "w-[350px] h-fit bg-[#111] border border-gray-800 p-6 rounded-xl shadow-2xl scale-in-center overflow-hidden" },
    React.createElement("div", { className: "flex items-center gap-3 mb-4 text-red-400" },
    React.createElement("div", { className: "w-10 h-10 rounded-full bg-red-400/10 flex items-center justify-center" },
    React.createElement("i", { className: "fas fa-exclamation-triangle" })
    ),
    React.createElement("h3", { className: "font-bold text-white" }, title)
    ),
    React.createElement("p", { className: "text-sm text-gray-400 mb-6 leading-relaxed" }, message),
    React.createElement("div", { className: "flex justify-end gap-3 font-bold" },
    React.createElement("button", {
      onClick: onCancel,
      className: "px-4 py-2 text-xs text-muted hover:text-white transition-colors" },
    "CANCEL"
    ),
    React.createElement("button", {
      onClick: onConfirm,
      className: "px-4 py-2 bg-red-500 text-white text-xs rounded hover:bg-red-600 transition-colors shadow-lg" },
    "DELETE ACCOUNT"
    )
    )
    )
    ));
};
const SearchableSelect = ({
  label,
  value,
  onChange,
  options,
  placeholder,
  className
}) => {
  const [isOpen, setIsOpen] = useState(false);
  const containerRef = React.useRef(null);
  useEffect(() => {
    const handleClickOutside = (event) => {
      if (
      containerRef.current &&
      !containerRef.current.contains(event.target))
      {
        setIsOpen(false);
      }
    };
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);
  const filteredOptions = (options || []).filter((opt) => {
    const label = typeof opt === 'string' ? opt : opt?.server || opt?.name || "";
    return String(label).toLowerCase().includes((value || "").toLowerCase());
  });
  return (
    React.createElement("div", { className: `relative ${className}`, ref: containerRef },
    React.createElement("label", { className: "block text-xs font-semibold text-muted mb-1" },
    label
    ),
    React.createElement("div", { className: "relative" },
    React.createElement("input", {
      type: "text",
      value: value,
      onChange: (e) => {
        onChange(e.target.value);
        if (!isOpen) setIsOpen(true);
      },
      onFocus: () => setIsOpen(true),
      placeholder: placeholder,
      className: "w-full bg-black border border-border rounded p-2 text-sm text-white focus:border-accent outline-none",
      autoComplete: "off" }
    ),
    React.createElement("i", {
      className: "fas fa-chevron-down absolute right-3 top-1/2 -translate-y-1/2 text-muted text-xs cursor-pointer hover:text-white",
      onClick: () => setIsOpen(!isOpen) }
    )
    ),
    isOpen &&
    React.createElement("ul", { className: "absolute z-[60] mt-1 w-full bg-black border border-border rounded max-h-48 overflow-y-auto shadow-xl" },
    filteredOptions.length > 0 ?
    filteredOptions.map((opt, idx) => {
      const displayLabel = typeof opt === 'string' ? opt : opt?.server || opt?.name || "Unknown";
      return (
        React.createElement("li", {
          key: idx,
          className: "p-2 text-sm text-white hover:bg-neutral-800 cursor-pointer",
          onClick: () => {
            onChange(displayLabel);
            setIsOpen(false);
          } },
        displayLabel
        ));
    }) :
    React.createElement("li", { className: "p-2 text-xs text-muted italic" }, "No matches found")
    )
    ));
};
const HISTORY_DEFAULTS = {
  "1m": 3000,
  "5m": 5000,
  "15m": 2500,
  "30m": 2000,
  "1h": 2000,
  "4h": 1000,
  "1d": 500
};
const BrandIcon = ({ type, className = "w-6 h-6" }) => {
  return (
    React.createElement("svg", {
      viewBox: "0 0 24 24",
      fill: "none",
      className: className,
      stroke: "currentColor",
      strokeWidth: "1.5" },
    React.createElement("path", { d: "M3 21h18M5 21V7l8-4 8 4v14" }),
    React.createElement("path", { d: "M9 10a2 2 0 1 1-4 0M19 10a2 2 0 1 1-4 0" })
    ));
};
const SettingsModal = ({
  isOpen,
  onClose,
  activeSymbol,
  indicators,
  refreshIndicators,
  onUpdateSettings
}) => {
  const [activeTab, setActiveTab] = useState(() => {
    return localStorage.getItem("quantum_settings_active_tab") || "general";
  });
  useEffect(() => {
    if (activeTab) {
      localStorage.setItem("quantum_settings_active_tab", activeTab);
    }
  }, [activeTab]);
  const [historyLimits, setHistoryLimits] = useState(() => {
    try {
      const stored = localStorage.getItem("chart_history_limits");
      return stored ?
      { ...HISTORY_DEFAULTS, ...JSON.parse(stored) } :
      { ...HISTORY_DEFAULTS };
    } catch (e) {
      return { ...HISTORY_DEFAULTS };
    }
  });
  const [config, setConfig] = useState({});
  const [platform, setPlatform] = useState("mt5");
  const [theme, setTheme] = useState("dark");
  const [commissions, setCommissions] = useState(() => {
    try {
      const stored = localStorage.getItem("trading_commissions");
      return stored ? JSON.parse(stored) : {
        futures_mini: 5.0,
        futures_micro: 1.2,
        cfd: 7.0
      };
    } catch (e) {
      return { futures_mini: 5.0, futures_micro: 1.2, cfd: 7.0 };
    }
  });
  const [riskSettings, setRiskSettings] = useState(() => {
    try {
      const stored = localStorage.getItem("risk_management_config");
      return stored ? JSON.parse(stored) : {
        maxDailyLoss: 500,
        maxContracts: 1,
        emotionalGuard: true,
        autoLock: true
      };
    } catch (e) {
      return { maxDailyLoss: 500, maxContracts: 1, emotionalGuard: true, autoLock: true };
    }
  });
  const [muteSave, setMuteSave] = useState(
    () => localStorage.getItem("mute_save_notifications") === "true"
  );
  const [muteTrading, setMuteTrading] = useState(
    () => localStorage.getItem("mute_trading_notifications") === "true"
  );
  const [pos, setPos] = useState({ x: 100, y: 100 });
  const [isDragging, setIsDragging] = useState(false);
  const dragRef = useRef(null);
  const offsetRef = useRef({ x: 0, y: 0 });
  const handleMouseDown = (e) => {
    if (e.target.closest(".drag-handle")) {
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
    const handleMouseMove = (e) => {
      setPos({
        x: e.clientX - offsetRef.current.x,
        y: e.clientY - offsetRef.current.y
      });
    };
    const handleMouseUp = () => setIsDragging(false);
    window.addEventListener("mousemove", handleMouseMove);
    window.addEventListener("mouseup", handleMouseUp);
    return () => {
      window.removeEventListener("mousemove", handleMouseMove);
      window.removeEventListener("mouseup", handleMouseUp);
    };
  }, [isDragging]);
  useEffect(() => {
    if (isOpen) {
      setPos({ x: (window.innerWidth - 600) / 2, y: 100 });
    }
  }, [isOpen]);
  const [accounts, setAccounts] = useState([]);
  const [isAddingAccount, setIsAddingAccount] = useState(false);
  const [activeAccountTab, setActiveAccountTab] = useState("all");
  const [newAccount, setNewAccount] = useState({
    name: "",
    broker: "",
    server: "",
    login: "",
    password: "",
    account_type: "demo",
    platform: "mt5",
    exchange_dir: ""
  });
  const [testResult, setTestResult] = useState(null);
  const [loadingAccounts, setLoadingAccounts] = useState(false);
  const { addNotification } = window.useNotification();
  const [confirmDelete, setConfirmDelete] = useState({
    isOpen: false,
    accountId: null,
    platform: null
  });
  const [availableBrokers, setAvailableBrokers] = useState([]);
  const [availableServers, setAvailableServers] = useState([]);
  useEffect(() => {
    const fetchBrokers = async () => {
      try {
        const p = isAddingAccount ? newAccount.platform : platform;
        const res = await fetch(`/api/accounts/brokers?type=${p}`);
        if (res.ok) {
          const data = await res.json();
          setAvailableBrokers(Array.isArray(data) ? data : []);
        }
      } catch (e) {
        console.error("Broker fetch failed:", e);
      }
    };
    fetchBrokers();
  }, [platform, newAccount.platform, isAddingAccount]);
  useEffect(() => {
    if (!isAddingAccount) return;
    const timer = setTimeout(async () => {
      const broker = newAccount.broker || "";
      const query = newAccount.server || "";
      const searchTerm = query.length >= 2 ? query : broker.length >= 2 ? broker : "";
      if (!searchTerm) {
        setAvailableServers([]);
        return;
      }
      try {
        const res = await fetch(`/api/accounts/server-search?q=${encodeURIComponent(searchTerm)}`);
        if (res.ok) {
          const data = await res.json();
          setAvailableServers(Array.isArray(data) ? data : []);
        }
      } catch (e) {
        console.error("Server fetch failed:", e);
      }
    }, 300);
    return () => clearTimeout(timer);
  }, [newAccount.broker, newAccount.server, newAccount.platform, isAddingAccount]);
  const fetchAccounts = async () => {
    setLoadingAccounts(true);
    try {
      const res = await fetch("/api/accounts");
      if (res.ok) {
        const data = await res.json();
        setAccounts(data);
      }
    } catch (e) {
      console.error("Failed to fetch accounts:", e);
    } finally {
      setLoadingAccounts(false);
    }
  };
  const handleAddAccount = async () => {
    if (!newAccount.name || !newAccount.platform) {
      addNotification("error", "Validation Error", "Please fill in all required fields");
      return;
    }
    const isEdit = !!newAccount.id;
    const method = isEdit ? "PATCH" : "POST";
    const url = isEdit ?
    `/api/accounts/${newAccount.id}?platform=${newAccount.platform}` :
    "/api/accounts";
    const payload = {
      ...newAccount,
      broker: (newAccount.broker || "").trim(),
      name: (newAccount.name || "").trim()
    };
    if (isEdit) delete payload.id;
    try {
      const res = await fetch(url, {
        method: method,
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
      });
      if (res.ok) {
        setNewAccount({
          name: "",
          broker: "",
          server: "",
          login: "",
          username: "",
          password: "",
          api_key: "",
          api_secret: "",
          passphrase: "",
          metadata: {
            system: "",
            gateway: "",
            app_id: "",
            app_version: "1.0.0",
            cid: "",
            sec: ""
          },
          account_type: "demo",
          platform: newAccount.platform,
          environment: "real",
          exchange_dir: ""
        });
        setIsAddingAccount(false);
        fetchAccounts();
        addNotification("success", isEdit ? "Account Updated" : "Account Added", isEdit ? "Account details updated successfully" : "New account connected successfully");
        setTestResult(null);
      } else {
        const err = await res.json();
        addNotification("error", isEdit ? "Update Failed" : "Add Account Failed", err.detail || "Could not save account");
      }
    } catch (e) {
      addNotification("error", "Connection Error", "Failed to reach the server");
    }
  };
  const handleEditAccount = (acc) => {
    setNewAccount({
      ...acc,
      password: "",
      api_secret: ""
    });
    setIsAddingAccount(true);
  };
  const handleSetMaster = async (id, platform = "mt5") => {
    try {
      const res = await fetch(`/api/accounts/${id}/master?platform=${platform}`, { method: "POST" });
      if (res.ok) {
        addNotification("success", "Master Account", "Active account switched successfully");
      } else {
        addNotification("error", "Master Switch", "Master assigned but connection failed.");
      }
      fetchAccounts();
    } catch (e) {
      addNotification("error", "Connection Error", "Failed to update master account");
    }
  };
  const handleToggleMirror = async (id, platform, currentVal) => {
    try {
      const res = await fetch(`/api/accounts/${id}?platform=${platform}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ mirror_trading: !currentVal })
      });
      if (res.ok) {
        addNotification("success", "Mirror Updated", `Replication ${!currentVal ? 'Enabled' : 'Disabled'}`);
        fetchAccounts();
      }
    } catch (e) {
      addNotification("error", "Error", "Failed to update mirror settings");
    }
  };
  const handleDeleteAccount = (id, platform = "mt5") => {
    setConfirmDelete({ isOpen: true, accountId: id, platform: platform });
  };
  const confirmDeletion = async () => {
    const id = confirmDelete.accountId;
    const platform = confirmDelete.platform || "mt5";
    try {
      const res = await fetch(`/api/accounts/${id}?platform=${platform}`, { method: "DELETE" });
      if (res.ok) {
        addNotification("success", "Account Removed", "The credentials have been deleted");
        fetchAccounts();
      }
    } catch (e) {
      addNotification("error", "Delete Failed", "Could not remove the account");
    } finally {
      setConfirmDelete({ isOpen: false, accountId: null, platform: null });
    }
  };
  const handleTestConnection = async (id, platform = "mt5") => {
    setTestResult({ id, status: "testing" });
    try {
      const res = await fetch(`/api/accounts/${id}/test?platform=${platform}`, { method: "POST" });
      const data = await res.json();
      setTestResult({ id, ...data });
    } catch (e) {
      setTestResult({ id, success: false, error: e.message });
    }
  };
  useEffect(() => {
    if (!isOpen) return;
    const loadSettings = async () => {
      try {
        const res = await fetch("/api/config");
        if (res.ok) {
          const data = await res.json();
          setConfig(data);
          setPlatform(data.platform || "tradovate");
          setTheme(data.theme || "dark");
          
          if (data.chart_history_limits) {
            setHistoryLimits(typeof data.chart_history_limits === 'string' ?
              JSON.parse(data.chart_history_limits) :
              data.chart_history_limits);
          }
          
          if (data.commissions) {
            setCommissions(typeof data.commissions === 'string' ?
              JSON.parse(data.commissions) :
              data.commissions);
          }

          if (data.risk_max_daily_loss !== undefined) {
            setRiskSettings({
              maxDailyLoss: data.risk_max_daily_loss,
              maxContracts: data.risk_max_contracts,
              emotionalGuard: data.risk_emotional_guard
            });
          }
        }
      } catch (e) {
        console.error("Failed to load config:", e);
        setPlatform(localStorage.getItem("platform") || "tradovate");
        setTheme(localStorage.getItem("theme") || "dark");
      }
    };
    loadSettings();
  }, [isOpen, activeSymbol]);
  useEffect(() => {
    if (activeTab === "accounts") {
      fetchAccounts();
    }
  }, [activeTab]);
  const save = async () => {
    const oldPlatform = localStorage.getItem("platform");
    const platformChanged = oldPlatform && oldPlatform !== platform;
    const payload = {
      platform,
      theme,
      chart_history_limits: historyLimits,
      commissions: commissions,
      risk_max_daily_loss: riskSettings.maxDailyLoss,
      risk_max_contracts: riskSettings.maxContracts,
      risk_emotional_guard: riskSettings.emotionalGuard,
      risk_locked_until: localStorage.getItem("platform_locked_until")
    };
    try {
      await fetch("/api/config", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
      });
    } catch (e) {
      console.error("Failed to save settings to API:", e);
    }
    localStorage.setItem("platform", platform);
    localStorage.setItem("broker_platform", platform);
    localStorage.setItem("theme", theme);
    localStorage.setItem("chart_history_limits", JSON.stringify(historyLimits));
    localStorage.setItem("trading_commissions", JSON.stringify(commissions));
    localStorage.setItem("risk_management_config", JSON.stringify(riskSettings));
    if (onUpdateSettings) {
      onUpdateSettings({
        appearance: {
        },
        layout: {
          theme: theme
        }
      });
    }
    window.dispatchEvent(new CustomEvent("settings_updated", { detail: { symbol: activeSymbol } }));
    localStorage.setItem("mute_save_notifications", muteSave);
    localStorage.setItem("mute_trading_notifications", muteTrading);
    window.dispatchEvent(new CustomEvent("notification_settings_changed", {
      detail: { muteSave, muteTrading }
    }));
    if (platformChanged) {
      window.dispatchEvent(new CustomEvent("platform_changed", { detail: { oldPlatform, newPlatform: platform } }));
    }
    onClose();
  };
  useEffect(() => {
    if (!SETTINGS_TABS.some((t) => t.id === activeTab)) {
      setActiveTab("general");
    }
  }, [activeTab]);
  useEffect(() => {
    if (!isOpen) return;
  }, [isOpen]);
  if (!isOpen) return null;
  return (
    React.createElement("div", { className: "fixed inset-0 z-[10000] pointer-events-none overflow-hidden font-sans" },
    React.createElement("div", {
      ref: dragRef,
      style: {
        position: "absolute",
        left: `${pos.x}px`,
        top: `${pos.y}px`,
        width: "600px",
        maxHeight: "85vh"
      },
      className: "bg-[#0a0a0a] border border-zinc-800 rounded-lg shadow-[0_20px_50px_rgba(0,0,0,0.8)] overflow-hidden flex flex-col pointer-events-auto animate-in fade-in zoom-in duration-300" },
    React.createElement("div", {
      onMouseDown: handleMouseDown,
      className: "drag-handle flex items-center justify-between px-6 py-4 border-b border-zinc-900 bg-zinc-900/50 cursor-move select-none hover:bg-zinc-900 transition-colors" },
    React.createElement("div", { className: "flex items-center gap-3" },
    React.createElement("div", { className: "w-7 h-7 rounded-lg bg-zinc-800 flex items-center justify-center border border-white/5" },
    React.createElement("i", { className: "fas fa-cog text-zinc-500 text-xs" })
    ),
    React.createElement("div", null,
    React.createElement("h2", { className: "text-xs font-black text-white uppercase tracking-widest" }, "Settings"
    ),
    React.createElement("p", { className: "text-[10px] text-zinc-500 font-bold uppercase tracking-tighter opacity-70" }, "Configuration & Tools \u2022 ",
    activeSymbol
    )
    )
    ),
    React.createElement("button", {
      onClick: onClose,
      className: "w-8 h-8 flex items-center justify-center rounded-full hover:bg-white/5 text-zinc-500 hover:text-white transition-all transition-colors duration-200" },
    React.createElement("i", { className: "fas fa-times" })
    )
    ),
    React.createElement("div", { className: "flex px-2 bg-black/40 border-b border-white/5" },
    SETTINGS_TABS.map((tab) =>
    React.createElement("button", {
      key: tab.id,
      onClick: () => setActiveTab(tab.id),
      className: `flex items-center gap-2 px-4 py-2 text-[10px] font-bold uppercase tracking-wider transition-all duration-200 border-b-2 ${activeTab === tab.id ?
      "text-zinc-300 border-zinc-500 bg-white/5" :
      "text-zinc-500 border-transparent hover:text-gray-400 hover:bg-white/5"}` },
    React.createElement("i", { className: `fas ${tab.icon} text-[10px]` }),
    tab.label
    )
    )
    ),
    React.createElement("div", { className: "flex-1 overflow-y-auto p-6 scrollbar-thin scrollbar-thumb-zinc-800 scrollbar-track-transparent" },
    React.createElement("div", { className: "space-y-6" },
    activeTab === "general" &&
    React.createElement("div", { className: "space-y-6 animate-in fade-in slide-in-from-top-2 duration-300" },
    React.createElement("div", { className: "bg-white/[0.02] p-3 rounded-lg border border-white/5 space-y-4 shadow-inner" },
    React.createElement("div", null,
    React.createElement("label", { className: "block text-[10px] font-black text-zinc-400 uppercase tracking-widest mb-2" }, "Execution Engine"
    ),
    React.createElement("select", {
      value: platform,
      onChange: (e) => setPlatform(e.target.value),
      className: "w-full bg-black/50 border border-white/10 rounded-lg p-3 text-sm text-white focus:border-accent outline-none transition-all duration-200" },
    React.createElement("option", { value: "mt5" }, "CFD/FOREX/FUTURES (MetaTrader 5)"),
    React.createElement("option", { value: "tradovate" }, "FUTURES (Tradovate)"),
    React.createElement("option", { value: "crypto" }, "CRYPTO (Binance/Bybit)")
    )
    ),
    React.createElement("div", null,
    React.createElement("label", { className: "block text-[10px] font-black text-zinc-400 uppercase tracking-widest mb-2" }, "UI Theme"
    ),
    React.createElement("select", {
      value: theme,
      onChange: (e) => setTheme(e.target.value),
      className: "w-full bg-black/50 border border-white/10 rounded-lg p-3 text-sm text-white focus:border-accent outline-none transition-all duration-200" },
    React.createElement("option", { value: "dark" }, "Quantum Dark"),
    React.createElement("option", { value: "midnight" }, "Midnight Blue")
    )
    ),
    React.createElement("div", { className: "pt-2" },
    React.createElement("label", { className: "block text-[10px] font-black text-zinc-400 uppercase tracking-widest mb-3" }, "Notifications & Alerts"
    ),
    React.createElement("div", { className: "space-y-3" },
    React.createElement("div", { className: "flex items-center justify-between bg-black/30 p-3 rounded-lg border border-white/5" },
    React.createElement("span", { className: "text-[11px] text-zinc-300 font-bold uppercase tracking-tighter" }, "Mute Save Notifications"),
    React.createElement("button", {
      onClick: () => setMuteSave(!muteSave),
      className: `w-10 h-5 rounded-full relative transition-colors ${muteSave ? 'bg-accent' : 'bg-zinc-800'}` },
    React.createElement("div", { className: `absolute top-1 w-3 h-3 rounded-full bg-white transition-all ${muteSave ? 'right-1' : 'left-1'}` })
    )
    ),
    React.createElement("div", { className: "flex items-center justify-between bg-black/30 p-3 rounded-lg border border-white/5" },
    React.createElement("span", { className: "text-[11px] text-zinc-300 font-bold uppercase tracking-tighter" }, "Mute Order Notifications"),
    React.createElement("button", {
      onClick: () => setMuteTrading(!muteTrading),
      className: `w-10 h-5 rounded-full relative transition-colors ${muteTrading ? 'bg-accent' : 'bg-zinc-800'}` },
    React.createElement("div", { className: `absolute top-1 w-3 h-3 rounded-full bg-white transition-all ${muteTrading ? 'right-1' : 'left-1'}` })
    )
    )
    )
    )
    ),
    React.createElement("div", { className: "p-4 bg-red-900/10 border border-red-500/20 rounded-xl shadow-[0_0_20px_rgba(239,68,68,0.05)]" },
    React.createElement("h3", { className: "text-red-400 text-[10px] font-black uppercase tracking-widest mb-2 flex items-center gap-2" },
    React.createElement("i", { className: "fas fa-exclamation-triangle" }), "System Troubleshooting"
    ),
    React.createElement("p", { className: "text-[11px] text-zinc-500 leading-relaxed mb-4" }, "If symbols don't appear or the UI feels laggy, use this to clear all local cache and force-sync."
    ),
    React.createElement("button", {
      onClick: () => {
        if (
        confirm(
          "⚠️ WARNING: This will clear all local settings, workspaces and cache. Continue?"
        ))
        {
          localStorage.clear();
          window.location.reload();
        }
      },
      className: "w-full py-2.5 bg-red-500/10 hover:bg-red-500/20 border border-red-500/20 text-red-500 text-[10px] font-bold rounded-lg transition-all flex items-center justify-center gap-2 uppercase tracking-widest" },
    React.createElement("i", { className: "fas fa-radiation-alt" }), "NUCLEAR PURGE & RESET"
    )
    )
    ),
    activeTab === "risk" &&
    React.createElement("div", { className: "space-y-6 animate-in fade-in slide-in-from-top-2 duration-300" },
    React.createElement("div", { className: "p-4 bg-zinc-900/50 border border-zinc-800 rounded-xl space-y-4" },
    React.createElement("div", { className: "flex items-center gap-3 mb-2" },
    React.createElement("div", { className: "w-8 h-8 rounded-lg bg-orange-500/10 flex items-center justify-center border border-orange-500/20" },
    React.createElement("i", { className: "fas fa-shield-alt text-orange-500" })
    ),
    React.createElement("div", null,
    React.createElement("h3", { className: "text-[11px] font-black text-white uppercase tracking-widest" }, "Quant Llama Emotional Guard"),
    React.createElement("p", { className: "text-[9px] text-zinc-500 font-bold uppercase" }, "Professional Risk Management")
    )
    ),
    React.createElement("div", { className: "grid grid-cols-2 gap-4" },
    React.createElement("div", { className: "space-y-2" },
    React.createElement("label", { className: "block text-[10px] font-black text-zinc-400 uppercase tracking-widest" }, "Max Daily Loss ($)"),
    React.createElement("div", { className: "relative" },
    React.createElement("span", { className: "absolute left-3 top-1/2 -translate-y-1/2 text-red-500 font-bold text-xs" }, "-$"),
    React.createElement("input", {
      type: "number",
      value: riskSettings.maxDailyLoss,
      onChange: (e) => setRiskSettings({ ...riskSettings, maxDailyLoss: parseFloat(e.target.value) || 0 }),
      className: "w-full bg-black border border-white/10 rounded-lg p-3 pl-8 text-sm text-white focus:border-red-500 outline-none transition-all" }
    )
    )
    ),
    React.createElement("div", { className: "space-y-2" },
    React.createElement("label", { className: "block text-[10px] font-black text-zinc-400 uppercase tracking-widest" }, "Max Contracts"),
    React.createElement("input", {
      type: "number",
      value: riskSettings.maxContracts,
      onChange: (e) => setRiskSettings({ ...riskSettings, maxContracts: parseInt(e.target.value) || 1 }),
      className: "w-full bg-black border border-white/10 rounded-lg p-3 text-sm text-white focus:border-accent outline-none transition-all" }
    )
    )
    ),
    React.createElement("div", { className: "space-y-3 pt-4 border-t border-white/5" },
    React.createElement("div", { className: "flex items-center justify-between bg-black/30 p-3 rounded-lg border border-white/5" },
    React.createElement("div", { className: "flex flex-col" },
    React.createElement("span", { className: "text-[11px] text-zinc-300 font-bold uppercase tracking-tighter" }, "Hard Lock Mechanism"),
    React.createElement("span", { className: "text-[9px] text-zinc-500 font-medium" }, "Platform locks until next NY session if limit is hit")
    ),
    React.createElement("button", {
      onClick: () => setRiskSettings({ ...riskSettings, emotionalGuard: !riskSettings.emotionalGuard }),
      className: `w-10 h-5 rounded-full relative transition-colors ${riskSettings.emotionalGuard ? 'bg-orange-500' : 'bg-zinc-800'}` },
    React.createElement("div", { className: `absolute top-1 w-3 h-3 rounded-full bg-white transition-all ${riskSettings.emotionalGuard ? 'right-1' : 'left-1'}` })
    )
    )
    )
    ),
    React.createElement("div", { className: "p-4 bg-orange-950/20 border border-orange-500/20 rounded-xl" },
    React.createElement("h4", { className: "text-orange-500 text-[10px] font-black uppercase tracking-widest mb-2" }, "Rules & Compliance"),
    React.createElement("ul", { className: "space-y-2" },
    React.createElement("li", { className: "text-[10px] text-zinc-400 flex gap-2" },
    React.createElement("i", { className: "fas fa-check text-orange-500 mt-0.5" }),
    "Trading will be automatically disabled when realized PnL reaches the loss limit."
    ),
    React.createElement("li", { className: "text-[10px] text-zinc-400 flex gap-2" },
    React.createElement("i", { className: "fas fa-check text-orange-500 mt-0.5" }),
    "The platform will be COMPLETELY LOCKED until 09:30 AM EST (NY Session) the following trading day."
    ),
    React.createElement("li", { className: "text-[10px] text-zinc-400 flex gap-2" },
    React.createElement("i", { className: "fas fa-check text-orange-500 mt-0.5" }),
    "This lock cannot be bypassed by clearing cache or restarting."
    )
    )
    ),
    React.createElement("button", {
      onClick: () => {
        if (confirm("⚠️ MANUAL LOCK: This will lock the platform until tomorrow's NY session. Are you sure?")) {
          const now = new Date();
          localStorage.setItem("platform_manually_locked", "true");
          save();
          window.location.reload();
        }
      },
      className: "w-full py-3 bg-red-500/10 hover:bg-red-500/20 border border-red-500/20 text-red-500 text-[10px] font-black rounded-lg transition-all flex items-center justify-center gap-2 uppercase tracking-widest" },
    React.createElement("i", { className: "fas fa-lock" }), "FORCE EMERGENCY LOCK"
    )
    ),
    activeTab === "commissions" &&
    React.createElement("div", { className: "space-y-6 animate-in fade-in slide-in-from-top-2 duration-300" },
    React.createElement("div", { className: "p-4 bg-white/[0.02] border border-white/5 rounded-xl" },
    React.createElement("h3", { className: "text-[10px] font-black text-zinc-400 uppercase tracking-[0.2em] mb-4" }, "Round-Trip Commission ($)"
    ),
    React.createElement("div", { className: "space-y-4" },
    React.createElement("div", { className: "flex items-center justify-between bg-black/40 p-3 rounded-xl border border-white/5 hover:border-white/10 transition-colors" },
    React.createElement("div", { className: "flex flex-col" },
    React.createElement("span", { className: "text-[10px] font-black text-zinc-300 uppercase" }, "Futures Mini"),
    React.createElement("span", { className: "text-[8px] text-muted font-bold uppercase tracking-tighter" }, "Per Contract RT")
    ),
    React.createElement("input", {
      type: "number",
      value: commissions.futures_mini,
      onChange: (e) => setCommissions({ ...commissions, futures_mini: parseFloat(e.target.value) || 0 }),
      step: "0.1",
      className: "w-24 bg-transparent text-right text-sm text-white focus:text-accent outline-none font-mono font-bold" }
    )
    ),
    React.createElement("div", { className: "flex items-center justify-between bg-black/40 p-3 rounded-xl border border-white/5 hover:border-white/10 transition-colors" },
    React.createElement("div", { className: "flex flex-col" },
    React.createElement("span", { className: "text-[10px] font-black text-zinc-300 uppercase" }, "Futures Micro"),
    React.createElement("span", { className: "text-[8px] text-muted font-bold uppercase tracking-tighter" }, "Per Contract RT")
    ),
    React.createElement("input", {
      type: "number",
      value: commissions.futures_micro,
      onChange: (e) => setCommissions({ ...commissions, futures_micro: parseFloat(e.target.value) || 0 }),
      step: "0.1",
      className: "w-24 bg-transparent text-right text-sm text-white focus:text-accent outline-none font-mono font-bold" }
    )
    ),
    React.createElement("div", { className: "flex items-center justify-between bg-black/40 p-3 rounded-xl border border-white/5 hover:border-white/10 transition-colors" },
    React.createElement("div", { className: "flex flex-col" },
    React.createElement("span", { className: "text-[10px] font-black text-zinc-300 uppercase" }, "CFD / FX / Others"),
    React.createElement("span", { className: "text-[8px] text-muted font-bold uppercase tracking-tighter" }, "Per Lot / Standard Unit")
    ),
    React.createElement("input", {
      type: "number",
      value: commissions.cfd,
      onChange: (e) => setCommissions({ ...commissions, cfd: parseFloat(e.target.value) || 0 }),
      step: "0.1",
      className: "w-24 bg-transparent text-right text-sm text-white focus:text-accent outline-none font-mono font-bold" }
    )
    )
    ),
    React.createElement("div", { className: "mt-6 p-3 bg-accent/5 border border-accent/10 rounded-lg" },
    React.createElement("p", { className: "text-[10px] text-accent/70 leading-relaxed italic" },
    React.createElement("i", { className: "fas fa-info-circle mr-1" }), "These values are applied only to the History Panel for PnL calculations. They represent the total cost (brokerage + exchange fees) for a full entry and exit transaction."
    )
    )
    )
    ),
    activeTab === "history" &&
    React.createElement("div", { className: "space-y-6 animate-in fade-in slide-in-from-top-2 duration-300" },
    React.createElement("div", { className: "flex justify-between items-center bg-white/[0.02] p-4 rounded-xl border border-white/5" },
    React.createElement("div", null,
    React.createElement("h3", { className: "text-[10px] font-black text-zinc-400 uppercase tracking-[0.2em]" }, "History Data"
    )
    ),
    React.createElement("button", {
      onClick: () => setHistoryLimits({ ...HISTORY_DEFAULTS }),
      className: "px-3 py-1.5 bg-accent/10 border border-accent/20 text-accent text-[10px] font-bold rounded-lg hover:bg-accent/20 transition-all uppercase tracking-tighter" },
    "Recommended"
    )
    ),
    React.createElement("div", { className: "grid grid-cols-2 gap-3" },
    Object.entries(historyLimits).map(([tf, limit]) =>
    React.createElement("div", {
      key: tf,
      className: "flex items-center justify-between bg-black/40 p-3 rounded-xl border border-white/5 hover:border-white/10 transition-colors" },
    React.createElement("span", { className: "text-[10px] font-black text-zinc-500 uppercase" },
    tf
    ),
    React.createElement("input", {
      type: "number",
      value: limit,
      onChange: (e) =>
      setHistoryLimits({
        ...historyLimits,
        [tf]: parseInt(e.target.value) || 0
      }),
      className: "w-20 bg-transparent text-right text-xs text-white focus:text-accent outline-none font-mono font-bold" }
    )
    )
    )
    )
    ),
    activeTab === "accounts" &&
    React.createElement("div", { className: "space-y-6 animate-in fade-in slide-in-from-top-2 duration-300" },
    !isAddingAccount ?
    React.createElement(React.Fragment, null,
    React.createElement("div", { className: "flex bg-black/60 p-1 rounded-xl border border-white/5 shadow-inner" },
    ["all", "mt5", "crypto", "tradovate", "nt8"].map((tab) =>
    React.createElement("button", {
      key: tab,
      onClick: () => setActiveAccountTab(tab),
      className: `flex-1 py-2 text-[10px] font-black rounded-lg uppercase tracking-widest transition-all duration-200 ${activeAccountTab === tab ?
      "bg-accent text-black shadow-lg" :
      "text-zinc-500 hover:text-white"}` },
    tab
    )
    )
    ),
    React.createElement("div", { className: "grid gap-3" },
    accounts.
    filter(
      (acc) =>
      activeAccountTab === "all" ||
      acc.platform === activeAccountTab || activeAccountTab === "tradovate" && acc.platform === "futures"
    ).
    map((acc) =>
    React.createElement("div", {
      key: acc.id,
      className: `p-4 rounded-2xl border transition-all duration-300 ${acc.is_master ?
      "bg-accent/[0.03] border-accent/20 shadow-[0_0_15px_rgba(34,197,94,0.05)]" :
      "bg-white/[0.01] border-white/5 hover:border-white/10"}` },
    React.createElement("div", { className: "flex items-center justify-between" },
    React.createElement("div", { className: "flex items-center gap-4" },
    React.createElement("div", { className: "w-10 h-10 rounded-xl bg-black/80 flex items-center justify-center border border-white/10 shadow-lg" },
    React.createElement(BrandIcon, {
      type: acc.broker,
      className: "w-6 h-6 text-zinc-400" }
    )
    ),
    React.createElement("div", null,
    React.createElement("div", { className: "flex items-center gap-2" },
    React.createElement("h4", { className: "text-xs font-black text-white uppercase tracking-tight" },
    acc.name
    ),
    acc.is_master &&
    React.createElement("span", { className: "w-2 h-2 rounded-full bg-accent shadow-[0_0_8px_rgba(34,197,94,0.5)] animate-pulse" })
    ),
    React.createElement("p", { className: "text-[10px] text-zinc-500 font-bold uppercase tracking-wider" },
    acc.broker, " \u2022 ", acc.platform
    ),
    acc.platform === "nt8" && acc.exchange_dir &&
    React.createElement("p", { className: "text-[9px] text-accent/60 font-medium truncate max-w-[150px] mt-0.5", title: acc.exchange_dir }, "Dir: ",
    acc.exchange_dir
    ),
    acc.balance !== undefined &&
    React.createElement("p", { className: `text-[11px] font-black mt-0.5 ${acc.balance >= 0 ? 'text-accent' : 'text-red-400'}` },
    new Intl.NumberFormat('en-US', { style: 'currency', currency: acc.currency || 'USD' }).format(acc.balance)
    )
    )
    ),
    React.createElement("div", { className: "flex items-center gap-2" },
    acc.platform === "nt8" &&
    React.createElement("button", {
      onClick: () => handleToggleMirror(acc.id, acc.platform, acc.mirror_trading ?? true),
      className: `w-8 h-8 flex items-center justify-center rounded-lg border transition-all ${acc.mirror_trading ?? true ?
      "bg-accent/10 border-accent/20 text-accent" :
      "bg-zinc-800/50 border-white/5 text-zinc-600"}`,
      title: acc.mirror_trading ?? true ? "Mirroring Active" : "Mirroring Disabled" },
    React.createElement("i", { className: `fas ${acc.mirror_trading ?? true ? "fa-clone" : "fa-clone text-zinc-700"}`, style: { opacity: acc.mirror_trading ?? true ? 1 : 0.4 } })
    ),
    React.createElement("button", {
      onClick: () => handleEditAccount(acc),
      className: "w-8 h-8 flex items-center justify-center bg-white/5 hover:bg-white/10 text-zinc-400 hover:text-white rounded-lg border border-white/5 transition-all",
      title: "Edit Credentials" },
    React.createElement("i", { className: "fas fa-edit text-[10px]" })
    ),
    React.createElement("button", {
      onClick: () => handleTestConnection(acc.id, acc.platform),
      className: `w-7 h-7 flex items-center justify-center rounded-lg border transition-all ${testResult?.id === acc.id ?
      testResult.success ? "bg-zinc-800 border-zinc-500 text-zinc-300" : "bg-red-900/10 border-red-900 text-red-700" :
      "bg-white/5 border-white/5 text-zinc-500 hover:text-zinc-300"}`,
      title: "Test Connection" },
    React.createElement("i", { className: `fas ${testResult?.id === acc.id && testResult.status === 'testing' ? "fa-circle-notch fa-spin" : "fa-plug"} text-[10px]` })
    ),
    !acc.is_master &&
    React.createElement("button", {
      onClick: () =>
      handleSetMaster(acc.id, acc.platform),
      className: "px-2.5 py-1.5 bg-zinc-800 hover:bg-zinc-700 text-zinc-300 text-[9px] font-black uppercase rounded-lg border border-white/5 transition-all" },
    "Activate"
    ),
    React.createElement("button", {
      onClick: () =>
      handleDeleteAccount(acc.id, acc.platform),
      className: "w-7 h-7 flex items-center justify-center bg-red-500/5 hover:bg-red-500/10 text-red-500/60 hover:text-red-500 rounded-lg border border-red-500/10 transition-all" },
    React.createElement("i", { className: "fas fa-trash-alt text-[10px]" })
    )
    )
    )
    )
    ),
    React.createElement("button", {
      onClick: () => {
        setNewAccount({
          name: "",
          broker: "",
          server: "",
          login: "",
          username: "",
          password: "",
          api_key: "",
          api_secret: "",
          passphrase: "",
          metadata: {
            system: "",
            gateway: "",
            app_id: "",
            app_version: "1.0.0",
            cid: "",
            sec: ""
          },
          account_type: "demo",
          platform: "mt5",
          environment: "real",
          exchange_dir: ""
        });
        setIsAddingAccount(true);
      },
      className: "w-full py-6 border-2 border-dashed border-white/5 rounded-2xl text-zinc-600 hover:text-accent hover:border-accent/30 hover:bg-accent/5 transition-all flex flex-col items-center gap-3 active:scale-[0.98]" },
    React.createElement("i", { className: "fas fa-plus-circle text-lg" }),
    React.createElement("span", { className: "text-[10px] font-black uppercase tracking-[0.2em]" }, "Establish New Bridge"
    )
    )
    )
    ) :
    React.createElement("div", { className: "bg-white/[0.02] p-4 rounded-lg border border-white/5 space-y-5 animate-in slide-in-from-right-4 duration-300" },
    React.createElement("div", { className: "flex items-center justify-between mb-2" },
    React.createElement("div", { className: "flex items-center gap-2 text-accent" },
    React.createElement("i", { className: "fas fa-plus text-xs" }),
    React.createElement("h3", { className: "text-[11px] font-black uppercase tracking-[0.2em]" }, "New Connection"
    )
    ),
    React.createElement("button", {
      onClick: () => setIsAddingAccount(false),
      className: "text-[10px] text-zinc-500 hover:text-white uppercase font-black transition-colors" },
    "Cancel"
    )
    ),
    React.createElement("div", { className: "grid grid-cols-2 gap-2" },
    ["mt5", "tradovate", "crypto", "nt8"].map((p) =>
    React.createElement("button", {
      key: p,
      onClick: () =>
      setNewAccount({ ...newAccount, platform: p }),
      className: `py-2 rounded-lg border text-[9px] font-black uppercase tracking-widest transition-all duration-200 ${newAccount.platform === p ?
      "bg-zinc-700 text-white border-zinc-600 shadow-none" :
      "bg-black/40 text-zinc-500 border-white/5 hover:border-white/20"}` },
    p
    )
    )
    ),
    React.createElement("div", { className: "space-y-4 pt-4 border-t border-white/5" },
    React.createElement("div", { className: "grid grid-cols-2 gap-3" },
    React.createElement("div", { className: "space-y-3" },
    React.createElement("label", { className: "block text-[10px] font-black text-zinc-500 uppercase tracking-widest ml-1" }, "Identity"),
    React.createElement("input", {
      type: "text",
      placeholder: "DISPLAY NAME",
      value: newAccount.name,
      onChange: (e) => setNewAccount({ ...newAccount, name: e.target.value }),
      className: "w-full bg-black/60 border border-white/10 rounded-lg p-2.5 text-xs text-white placeholder:text-zinc-700 outline-none focus:border-zinc-500 transition-all font-bold" }
    ),
    newAccount.platform !== "tradovate" &&
    React.createElement(SearchableSelect, {
      label: "Broker / Exchange",
      placeholder: "SEARCH BROKER...",
      value: newAccount.broker,
      onChange: (val) => setNewAccount({ ...newAccount, broker: val }),
      options: availableBrokers,
      className: "z-[80]" }
    ),
    newAccount.platform !== "tradovate" &&
    React.createElement("select", {
      value: newAccount.account_type,
      onChange: (e) => setNewAccount({ ...newAccount, account_type: e.target.value }),
      className: "w-full bg-black/60 border border-white/10 rounded-xl p-3 text-xs text-white outline-none focus:border-accent transition-all font-bold" },
    React.createElement("option", { value: "demo" }, "DEMO / PAPER"),
    React.createElement("option", { value: "real" }, "LIVE / REAL")
    )
    ),
    React.createElement("div", { className: "space-y-3" },
    React.createElement("label", { className: "block text-[10px] font-black text-zinc-500 uppercase tracking-widest ml-1" }, "Source"),
    newAccount.platform === "mt5" ?
    React.createElement(SearchableSelect, {
      label: "Server / Host",
      placeholder: "SERVER NAME",
      value: newAccount.server,
      onChange: (val) => setNewAccount({ ...newAccount, server: val }),
      options: availableServers,
      className: "w-full" }
    ) :
    newAccount.platform !== "tradovate" &&
    React.createElement("input", {
      type: "text",
      placeholder: "BASE URL (OPTIONAL)",
      value: newAccount.server,
      onChange: (e) => setNewAccount({ ...newAccount, server: e.target.value }),
      className: "w-full bg-black/60 border border-white/10 rounded-xl p-3 text-xs text-white placeholder:text-zinc-700 outline-none focus:border-accent transition-all font-bold" }
    ),
    React.createElement("input", {
      type: "text",
      placeholder: newAccount.platform === "crypto" ? "API KEY" : newAccount.platform === "tradovate" ? "USERNAME" : "LOGIN / USERNAME",
      value: newAccount.platform === "crypto" ? newAccount.api_key : newAccount.login || newAccount.username,
      onChange: (e) => {
        if (newAccount.platform === "crypto") {
          setNewAccount({ ...newAccount, api_key: e.target.value });
        } else {
          setNewAccount({ ...newAccount, login: e.target.value, username: e.target.value });
        }
      },
      className: "w-full bg-black/60 border border-white/10 rounded-xl p-3 text-xs text-white placeholder:text-zinc-700 outline-none focus:border-accent transition-all font-bold" }
    ),
    React.createElement("input", {
      type: "password",
      placeholder: newAccount.platform === "crypto" ? "API SECRET" : newAccount.platform === "tradovate" ? "PASSWORD (API)" : "PASSWORD",
      value: newAccount.platform === "crypto" ? newAccount.api_secret : newAccount.password,
      onChange: (e) => {
        if (newAccount.platform === "crypto") {
          setNewAccount({ ...newAccount, api_secret: e.target.value });
        } else {
          setNewAccount({ ...newAccount, password: e.target.value });
        }
      },
      className: "w-full bg-black/60 border border-white/10 rounded-xl p-3 text-xs text-white placeholder:text-zinc-700 outline-none focus:border-accent transition-all font-bold" }
    ),
    newAccount.platform === "crypto" &&
    React.createElement("input", {
      type: "password",
      placeholder: "PASSPHRASE (IF REQ)",
      value: newAccount.passphrase,
      onChange: (e) => setNewAccount({ ...newAccount, passphrase: e.target.value }),
      className: "w-full bg-black/60 border border-white/10 rounded-xl p-3 text-xs text-white placeholder:text-zinc-700 outline-none focus:border-accent transition-all font-bold" }
    )
    )
    ),
    newAccount.platform === "tradovate" &&
    React.createElement("div", { className: "space-y-4 pt-4 border-t border-white/5" },
    React.createElement("div", { className: "grid grid-cols-2 gap-3" },
    React.createElement("div", { className: "space-y-3" },
    React.createElement("label", { className: "block text-[10px] font-black text-zinc-500 uppercase tracking-widest ml-1" }, "API Authentication"),
    React.createElement("input", {
      type: "text",
      placeholder: "CLIENT ID (CID)",
      value: newAccount.cid || "",
      onChange: (e) => setNewAccount({ ...newAccount, cid: e.target.value }),
      className: "w-full bg-black/60 border border-white/10 rounded-xl p-3 text-xs text-white placeholder:text-zinc-700 outline-none focus:border-accent transition-all font-bold" }
    ),
    React.createElement("input", {
      type: "password",
      placeholder: "SECRET KEY (SEC)",
      value: newAccount.sec || "",
      onChange: (e) => setNewAccount({ ...newAccount, sec: e.target.value }),
      className: "w-full bg-black/60 border border-white/10 rounded-xl p-3 text-xs text-white placeholder:text-zinc-700 outline-none focus:border-accent transition-all font-bold" }
    )
    ),
    React.createElement("div", { className: "space-y-3" },
    React.createElement("label", { className: "block text-[10px] font-black text-zinc-500 uppercase tracking-widest ml-1" }, "Identification"),
    React.createElement("input", {
      type: "text",
      placeholder: "APP ID",
      value: newAccount.app_id || "",
      onChange: (e) => setNewAccount({ ...newAccount, app_id: e.target.value }),
      className: "w-full bg-black/60 border border-white/10 rounded-xl p-3 text-xs text-white placeholder:text-zinc-700 outline-none focus:border-accent transition-all font-bold" }
    ),
    React.createElement("select", {
      value: newAccount.environment,
      onChange: (e) => setNewAccount({ ...newAccount, environment: e.target.value }),
      className: "w-full bg-black/60 border border-white/10 rounded-xl p-3 text-xs text-white outline-none focus:border-accent transition-all font-bold" },
    React.createElement("option", { value: "demo" }, "DEMO ENVIRONMENT"),
    React.createElement("option", { value: "real" }, "LIVE ENVIRONMENT")
    )
    )
    )
    ),
    newAccount.platform === "nt8" &&
    React.createElement("div", { className: "space-y-4 pt-4 border-t border-white/5" },
    React.createElement("div", { className: "grid grid-cols-1 gap-3" },
    React.createElement("label", { className: "block text-[10px] font-black text-zinc-500 uppercase tracking-widest ml-1" }, "Exchange Configuration"),
    React.createElement("input", {
      type: "text",
      placeholder: "EXCHANGE DIRECTORY (C:\\QuantumGAN\\Exchange)",
      value: newAccount.exchange_dir || "",
      onChange: (e) => setNewAccount({ ...newAccount, exchange_dir: e.target.value }),
      className: "w-full bg-black/60 border border-white/10 rounded-xl p-3 text-xs text-white placeholder:text-zinc-700 outline-none focus:border-accent transition-all font-bold" }
    ),
    React.createElement("select", {
      value: newAccount.account_type || "demo",
      onChange: (e) => setNewAccount({ ...newAccount, account_type: e.target.value }),
      className: "w-full bg-black/60 border border-white/10 rounded-xl p-3 text-xs text-white outline-none focus:border-accent transition-all font-bold" },
    React.createElement("option", { value: "demo" }, "DEMO / PAPER"),
    React.createElement("option", { value: "real" }, "LIVE / REAL")
    )
    )
    ),
    React.createElement("button", {
      onClick: handleAddAccount,
      className: "w-full py-2.5 bg-zinc-700 text-zinc-200 text-[10px] font-black uppercase tracking-widest rounded-lg hover:bg-zinc-600 transition-all border border-white/5 active:scale-[0.98]" },
    newAccount.id ? "Update Connection" : "Confirm Connection"
    )
    )
    )
    )
    )
    ),
    React.createElement("div", { className: "p-4 bg-black/60 border-t border-white/5 flex gap-3" },
    React.createElement("button", {
      onClick: onClose,
      className: "flex-1 py-2 text-[10px] font-black text-zinc-500 hover:text-white hover:bg-white/5 rounded-lg transition-all uppercase tracking-widest" },
    "Cancel"
    ),
    React.createElement("button", {
      onClick: save,
      className: "flex-1 py-2 bg-zinc-700 text-zinc-200 text-[10px] font-black uppercase tracking-widest rounded-lg hover:bg-zinc-600 transition-all border border-white/5 active:scale-[0.98]" },
    "Save Settings"
    )
    )
    ),
    React.createElement(ConfirmDialog, {
      isOpen: confirmDelete.isOpen,
      title: "Remove Bridge?",
      message: "Are you sure you want to delete these connection credentials? All active sessions using this bridge will be terminated.",
      onConfirm: confirmDeletion,
      onCancel: () =>
      setConfirmDelete({ isOpen: false, accountId: null, platform: null }) }
    )
    ));
};
window.SettingsModal = SettingsModal;