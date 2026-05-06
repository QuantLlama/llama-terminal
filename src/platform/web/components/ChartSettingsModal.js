const { useState, useEffect, useRef, useMemo, useCallback } = React;
const TabButton = ({ id, label, icon, activeTab, onClick }) =>
  React.createElement("button", {
    type: "button",
    onClick: () => onClick(id),
    className: `flex items-center gap-2 px-4 py-2 text-[11px] font-bold uppercase tracking-wider transition-all duration-200 border-b-2 ${activeTab === id ? "text-accent border-accent bg-accent/5" : "text-gray-500 border-transparent hover:text-gray-300 hover:bg-white/5"}`
  },
    React.createElement("i", { className: `fas fa-${icon} text-[10px]` }),
    label
  );
const ControlRow = ({ label, children }) =>
  React.createElement("div", { className: "flex items-center justify-between py-2 px-1 group" },
    React.createElement("label", { className: "text-[11px] text-gray-400 group-hover:text-gray-200 transition-colors uppercase tracking-tight" }, label),
    React.createElement("div", { className: "flex items-center gap-2" },
      children
    )
  );
const CollapsibleSection = ({ title, icon, children, isOpen: initialOpen = false, enabled, onToggleEnabled }) => {
  const [isOpen, setIsOpen] = useState(initialOpen);
  return (
    React.createElement("div", { className: `p-4 bg-white/[0.02] border border-white/5 rounded-xl transition-all duration-300 ${!enabled && onToggleEnabled ? 'opacity-60' : ''}` },
      React.createElement("div", { className: "flex items-center justify-between mb-2" },
        React.createElement("div", {
          className: "flex items-center gap-3 cursor-pointer flex-1",
          onClick: () => setIsOpen(!isOpen)
        },
          React.createElement("i", { className: `fas fa-${icon} text-accent text-xs transition-transform duration-300 ${isOpen ? 'rotate-0' : '-rotate-90'}` }),
          React.createElement("h4", { className: "text-[10px] font-black text-white uppercase tracking-[0.2em]" }, title)
        ),
        onToggleEnabled &&
        React.createElement("label", { className: "relative inline-flex items-center cursor-pointer" },
          React.createElement("input", {
            type: "checkbox",
            checked: enabled,
            onChange: (e) => onToggleEnabled(e.target.checked),
            className: "sr-only peer"
          }
          ),
          React.createElement("div", { className: "w-9 h-5 bg-white/10 peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-4 after:w-4 after:transition-all peer-checked:bg-accent" })
        )
      ),
      isOpen &&
      React.createElement("div", { className: "space-y-3 pt-2 border-t border-white/5 animate-in fade-in slide-in-from-top-2 duration-300" },
        children
      )
    ));
};
const ensureHex = (color, fallback = "#000000") => {
  if (!color || typeof color !== 'string') return fallback;
  if (color.startsWith('#') && (color.length === 7 || color.length === 4)) return color;
  if (color.startsWith('rgb')) return fallback;
  return fallback;
};
const ChartSettingsModal = ({
  isOpen,
  onClose,
  chartId,
  settings: rawSettings,
  onUpdateSettings,
  symbol,
  bigTradeConfig,
  setBigTradeConfig
}) => {
  const normalizeSettings = (s) => {
    const defaults = getDefaultChartSettings();
    return {
      ...defaults,
      ...s,
      indicators: {
        ...defaults.indicators,
        ...(s?.indicators || {}),
        orderflow: { ...defaults.indicators.orderflow, ...(s?.indicators?.orderflow || {}) },
        volumeProfile: { ...defaults.indicators.volumeProfile, ...(s?.indicators?.volumeProfile || {}) },
        tpo: { ...defaults.indicators.tpo, ...(s?.indicators?.tpo || {}) },
        bigTrades: { ...defaults.indicators.bigTrades, ...(s?.indicators?.bigTrades || {}) }
      },
      overlays: {
        ...defaults.overlays,
        ...(s?.overlays || {})
      },
      footprint: {
        ...defaults.footprint,
        ...(s?.footprint || {})
      },
      filters: { ...defaults.filters, ...(s?.filters || {}) },
      layout: { ...defaults.layout, ...(s?.layout || {}) },
      appearance: {
        ...defaults.appearance,
        ...(s?.appearance || {}),
        priceLine: { ...defaults.appearance.priceLine, ...(s?.appearance?.priceLine || {}) }
      },
      dom: {
        ...defaults.dom,
        ...(s?.dom || {})
      },
      footprint: {
        ...defaults.footprint,
        ...(s?.footprint || {})
      }
    };
  };
  const [localSettings, setLocalSettings] = useState(() =>
    normalizeSettings(rawSettings)
  );
  const [activeTab, setActiveTab] = useState("style");
  const handleFpChange = (newMode) => {
    updateLocal('footprint.mode', newMode);
    window.dispatchEvent(new CustomEvent('footprint_mode_change', {
      detail: { chartId, mode: newMode }
    }));
  };
  const handleFpSettingChange = (setting, value) => {
    updateLocal(`footprint.${setting}`, value);
    window.dispatchEvent(new CustomEvent('footprint_settings_change', {
      detail: { chartId, settings: { [setting]: value } }
    }));
  };
  const [pos, setPos] = useState({ x: 100, y: 100 });
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
    const handleMouseMove = (e) => {
      setPos({
        x: e.clientX - offsetRef.current.x,
        y: e.clientY - offsetRef.current.y
      });
    };
    const handleMouseUp = () => setIsDragging(false);
    window.addEventListener('mousemove', handleMouseMove);
    window.addEventListener('mouseup', handleMouseUp);
    return () => {
      window.removeEventListener('mousemove', handleMouseMove);
      window.removeEventListener('mouseup', handleMouseUp);
    };
  }, [isDragging]);
  const wasOpen = useRef(false);
  useEffect(() => {
    if (isOpen && !wasOpen.current) {
      setPos({ x: (window.innerWidth - 600) / 2, y: 100 });
      setLocalSettings(normalizeSettings(rawSettings));
      setActiveTab("style");
    }
    wasOpen.current = isOpen;
  }, [isOpen]);
  const updateLocal = (path, value) => {
    setLocalSettings((prev) => {
      const newSettings = JSON.parse(JSON.stringify(prev));
      if (path === 'indicators.bigTrades.enabled' && value === true) {
        newSettings.overlays.showBigTrades = true;
      }
      if (path === 'indicators.volumeProfile.enabled' && value === true) {
        newSettings.overlays.showVolume = true;
      }
      const parts = path.split('.');
      let current = newSettings;
      for (let i = 0; i < parts.length - 1; i++) {
        if (!current[parts[i]]) current[parts[i]] = {};
        current = current[parts[i]];
      }
      current[parts[parts.length - 1]] = value;
      onUpdateSettings(chartId, newSettings);
      if (path.startsWith('indicators.bigTrades') || path === 'overlays.showBigTrades') {
        if (setBigTradeConfig) {
        }
      }
      return newSettings;
    });
  };
  const handleApply = () => {
    onUpdateSettings(chartId, localSettings);
    onClose();
  };
  const handleReset = () => {
    const defaultSettings = getDefaultChartSettings();
    setLocalSettings(defaultSettings);
    onUpdateSettings(chartId, defaultSettings);
  };
  if (!isOpen) return null;
  return (
    React.createElement("div", { className: "fixed inset-0 z-[10000] pointer-events-none overflow-hidden font-sans" },
      React.createElement("div", {
        ref: dragRef,
        style: {
          position: 'absolute',
          left: `${pos.x}px`,
          top: `${pos.y}px`,
          width: '600px',
          maxHeight: '85vh'
        },
        className: "bg-[#0a0a0a]/95 border border-white/10 rounded-xl shadow-[0_20px_50px_rgba(0,0,0,0.5)] overflow-hidden flex flex-col pointer-events-auto backdrop-blur-2xl animate-in fade-in zoom-in duration-300",
        onMouseDown: handleMouseDown
      },
        React.createElement("div", { className: "drag-handle flex items-center justify-between px-5 py-4 bg-white/5 cursor-move border-b border-white/5" },
          React.createElement("div", { className: "flex items-center gap-3" },
            React.createElement("div", { className: "flex -space-x-1" },
              React.createElement("div", { className: "w-2.5 h-2.5 rounded-full bg-accent shadow-[0_0_8px_rgba(var(--accent-rgb),0.5)]" })
            ),
            React.createElement("h3", { className: "text-xs font-black text-white tracking-[0.1em] uppercase" }, "Chart Configuration")
          ),
          React.createElement("button", { type: "button", onClick: onClose, className: "p-1.5 hover:bg-white/10 rounded-lg transition-all text-gray-400 hover:text-white hover:rotate-90 duration-300" },
            React.createElement("svg", { className: "w-4 h-4", fill: "none", stroke: "currentColor", viewBox: "0 0 24 24" }, React.createElement("path", { strokeLinecap: "round", strokeLinejoin: "round", strokeWidth: 2, d: "M6 18L18 6M6 6l12 12" }))
          )
        ),
        React.createElement("div", { className: "flex px-2 bg-black/40 border-b border-white/5 overflow-x-auto no-scrollbar" },
          React.createElement(TabButton, { id: "style", label: "Style", icon: "palette", activeTab: activeTab, onClick: setActiveTab }),
          React.createElement(TabButton, { id: "indicators", label: "Indicators", icon: "chart-line", activeTab: activeTab, onClick: setActiveTab }),
          React.createElement(TabButton, { id: "layout", label: "Layout", icon: "th-large", activeTab: activeTab, onClick: setActiveTab }),
          React.createElement(TabButton, { id: "filters", label: "Filters", icon: "filter", activeTab: activeTab, onClick: setActiveTab }),
          React.createElement(TabButton, { id: "timer", label: "Timer", icon: "clock", activeTab: activeTab, onClick: setActiveTab })
        ),
        React.createElement("div", { className: "p-6 overflow-y-auto no-scrollbar flex-1", style: { maxHeight: '60vh' } },
          activeTab === "style" &&
          React.createElement("div", { className: "space-y-4 animate-in fade-in slide-in-from-left-2 duration-300" },
            React.createElement("div", { className: "border-l-2 border-accent/30 pl-3 py-1 mb-4" },
              React.createElement("h4", { className: "text-[10px] font-black text-accent uppercase tracking-widest mb-2" }, "Chart Type"),
              React.createElement(ControlRow, { label: "Display Mode" },
                React.createElement("select", { value: localSettings.chartType || 'candle', onChange: (e) => updateLocal('chartType', e.target.value), className: "text-[10px] bg-white/5 border border-white/10 rounded px-2 py-1 text-white outline-none" },
                  React.createElement("option", { value: "candle" }, "Candles"),
                  React.createElement("option", { value: "line" }, "Line"),
                  React.createElement("option", { value: "bar" }, "Bars"),
                  React.createElement("option", { value: "tpo" }, "TPO Profile")
                )
              )
            ),
            localSettings.chartType === 'tpo' &&
            React.createElement("div", { className: "space-y-4 pt-2 border-t border-white/5 animate-in fade-in slide-in-from-top-2" },
              React.createElement("div", { className: "border-l-2 border-blue-500/50 pl-3 py-1 mb-4" },
                React.createElement("h4", { className: "text-[10px] font-black text-blue-400 uppercase tracking-widest mb-2" }, "TPO Behavior"),
                React.createElement(ControlRow, { label: "Session Period" },
                  React.createElement("select", { value: localSettings.indicators.tpo.sessionPeriod, onChange: (e) => updateLocal('indicators.tpo.sessionPeriod', e.target.value), className: "text-[10px] bg-white/5 border border-white/10 rounded px-2 py-1 text-white outline-none" },
                    React.createElement("option", { value: "1d" }, "Daily (1 Day)"),
                    React.createElement("option", { value: "1w" }, "Weekly"),
                    React.createElement("option", { value: "1M" }, "Monthly")
                  )
                ),
                React.createElement(ControlRow, { label: "Block Period (mins)" },
                  React.createElement("input", { type: "number", min: 1, max: 240, step: 1, value: localSettings.indicators.tpo.blockPeriod, onChange: (e) => updateLocal('indicators.tpo.blockPeriod', parseInt(e.target.value) || 30), className: "w-16 text-[10px] bg-white/5 border border-white/10 rounded px-2 py-1 text-white outline-none" })
                ),
                React.createElement(ControlRow, { label: "Row Size (Ticks)" },
                  React.createElement("input", { type: "number", min: 0, step: 1, value: localSettings.indicators.tpo.rowSize, onChange: (e) => updateLocal('indicators.tpo.rowSize', parseInt(e.target.value) || 0), title: "0 = Auto Size", className: "w-16 text-[10px] bg-white/5 border border-white/10 rounded px-2 py-1 text-white outline-none" })
                )
              ),
              React.createElement("div", { className: "border-l-2 border-blue-500/50 pl-3 py-1 mb-4" },
                React.createElement("h4", { className: "text-[10px] font-black text-blue-400 uppercase tracking-widest mb-2" }, "TPO Colors"),
                React.createElement("div", { className: "grid grid-cols-2 gap-2" },
                  React.createElement(ControlRow, { label: "Value Area" },
                    React.createElement("input", { type: "color", value: ensureHex(localSettings.indicators.tpo.colorVA, "#3b82f6"), onChange: (e) => updateLocal('indicators.tpo.colorVA', e.target.value), className: "w-8 h-4 bg-transparent rounded cursor-pointer border-0" })
                  ),
                  React.createElement(ControlRow, { label: "Outside VA" },
                    React.createElement("input", { type: "color", value: ensureHex(localSettings.indicators.tpo.colorTPO, "#6b7280"), onChange: (e) => updateLocal('indicators.tpo.colorTPO', e.target.value), className: "w-8 h-4 bg-transparent rounded cursor-pointer border-0" })
                  ),
                  React.createElement(ControlRow, { label: "POC Line" },
                    React.createElement("input", { type: "color", value: ensureHex(localSettings.indicators.tpo.colorPOC, "#ef4444"), onChange: (e) => updateLocal('indicators.tpo.colorPOC', e.target.value), className: "w-8 h-4 bg-transparent rounded cursor-pointer border-0" })
                  ),
                  React.createElement(ControlRow, { label: "Initial Balance" },
                    React.createElement("input", { type: "color", value: ensureHex(localSettings.indicators.tpo.colorIB, "#eab308"), onChange: (e) => updateLocal('indicators.tpo.colorIB', e.target.value), className: "w-8 h-4 bg-transparent rounded cursor-pointer border-0" })
                  )
                )
              )
            ),
            localSettings.chartType !== 'tpo' &&
            React.createElement("div", { className: "border-l-2 border-accent/30 pl-3 py-1" },
              React.createElement("h4", { className: "text-[10px] font-black text-accent uppercase tracking-widest mb-2" }, "Candle Colors"),
              React.createElement(ControlRow, { label: "Bull Candle" },
                React.createElement("input", { type: "color", value: ensureHex(localSettings.appearance.upColor, "#26a69a"), onChange: (e) => updateLocal('appearance.upColor', e.target.value), className: "w-12 h-6 bg-transparent rounded cursor-pointer border-0" })
              ),
              React.createElement(ControlRow, { label: "Bear Candle" },
                React.createElement("input", { type: "color", value: ensureHex(localSettings.appearance.downColor, "#ef5350"), onChange: (e) => updateLocal('appearance.downColor', e.target.value), className: "w-12 h-6 bg-transparent rounded cursor-pointer border-0" })
              )
            ),
            React.createElement("div", { className: "border-l-2 border-white/10 pl-3 py-1" },
              React.createElement("h4", { className: "text-[10px] font-black text-gray-500 uppercase tracking-widest mb-2" }, "Environment"),
              React.createElement(ControlRow, { label: "Background" },
                React.createElement("input", { type: "color", value: ensureHex(localSettings.appearance.backgroundColor, "#000000"), onChange: (e) => updateLocal('appearance.backgroundColor', e.target.value), className: "w-12 h-6 bg-transparent rounded cursor-pointer border-0" })
              ),
              React.createElement(ControlRow, { label: "Show Grid" },
                React.createElement("input", { type: "checkbox", checked: localSettings.layout.showGrid, onChange: (e) => updateLocal('layout.showGrid', e.target.checked), className: "w-4 h-4 rounded bg-white/5 border-white/10 accent-accent" })
              ),
              React.createElement(ControlRow, { label: "Watermark" },
                React.createElement("input", { type: "checkbox", checked: localSettings.layout.showWatermark, onChange: (e) => updateLocal('layout.showWatermark', e.target.checked), className: "w-4 h-4 rounded bg-white/5 border-white/10 accent-accent" })
              )
            ),
            React.createElement("div", { className: "border-l-2 border-white/10 pl-3 py-1" },
              React.createElement("h4", { className: "text-[10px] font-black text-gray-500 uppercase tracking-widest mb-2" }, "Candle Borders"),
              React.createElement(ControlRow, { label: "Show Borders" },
                React.createElement("input", { type: "checkbox", checked: localSettings.appearance.borderVisible, onChange: (e) => updateLocal('appearance.borderVisible', e.target.checked), className: "w-4 h-4 rounded bg-white/5 border-white/10 accent-accent" })
              ),
              localSettings.appearance.borderVisible &&
              React.createElement(React.Fragment, null,
                React.createElement(ControlRow, { label: "Bull Border" },
                  React.createElement("input", { type: "color", value: ensureHex(localSettings.appearance.borderUpColor, "#26a69a"), onChange: (e) => updateLocal('appearance.borderUpColor', e.target.value), className: "w-12 h-6 bg-transparent rounded cursor-pointer border-0" })
                ),
                React.createElement(ControlRow, { label: "Bear Border" },
                  React.createElement("input", { type: "color", value: ensureHex(localSettings.appearance.borderDownColor, "#ef5350"), onChange: (e) => updateLocal('appearance.borderDownColor', e.target.value), className: "w-12 h-6 bg-transparent rounded cursor-pointer border-0" })
                )
              )
            ),
            React.createElement("div", { className: "border-l-2 border-accent/30 pl-3 py-1 mt-4" },
              React.createElement("div", { className: "flex items-center justify-between mb-2" },
                React.createElement("h4", { className: "text-[10px] font-black text-accent uppercase tracking-widest" }, "Current Price Line"),
                React.createElement("input", { type: "checkbox", checked: localSettings.appearance.priceLine.enabled, onChange: (e) => updateLocal('appearance.priceLine.enabled', e.target.checked), className: "w-4 h-4 accent-accent" })
              ),
              localSettings.appearance.priceLine.enabled &&
              React.createElement("div", { className: "space-y-2 animate-in fade-in slide-in-from-top-2 duration-300" },
                React.createElement(ControlRow, { label: "Line Color" },
                  React.createElement("input", { type: "color", value: ensureHex(localSettings.appearance.priceLine.color, "#ffffff"), onChange: (e) => updateLocal('appearance.priceLine.color', e.target.value), className: "w-12 h-6 bg-transparent rounded cursor-pointer border-0" })
                ),
                React.createElement(ControlRow, { label: "Line Width" },
                  React.createElement("input", { type: "range", min: "1", max: "5", step: "1", value: localSettings.appearance.priceLine.lineWidth, onChange: (e) => updateLocal('appearance.priceLine.lineWidth', parseInt(e.target.value)), className: "w-24 accent-accent" }),
                  React.createElement("span", { className: "text-[10px] text-gray-400 w-4" }, localSettings.appearance.priceLine.lineWidth, "px")
                ),
                React.createElement(ControlRow, { label: "Line Style" },
                  React.createElement("select", { value: localSettings.appearance.priceLine.lineStyle, onChange: (e) => updateLocal('appearance.priceLine.lineStyle', parseInt(e.target.value)), className: "text-[10px] bg-white/5 border border-white/10 rounded px-2 py-1 text-white outline-none" },
                    React.createElement("option", { value: 0 }, "Solid"),
                    React.createElement("option", { value: 1 }, "Dotted"),
                    React.createElement("option", { value: 2 }, "Dashed")
                  )
                ),
                React.createElement(ControlRow, { label: "Full Chart Width" },
                  React.createElement("input", { type: "checkbox", checked: localSettings.appearance.priceLine.fullWidth, onChange: (e) => updateLocal('appearance.priceLine.fullWidth', e.target.checked), className: "w-4 h-4 accent-accent" })
                )
              )
            ),
            React.createElement("div", { className: "border-l-2 border-accent/30 pl-3 py-1 mt-4" },
              React.createElement("div", { className: "flex items-center justify-between mb-2" },
                React.createElement("h4", { className: "text-[10px] font-black text-accent uppercase tracking-widest" }, "Daily Change Indicator"),
                React.createElement("input", { type: "checkbox", checked: localSettings.stats?.enabled ?? true, onChange: (e) => updateLocal('stats.enabled', e.target.checked), className: "w-4 h-4 accent-accent" })
              ),
              (localSettings.stats?.enabled ?? true) &&
              React.createElement("div", { className: "space-y-2 animate-in fade-in slide-in-from-top-2 duration-300" },
                React.createElement(ControlRow, { label: "Display Type" },
                  React.createElement("select", { value: localSettings.stats?.type || 'percent', onChange: (e) => updateLocal('stats.type', e.target.value), className: "text-[10px] bg-white/5 border border-white/10 rounded px-2 py-1 text-white outline-none" },
                    React.createElement("option", { value: "percent" }, "Percentage (%)"),
                    React.createElement("option", { value: "points" }, "Points (Pts)"),
                    React.createElement("option", { value: "both" }, "Both")
                  )
                ),
                React.createElement(ControlRow, { label: "Position" },
                  React.createElement("select", { value: localSettings.stats?.position || 'above-timer', onChange: (e) => updateLocal('stats.position', e.target.value), className: "text-[10px] bg-white/5 border border-white/10 rounded px-2 py-1 text-white outline-none" },
                    React.createElement("option", { value: "above-timer" }, "Above Timer"),
                    React.createElement("option", { value: "top-left" }, "Top Left"),
                    React.createElement("option", { value: "top-right" }, "Top Right"),
                    React.createElement("option", { value: "bottom-left" }, "Bottom Left"),
                    React.createElement("option", { value: "bottom-right" }, "Bottom Right")
                  )
                ),
                React.createElement(ControlRow, { label: "Font Size" },
                  React.createElement("input", { type: "range", min: "10", max: "32", step: "1", value: localSettings.stats?.fontSize || 14, onChange: (e) => updateLocal('stats.fontSize', parseInt(e.target.value)), className: "w-24 accent-accent" }),
                  React.createElement("span", { className: "text-[10px] text-gray-400 w-4" }, localSettings.stats?.fontSize || 14, "px")
                )
              )
            )
          ),
          activeTab === "indicators" &&
          React.createElement("div", { className: "space-y-4 animate-in fade-in slide-in-from-left-2 duration-300 pb-4" },
            React.createElement(CollapsibleSection, {
              title: "Order Flow System",
              icon: "wave-square",
              enabled: localSettings.indicators.orderflow.enabled,
              onToggleEnabled: (val) => updateLocal('indicators.orderflow.enabled', val)
            },
              React.createElement(ControlRow, { label: "Show VWAP" },
                React.createElement("input", { type: "checkbox", checked: localSettings.indicators.orderflow.showVwap, onChange: (e) => updateLocal('indicators.orderflow.showVwap', e.target.checked), className: "w-4 h-4 accent-accent" })
              ),
              React.createElement("div", { className: "pl-4 space-y-2" },
                React.createElement(ControlRow, { label: "VWAP Width" },
                  React.createElement("input", { type: "range", min: "1", max: "5", value: localSettings.indicators.orderflow.vwapWidth || 2, onChange: (e) => updateLocal('indicators.orderflow.vwapWidth', parseInt(e.target.value)), className: "w-20 accent-accent" })
                ),
                React.createElement(ControlRow, { label: "VWAP Color" },
                  React.createElement("input", { type: "color", value: ensureHex(localSettings.indicators.orderflow.vwapColor, "#fbbf24"), onChange: (e) => updateLocal('indicators.orderflow.vwapColor', e.target.value), className: "w-full h-6 rounded bg-transparent border-0" })
                )
              ),
              React.createElement(ControlRow, { label: "VWAP Bands" },
                React.createElement("input", { type: "checkbox", checked: localSettings.indicators.orderflow.showVwapBands, onChange: (e) => updateLocal('indicators.orderflow.showVwapBands', e.target.checked), className: "w-4 h-4 accent-accent" })
              ),
              localSettings.indicators.orderflow.showVwapBands &&
              React.createElement("div", { className: "pl-4 space-y-2" },
                React.createElement(ControlRow, { label: "Band Width" },
                  React.createElement("input", { type: "range", min: "1", max: "5", value: localSettings.indicators.orderflow.bandWidth || 1, onChange: (e) => updateLocal('indicators.orderflow.bandWidth', parseInt(e.target.value)), className: "w-20 accent-accent" })
                ),
                React.createElement("div", { className: "grid grid-cols-2 gap-2" },
                  React.createElement("div", { className: "space-y-1" },
                    React.createElement("label", { className: "text-[8px] text-gray-500 uppercase" }, "Band 1\u03C3"),
                    React.createElement("input", { type: "color", value: ensureHex(localSettings.indicators.orderflow.band1Color, "#fbbf24"), onChange: (e) => updateLocal('indicators.orderflow.band1Color', e.target.value), className: "w-full h-6 rounded bg-transparent border-0" })
                  ),
                  React.createElement("div", { className: "space-y-1" },
                    React.createElement("label", { className: "text-[8px] text-gray-500 uppercase" }, "Band 2\u03C3"),
                    React.createElement("input", { type: "color", value: ensureHex(localSettings.indicators.orderflow.band2Color, "#fbbf24"), onChange: (e) => updateLocal('indicators.orderflow.band2Color', e.target.value), className: "w-full h-6 rounded bg-transparent border-0" })
                  )
                )
              ),
              React.createElement(ControlRow, { label: "Cumulative Delta" },
                React.createElement("input", { type: "checkbox", checked: localSettings.indicators.orderflow.showCumDelta, onChange: (e) => updateLocal('indicators.orderflow.showCumDelta', e.target.checked), className: "w-4 h-4 accent-accent" })
              ),
              localSettings.indicators.orderflow.showCumDelta &&
              React.createElement("div", { className: "pl-4 space-y-2" },
                React.createElement(ControlRow, { label: "Delta Width" },
                  React.createElement("input", { type: "range", min: "1", max: "5", value: localSettings.indicators.orderflow.cumDeltaWidth || 2, onChange: (e) => updateLocal('indicators.orderflow.cumDeltaWidth', parseInt(e.target.value)), className: "w-20 accent-accent" })
                ),
                React.createElement(ControlRow, { label: "Delta Color" },
                  React.createElement("input", { type: "color", value: ensureHex(localSettings.indicators.orderflow.cumDeltaColor, "#3b82f6"), onChange: (e) => updateLocal('indicators.orderflow.cumDeltaColor', e.target.value), className: "w-full h-6 rounded bg-transparent border-0" })
                )
              ),
              React.createElement(ControlRow, { label: "Calc Limit" },
                React.createElement("input", { type: "number", step: "1000", min: "1000", max: "50000", value: localSettings.indicators.orderflow.limit || 5000, onChange: (e) => updateLocal('indicators.orderflow.limit', parseInt(e.target.value)), className: "w-20 bg-black/40 border border-white/10 rounded px-2 py-1 text-xs text-white" })
              )
            ),
            React.createElement(CollapsibleSection, {
              title: "Volume Profile",
              icon: "align-left",
              enabled: localSettings.indicators.volumeProfile.enabled,
              onToggleEnabled: (val) => updateLocal('indicators.volumeProfile.enabled', val)
            },
              React.createElement("div", { className: "grid grid-cols-1 gap-1 p-2 bg-white/[0.02] rounded-lg border border-white/5" },
                React.createElement(ControlRow, { label: "Range Mode" },
                  React.createElement("select", { value: localSettings.indicators.volumeProfile.params.rangeMode, onChange: (e) => updateLocal('indicators.volumeProfile.params.rangeMode', e.target.value), className: "text-[10px] bg-white/5 border border-white/10 rounded px-2 py-1 text-white outline-none" },
                    React.createElement("option", { value: "session" }, "Session (Daily)"),
                    React.createElement("option", { value: "weekly" }, "Weekly"),
                    React.createElement("option", { value: "monthly" }, "Monthly"),
                    React.createElement("option", { value: "hourly" }, "Hourly"),
                    React.createElement("option", { value: "visible" }, "Visible Range")
                  )
                ),
                localSettings.indicators.volumeProfile.params.rangeMode === 'hourly' &&
                React.createElement(ControlRow, { label: "Hourly Block (min)" },
                  React.createElement("input", { type: "number", min: "1", max: "240", value: localSettings.indicators.volumeProfile.params.hourlyBlock || 60, onChange: (e) => updateLocal('indicators.volumeProfile.params.hourlyBlock', parseInt(e.target.value)), className: "w-16 bg-white/5 border border-white/10 rounded px-2 py-1 text-xs text-white" })
                ),
                React.createElement(ControlRow, { label: "Profile Mode" },
                  React.createElement("select", { value: localSettings.indicators.volumeProfile.params.profileMode, onChange: (e) => updateLocal('indicators.volumeProfile.params.profileMode', e.target.value), className: "text-[10px] bg-white/5 border border-white/10 rounded px-2 py-1 text-white outline-none" },
                    React.createElement("option", { value: "volume" }, "Total Volume"),
                    React.createElement("option", { value: "delta" }, "Delta"),
                    React.createElement("option", { value: "buy-sell" }, "Buy/Sell")
                  )
                )
              ),
              React.createElement("div", { className: "space-y-2 p-2" },
                React.createElement(ControlRow, { label: "Value Area %" },
                  React.createElement("input", { type: "number", value: localSettings.indicators.volumeProfile.params.vaPercent, onChange: (e) => updateLocal('indicators.volumeProfile.params.vaPercent', parseInt(e.target.value)), className: "w-16 bg-white/5 border border-white/10 rounded px-2 py-1 text-xs text-white" })
                ),
                React.createElement(ControlRow, { label: "Bucket Count" },
                  React.createElement("input", { type: "range", min: "20", max: "300", step: "10", value: localSettings.indicators.volumeProfile.params.bucketCount || 100, onChange: (e) => updateLocal('indicators.volumeProfile.params.bucketCount', parseInt(e.target.value)), className: "w-24 accent-accent" }),
                  React.createElement("span", { className: "text-[10px] text-gray-500 w-6" }, localSettings.indicators.volumeProfile.params.bucketCount)
                ),
                React.createElement(ControlRow, { label: "Width %" },
                  React.createElement("input", { type: "range", min: "10", max: "100", value: localSettings.indicators.volumeProfile.params.histogramWidth, onChange: (e) => updateLocal('indicators.volumeProfile.params.histogramWidth', parseInt(e.target.value)), className: "w-24 accent-accent" }),
                  React.createElement("span", { className: "text-[10px] text-gray-500 w-6" }, localSettings.indicators.volumeProfile.params.histogramWidth, "%")
                ),
                React.createElement(ControlRow, { label: "Opacity %" },
                  React.createElement("input", { type: "range", min: "0", max: "100", value: (localSettings.indicators.volumeProfile.params.opacity ?? 0.5) * 100, onChange: (e) => updateLocal('indicators.volumeProfile.params.opacity', parseInt(e.target.value) / 100), className: "w-24 accent-accent" }),
                  React.createElement("span", { className: "text-[10px] text-gray-500 w-6" }, Math.round((localSettings.indicators.volumeProfile.params.opacity ?? 0.5) * 100), "%")
                )
              ),
              React.createElement("div", { className: "grid grid-cols-2 gap-2 p-2" },
                React.createElement("label", { className: "flex items-center gap-2 cursor-pointer" },
                  React.createElement("input", { type: "checkbox", checked: localSettings.indicators.volumeProfile.params.showPoc, onChange: (e) => updateLocal('indicators.volumeProfile.params.showPoc', e.target.checked), className: "w-3 h-3 accent-accent" }),
                  React.createElement("span", { className: "text-[9px] text-gray-400 uppercase font-bold" }, "POC")
                ),
                React.createElement("label", { className: "flex items-center gap-2 cursor-pointer" },
                  React.createElement("input", { type: "checkbox", checked: localSettings.indicators.volumeProfile.params.showVa, onChange: (e) => updateLocal('indicators.volumeProfile.params.showVa', e.target.checked), className: "w-3 h-3 accent-accent" }),
                  React.createElement("span", { className: "text-[9px] text-gray-400 uppercase font-bold" }, "VA")
                ),
                React.createElement("label", { className: "flex items-center gap-2 cursor-pointer" },
                  React.createElement("input", { type: "checkbox", checked: localSettings.indicators.volumeProfile.params.showLabels, onChange: (e) => updateLocal('indicators.volumeProfile.params.showLabels', e.target.checked), className: "w-3 h-3 accent-accent" }),
                  React.createElement("span", { className: "text-[9px] text-gray-400 uppercase font-bold" }, "Labels")
                ),
                React.createElement("label", { className: "flex items-center gap-2 cursor-pointer" },
                  React.createElement("input", { type: "checkbox", checked: localSettings.indicators.volumeProfile.params.extendLines, onChange: (e) => updateLocal('indicators.volumeProfile.params.extendLines', e.target.checked), className: "w-3 h-3 accent-accent" }),
                  React.createElement("span", { className: "text-[9px] text-gray-400 uppercase font-bold" }, "Extend Lines")
                )
              ),
              React.createElement("div", { className: "grid grid-cols-2 gap-3 p-2 border-t border-white/5 mt-2" },
                React.createElement("div", { className: "space-y-1" },
                  React.createElement("div", { className: "flex items-center justify-between px-0.5" },
                    React.createElement("label", { className: "text-[8px] text-gray-500 uppercase font-bold" }, "Histogram Color"),
                    React.createElement("select", { value: localSettings.indicators.volumeProfile.params.colorStyle || "spectral", onChange: (e) => updateLocal('indicators.volumeProfile.params.colorStyle', e.target.value), className: "text-[8px] bg-white/5 border border-white/10 rounded px-1 py-0.5 text-white outline-none" },
                      React.createElement("option", { value: "spectral" }, "Spectral"),
                      React.createElement("option", { value: "solid" }, "Up/Down")
                    )
                  ),
                  localSettings.indicators.volumeProfile.params.colorStyle === "solid" &&
                  React.createElement("div", { className: "flex gap-2 animate-in fade-in zoom-in duration-200" },
                    React.createElement("input", { type: "color", value: ensureHex(localSettings.indicators.volumeProfile.params.colorUp, "#26a69a"), onChange: (e) => updateLocal('indicators.volumeProfile.params.colorUp', e.target.value), className: "flex-1 h-6 bg-transparent border-0 rounded cursor-pointer", title: "Up Color" }),
                    React.createElement("input", { type: "color", value: ensureHex(localSettings.indicators.volumeProfile.params.colorDown, "#ef5350"), onChange: (e) => updateLocal('indicators.volumeProfile.params.colorDown', e.target.value), className: "flex-1 h-6 bg-transparent border-0 rounded cursor-pointer", title: "Down Color" })
                  )
                ),
                React.createElement("div", { className: "space-y-1" },
                  React.createElement("label", { className: "text-[8px] text-gray-500 uppercase font-bold px-0.5" }, "Levels (POC / VA)"),
                  React.createElement("div", { className: "flex gap-2" },
                    React.createElement("input", { type: "color", value: ensureHex(localSettings.indicators.volumeProfile.params.colorPoc, "#fbbf24"), onChange: (e) => updateLocal('indicators.volumeProfile.params.colorPoc', e.target.value), className: "flex-1 h-6 bg-transparent border-0 rounded cursor-pointer", title: "POC Line" }),
                    React.createElement("input", {
                      type: "color", value: ensureHex(localSettings.indicators.volumeProfile.params.colorVah, "#ffffff"), onChange: (e) => {
                        updateLocal('indicators.volumeProfile.params.colorVah', e.target.value);
                        updateLocal('indicators.volumeProfile.params.colorVal', e.target.value);
                      }, className: "flex-1 h-6 bg-transparent border-0 rounded cursor-pointer", title: "Value Area Lines"
                    })
                  )
                )
              )
            ),
            React.createElement(CollapsibleSection, {
              title: "Footprint Chart",
              icon: "grip-lines",
              isOpen: localSettings.footprint.mode !== 'off',
              enabled: localSettings.footprint.mode !== 'off',
              onToggleEnabled: (val) => handleFpChange(val ? 'bidask' : 'off')
            },
              React.createElement("div", { className: "space-y-3" },
                React.createElement("div", { className: "p-3 rounded-xl bg-white/[0.02] border border-white/5" },
                  React.createElement("label", { className: "text-[9px] text-gray-500 uppercase font-bold mb-2 block" }, "Display Mode"),
                  React.createElement("div", { className: "grid grid-cols-2 gap-1.5" },
                    [
                      { id: 'bidask', label: 'Bid × Ask' },
                      { id: 'volume', label: 'Volume' },
                      { id: 'delta', label: 'Delta' },
                      { id: 'volume_delta', label: 'Vol × Delta' }].
                      map((m) =>
                        React.createElement("button", {
                          key: m.id,
                          type: "button",
                          onClick: () => handleFpChange(m.id),
                          className: `px-2 py-1.5 rounded-lg text-[10px] font-bold transition-all duration-200 border ${localSettings.footprint.mode === m.id ? 'bg-accent text-black border-accent shadow-[0_0_8px_rgba(var(--accent-rgb),0.4)]' : 'bg-white/5 text-gray-400 border-white/5 hover:border-white/20 hover:text-gray-200'}`
                        },
                          m.label
                        )
                      )
                  )
                ),
                React.createElement("div", { className: "space-y-2 pt-2 border-t border-white/5" },
                  React.createElement(ControlRow, { label: "Font Size" },
                    React.createElement("input", {
                      type: "range", min: "8", max: "16", step: "1",
                      value: localSettings.footprint.fontSize,
                      onChange: (e) => handleFpSettingChange('fontSize', parseInt(e.target.value)),
                      className: "w-24 accent-accent"
                    }
                    ),
                    React.createElement("span", { className: "text-[10px] text-gray-400 w-4" }, localSettings.footprint.fontSize, "px")
                  ),
                  React.createElement(ControlRow, { label: "Show Wicks" },
                    React.createElement("input", {
                      type: "checkbox",
                      checked: localSettings.footprint.showWicks,
                      onChange: (e) => handleFpSettingChange('showWicks', e.target.checked),
                      className: "w-4 h-4 accent-accent"
                    }
                    )
                  ),
                  localSettings.footprint.showWicks &&
                  React.createElement(ControlRow, { label: "Wick Thickness" },
                    React.createElement("input", {
                      type: "range", min: "1", max: "4", step: "1",
                      value: localSettings.footprint.wickThickness,
                      onChange: (e) => handleFpSettingChange('wickThickness', parseInt(e.target.value)),
                      className: "w-24 accent-accent"
                    }
                    ),
                    React.createElement("span", { className: "text-[10px] text-gray-400 w-4" }, localSettings.footprint.wickThickness, "px")
                  ),
                  React.createElement(ControlRow, { label: "Highlight POC" },
                    React.createElement("div", { className: "flex items-center gap-2" },
                      React.createElement("input", {
                        type: "color",
                        value: localSettings.footprint.pocColor,
                        onChange: (e) => handleFpSettingChange('pocColor', e.target.value),
                        className: "w-4 h-4 rounded bg-transparent border-0 cursor-pointer"
                      }
                      ),
                      React.createElement("input", {
                        type: "checkbox",
                        checked: localSettings.footprint.showPOC,
                        onChange: (e) => handleFpSettingChange('showPOC', e.target.checked),
                        className: "w-4 h-4 accent-accent"
                      }
                      )
                    )
                  ),
                  React.createElement("div", { className: "pt-2 border-t border-white/5 space-y-2" },
                    React.createElement("div", { className: "text-[10px] text-gray-500 uppercase tracking-wider font-bold px-1" }, "Cluster Colors"),
                    React.createElement(ControlRow, { label: "Buy Cluster" },
                      React.createElement("input", {
                        type: "color",
                        value: localSettings.footprint.buyColor,
                        onChange: (e) => handleFpSettingChange('buyColor', e.target.value),
                        className: "w-8 h-4 rounded bg-transparent border-0 cursor-pointer"
                      }
                      )
                    ),
                    React.createElement(ControlRow, { label: "Sell Cluster" },
                      React.createElement("input", {
                        type: "color",
                        value: localSettings.footprint.sellColor,
                        onChange: (e) => handleFpSettingChange('sellColor', e.target.value),
                        className: "w-8 h-4 rounded bg-transparent border-0 cursor-pointer"
                      }
                      )
                    )
                  ),
                  React.createElement("div", { className: "pt-2 border-t border-white/5 space-y-2" },
                    React.createElement("div", { className: "flex items-center justify-between px-1" },
                      React.createElement("div", { className: "text-[10px] text-gray-500 uppercase tracking-wider font-bold" }, "Candle Visuals"),
                      React.createElement("label", { className: "flex items-center gap-1.5 cursor-pointer group" },
                        React.createElement("input", {
                          type: "checkbox",
                          checked: localSettings.footprint.syncWithChartColors ?? true,
                          onChange: (e) => handleFpSettingChange('syncWithChartColors', e.target.checked),
                          className: "w-3 h-3 accent-accent"
                        }),
                        React.createElement("span", { className: "text-[9px] text-gray-500 group-hover:text-gray-300 transition-colors uppercase font-bold" }, "Sync with Chart")
                      )
                    ),
                    !(localSettings.footprint.syncWithChartColors ?? true) && React.createElement(React.Fragment, null,
                      React.createElement(ControlRow, { label: "Bull Border" },
                        React.createElement("div", { className: "flex items-center gap-2" },
                          React.createElement("input", {
                            type: "color",
                            value: ensureHex(localSettings.footprint.bodyBullColor, '#00dc6e'),
                            onChange: (e) => handleFpSettingChange('bodyBullColor', e.target.value),
                            className: "w-8 h-4 rounded bg-transparent border-0 cursor-pointer"
                          }),
                          React.createElement("input", {
                            type: "range", min: "0", max: "100", step: "5",
                            value: Math.round(localSettings.footprint.bodyBullOpacity ?? 55),
                            onChange: (e) => handleFpSettingChange('bodyBullOpacity', parseInt(e.target.value)),
                            className: "w-20 accent-accent"
                          }),
                          React.createElement("span", { className: "text-[9px] text-gray-500 w-7" }, localSettings.footprint.bodyBullOpacity ?? 55, "%")
                        )
                      ),
                      React.createElement(ControlRow, { label: "Bear Border" },
                        React.createElement("div", { className: "flex items-center gap-2" },
                          React.createElement("input", {
                            type: "color",
                            value: ensureHex(localSettings.footprint.bodyBearColor, '#e6284b'),
                            onChange: (e) => handleFpSettingChange('bodyBearColor', e.target.value),
                            className: "w-8 h-4 rounded bg-transparent border-0 cursor-pointer"
                          }),
                          React.createElement("input", {
                            type: "range", min: "0", max: "100", step: "5",
                            value: Math.round(localSettings.footprint.bodyBearOpacity ?? 55),
                            onChange: (e) => handleFpSettingChange('bodyBearOpacity', parseInt(e.target.value)),
                            className: "w-20 accent-accent"
                          }),
                          React.createElement("span", { className: "text-[9px] text-gray-500 w-7" }, localSettings.footprint.bodyBearOpacity ?? 55, "%")
                        )
                      )
                    )
                  )
                ),
                React.createElement("div", { className: "p-2 rounded bg-white/[0.015] border border-white/5 space-y-1" },
                  React.createElement("div", { className: "flex items-center gap-2 text-[9px] text-gray-500" },
                    React.createElement("span", { className: "w-3 h-3 rounded-sm", style: { background: 'rgba(255,215,0,0.5)' } }), "POC \u2014 Price with max volume per candle"
                  ),
                  React.createElement("div", { className: "flex items-center gap-2 text-[9px] text-gray-500" },
                    React.createElement("span", { className: "w-3 h-3 rounded-full", style: { background: '#00e676' } }), "Buy imbalance (Ask/Bid > 3:1)"
                  ),
                  React.createElement("div", { className: "flex items-center gap-2 text-[9px] text-gray-500" },
                    React.createElement("span", { className: "w-3 h-3 rounded-full", style: { background: '#ff1744' } }), "Sell imbalance (Bid/Ask > 3:1)"
                  )
                )
              )
            ),
            React.createElement(CollapsibleSection, {
              title: "Big Trades",
              icon: "circle-dot",
              enabled: localSettings.indicators.bigTrades.enabled,
              onToggleEnabled: (val) => updateLocal('indicators.bigTrades.enabled', val)
            },
              React.createElement("div", { className: "space-y-3" },
                React.createElement("div", { className: `p-3 rounded-xl border transition-all duration-500 overflow-hidden relative ${localSettings.indicators.bigTrades.bigLlama ? 'bg-accent/10 border-accent/30 shadow-[0_0_15px_rgba(var(--accent-rgb),0.15)]' : 'bg-white/[0.02] border-white/5'}` },
                  React.createElement("div", { className: "flex items-center justify-between relative z-10" },
                    React.createElement("div", { className: "flex items-center gap-3" },
                      React.createElement("div", { className: `w-8 h-8 rounded-lg flex items-center justify-center transition-colors ${localSettings.indicators.bigTrades.bigLlama ? 'bg-accent text-black' : 'bg-white/5 text-gray-500'}` },
                        React.createElement("i", { className: "fas fa-microchip text-xs" })
                      ),
                      React.createElement("div", null,
                        React.createElement("h4", { className: "text-[10px] font-bold uppercase tracking-wider" }, "Activate Big Llama"),
                        React.createElement("p", { className: "text-[8px] text-gray-500 font-medium" }, "Evolutionary Intelligent Detection")
                      )
                    ),
                    React.createElement("div", {
                      className: `w-10 h-5 rounded-full p-1 cursor-pointer transition-colors duration-300 ${localSettings.indicators.bigTrades.bigLlama ? 'bg-accent' : 'bg-white/10'}`,
                      onClick: () => {
                        const newVal = !localSettings.indicators.bigTrades.bigLlama;
                        updateLocal('indicators.bigTrades.bigLlama', newVal);
                        fetch('/api/v2/llama/toggle', {
                          method: 'POST',
                          headers: { 'Content-Type': 'application/json' },
                          body: JSON.stringify({ type: 'big', active: newVal })
                        }).catch(() => { });
                      }
                    },
                      React.createElement("div", { className: `w-3 h-3 bg-white rounded-full transition-transform duration-300 ${localSettings.indicators.bigTrades.bigLlama ? 'translate-x-5' : 'translate-x-0'}` })
                    )
                  ),
                  localSettings.indicators.bigTrades.bigLlama &&
                  React.createElement("div", { className: "mt-2 pt-2 border-t border-accent/20 animate-in fade-in slide-in-from-top-2 duration-500" },
                    React.createElement("div", { className: "flex items-center gap-2" },
                      React.createElement("div", { className: "w-1.5 h-1.5 bg-accent rounded-full animate-pulse" }),
                      React.createElement("span", { className: "text-[8px] text-accent font-bold uppercase tracking-tighter" }, "Evolving Parameters...")
                    )
                  )
                ),
                React.createElement("div", { className: "grid grid-cols-2 gap-3" },
                  React.createElement("div", { className: "p-3 bg-white/[0.03] rounded-xl border border-white/5 space-y-4" },
                    React.createElement("div", { className: "flex items-center justify-between pb-1 border-b border-white/5" },
                      React.createElement("span", { className: "text-[10px] font-bold text-emerald-500 uppercase tracking-wider" }, "Modo Real (Tick)"),
                      React.createElement("input", { type: "checkbox", checked: localSettings.indicators.bigTrades.real?.enabled, onChange: (e) => updateLocal('indicators.bigTrades.real.enabled', e.target.checked), className: "w-4 h-4 accent-emerald-500 cursor-pointer" })
                    ),
                    localSettings.indicators.bigTrades.real?.enabled &&
                    React.createElement("div", { className: "space-y-4 animate-in fade-in duration-300" },
                      React.createElement("div", { className: "grid grid-cols-2 gap-2" },
                        React.createElement("div", { className: "space-y-1" },
                          React.createElement("label", { className: "text-[7px] text-gray-500 uppercase font-bold px-0.5" }, "Threshold"),
                          React.createElement("input", { type: "number", value: localSettings.indicators.bigTrades.real?.threshold, onChange: (e) => updateLocal('indicators.bigTrades.real.threshold', parseFloat(e.target.value) || 0), className: "w-full bg-black/40 border border-white/10 rounded px-1.5 py-1 text-[10px] text-white focus:border-emerald-500/50 outline-none" })
                        ),
                        React.createElement("div", { className: "space-y-1" },
                          React.createElement("label", { className: "text-[7px] text-gray-500 uppercase font-bold px-0.5" }, "Limit"),
                          React.createElement("input", { type: "number", value: localSettings.indicators.bigTrades.real?.displayLimit || 100, onChange: (e) => updateLocal('indicators.bigTrades.real.displayLimit', parseInt(e.target.value) || 1), className: "w-full bg-black/40 border border-white/10 rounded px-1.5 py-1 text-[10px] text-white focus:border-emerald-500/50 outline-none" })
                        )
                      ),
                      React.createElement("div", { className: "flex items-center gap-2" },
                        React.createElement("input", { type: "color", value: ensureHex(localSettings.indicators.bigTrades.real?.buyColor, "#10b981"), onChange: (e) => updateLocal('indicators.bigTrades.real.buyColor', e.target.value), className: "flex-1 h-6 bg-transparent border-0 rounded cursor-pointer" }),
                        React.createElement("input", { type: "color", value: ensureHex(localSettings.indicators.bigTrades.real?.sellColor, "#ef4444"), onChange: (e) => updateLocal('indicators.bigTrades.real.sellColor', e.target.value), className: "flex-1 h-6 bg-transparent border-0 rounded cursor-pointer" })
                      ),
                      React.createElement("div", { className: "space-y-3 pt-1" },
                        React.createElement("div", { className: "space-y-1" },
                          React.createElement("div", { className: "flex justify-between items-center px-0.5" },
                            React.createElement("span", { className: "text-[8px] text-gray-400 uppercase" }, "Bubble Scale"),
                            React.createElement("span", { className: "text-[9px] text-emerald-500 font-mono font-bold" }, localSettings.indicators.bigTrades.real?.bubbleScale?.toFixed(1))
                          ),
                          React.createElement("input", { type: "range", min: "0.5", max: "3", step: "0.1", value: localSettings.indicators.bigTrades.real?.bubbleScale || 1.0, onChange: (e) => updateLocal('indicators.bigTrades.real.bubbleScale', parseFloat(e.target.value)), className: "w-full h-1.5 accent-emerald-500 bg-white/5 rounded-full appearance-none cursor-pointer" })
                        ),
                        React.createElement("div", { className: "space-y-1" },
                          React.createElement("div", { className: "flex justify-between items-center px-0.5" },
                            React.createElement("span", { className: "text-[8px] text-gray-400 uppercase" }, "Text Size"),
                            React.createElement("span", { className: "text-[9px] text-emerald-500 font-mono font-bold" }, localSettings.indicators.bigTrades.real?.textSize?.toFixed(1))
                          ),
                          React.createElement("input", { type: "range", min: "0.5", max: "3", step: "0.1", value: localSettings.indicators.bigTrades.real?.textSize || 1.2, onChange: (e) => updateLocal('indicators.bigTrades.real.textSize', parseFloat(e.target.value)), className: "w-full h-1.5 accent-emerald-500 bg-white/5 rounded-full appearance-none cursor-pointer" })
                        ),
                        React.createElement("div", { className: "space-y-1" },
                          React.createElement("div", { className: "flex justify-between items-center px-0.5" },
                            React.createElement("span", { className: "text-[8px] text-gray-400 uppercase" }, "Opacity"),
                            React.createElement("span", { className: "text-[9px] text-emerald-500 font-mono font-bold" }, Math.floor((localSettings.indicators.bigTrades.real?.opacity || 0.4) * 100), "%")
                          ),
                          React.createElement("input", { type: "range", min: "0", max: "1", step: "0.05", value: localSettings.indicators.bigTrades.real?.opacity ?? 0.4, onChange: (e) => updateLocal('indicators.bigTrades.real.opacity', parseFloat(e.target.value)), className: "w-full h-1.5 accent-emerald-500 bg-white/5 rounded-full appearance-none cursor-pointer" })
                        )
                      ),
                      React.createElement("label", { className: "flex items-center gap-1.5 cursor-pointer pt-0.5" },
                        React.createElement("input", { type: "checkbox", checked: localSettings.indicators.bigTrades.real?.showValue, onChange: (e) => updateLocal('indicators.bigTrades.real.showValue', e.target.checked), className: "w-2.5 h-2.5 accent-emerald-500" }),
                        React.createElement("span", { className: "text-[8px] text-gray-400 uppercase" }, "Show Value")
                      )
                    )
                  ),
                  React.createElement("div", { className: "p-3 bg-white/[0.03] rounded-xl border border-white/5 space-y-4" },
                    React.createElement("div", { className: "flex items-center justify-between pb-1 border-b border-white/5" },
                      React.createElement("span", { className: "text-[10px] font-bold text-blue-500 uppercase tracking-wider" }, "Modo Acumulado"),
                      React.createElement("input", { type: "checkbox", checked: localSettings.indicators.bigTrades.cumulative?.enabled, onChange: (e) => updateLocal('indicators.bigTrades.cumulative.enabled', e.target.checked), className: "w-4 h-4 accent-blue-500 cursor-pointer" })
                    ),
                    localSettings.indicators.bigTrades.cumulative?.enabled &&
                    React.createElement("div", { className: "space-y-4 animate-in fade-in duration-300 pt-1" },
                      React.createElement("div", { className: "grid grid-cols-2 gap-2" },
                        React.createElement("div", { className: "space-y-1" },
                          React.createElement("label", { className: "text-[7px] text-gray-500 uppercase font-bold px-0.5" }, "Threshold"),
                          React.createElement("input", { type: "number", value: localSettings.indicators.bigTrades.cumulative?.threshold, onChange: (e) => updateLocal('indicators.bigTrades.cumulative.threshold', parseFloat(e.target.value) || 0), className: "w-full bg-black/40 border border-white/10 rounded px-1.5 py-1 text-[10px] text-white focus:border-blue-500/50 outline-none" })
                        ),
                        React.createElement("div", { className: "space-y-1" },
                          React.createElement("label", { className: "text-[7px] text-gray-500 uppercase font-bold px-0.5" }, "Window (ms)"),
                          React.createElement("input", { type: "number", value: localSettings.indicators.bigTrades.cumulative?.window, onChange: (e) => updateLocal('indicators.bigTrades.cumulative.window', parseInt(e.target.value) || 0), className: "w-full bg-black/40 border border-white/10 rounded px-1.5 py-1 text-[10px] text-white focus:border-blue-500/50 outline-none" })
                        )
                      ),
                      React.createElement("div", { className: "grid grid-cols-2 gap-2" },
                        React.createElement("div", { className: "space-y-1" },
                          React.createElement("label", { className: "text-[7px] text-gray-500 uppercase font-bold px-0.5" }, "Limit"),
                          React.createElement("input", { type: "number", value: localSettings.indicators.bigTrades.cumulative?.displayLimit || 100, onChange: (e) => updateLocal('indicators.bigTrades.cumulative.displayLimit', parseInt(e.target.value) || 1), className: "w-full bg-black/40 border border-white/10 rounded px-1.5 py-1 text-[10px] text-white focus:border-blue-500/50 outline-none" })
                        ),
                        React.createElement("div", { className: "space-y-1" },
                          React.createElement("label", { className: "text-[7px] text-blue-400 uppercase font-bold px-0.5" }, "Absorption Sens."),
                          React.createElement("input", { type: "number", step: "0.1", value: localSettings.indicators.bigTrades.cumulative?.absorptionFactor || 2.0, onChange: (e) => updateLocal('indicators.bigTrades.cumulative.absorptionFactor', parseFloat(e.target.value) || 2.0), title: "Lower values = stricter absorption detection", className: "w-full bg-black/40 border border-white/10 rounded px-1.5 py-1 text-[10px] text-white focus:border-blue-500/50 outline-none" })
                        )
                      ),
                      React.createElement("div", { className: "flex items-center gap-2" },
                        React.createElement("input", { type: "color", value: ensureHex(localSettings.indicators.bigTrades.cumulative?.buyColor, "#3b82f6"), onChange: (e) => updateLocal('indicators.bigTrades.cumulative.buyColor', e.target.value), className: "flex-1 h-6 bg-transparent border-0 rounded cursor-pointer" }),
                        React.createElement("input", { type: "color", value: ensureHex(localSettings.indicators.bigTrades.cumulative?.sellColor, "#f59e0b"), onChange: (e) => updateLocal('indicators.bigTrades.cumulative.sellColor', e.target.value), className: "flex-1 h-6 bg-transparent border-0 rounded cursor-pointer" })
                      ),
                      React.createElement("div", { className: "space-y-3 pt-1" },
                        React.createElement("div", { className: "space-y-1" },
                          React.createElement("div", { className: "flex justify-between items-center px-0.5" },
                            React.createElement("span", { className: "text-[8px] text-gray-400 uppercase" }, "Bubble Scale"),
                            React.createElement("span", { className: "text-[9px] text-blue-500 font-mono font-bold" }, localSettings.indicators.bigTrades.cumulative?.bubbleScale?.toFixed(1))
                          ),
                          React.createElement("input", { type: "range", min: "0.5", max: "3", step: "0.1", value: localSettings.indicators.bigTrades.cumulative?.bubbleScale || 1.2, onChange: (e) => updateLocal('indicators.bigTrades.cumulative.bubbleScale', parseFloat(e.target.value)), className: "w-full h-1.5 accent-blue-500 bg-white/5 rounded-full appearance-none cursor-pointer" })
                        ),
                        React.createElement("div", { className: "space-y-1" },
                          React.createElement("div", { className: "flex justify-between items-center px-0.5" },
                            React.createElement("span", { className: "text-[8px] text-gray-400 uppercase" }, "Text Size"),
                            React.createElement("span", { className: "text-[9px] text-blue-500 font-mono font-bold" }, localSettings.indicators.bigTrades.cumulative?.textSize?.toFixed(1))
                          ),
                          React.createElement("input", { type: "range", min: "0.5", max: "3", step: "0.1", value: localSettings.indicators.bigTrades.cumulative?.textSize || 1.2, onChange: (e) => updateLocal('indicators.bigTrades.cumulative.textSize', parseFloat(e.target.value)), className: "w-full h-1.5 accent-blue-500 bg-white/5 rounded-full appearance-none cursor-pointer" })
                        ),
                        React.createElement("div", { className: "space-y-1" },
                          React.createElement("div", { className: "flex justify-between items-center px-0.5" },
                            React.createElement("span", { className: "text-[8px] text-gray-400 uppercase" }, "Opacity"),
                            React.createElement("span", { className: "text-[9px] text-blue-500 font-mono font-bold" }, Math.floor((localSettings.indicators.bigTrades.cumulative?.opacity || 0.6) * 100), "%")
                          ),
                          React.createElement("input", { type: "range", min: "0", max: "1", step: "0.05", value: localSettings.indicators.bigTrades.cumulative?.opacity ?? 0.6, onChange: (e) => updateLocal('indicators.bigTrades.cumulative.opacity', parseFloat(e.target.value)), className: "w-full h-1.5 accent-blue-500 bg-white/5 rounded-full appearance-none cursor-pointer" })
                        )
                      ),
                      React.createElement("label", { className: "flex items-center gap-2 cursor-pointer pt-1 hover:text-white transition-colors" },
                        React.createElement("input", { type: "checkbox", checked: localSettings.indicators.bigTrades.cumulative?.showValue, onChange: (e) => updateLocal('indicators.bigTrades.cumulative.showValue', e.target.checked), className: "w-3.5 h-3.5 accent-blue-500 rounded" }),
                        React.createElement("span", { className: "text-[9px] text-gray-400 uppercase font-medium" }, "Show Value")
                      )
                    )
                  )
                )
              )
            ),
            React.createElement(CollapsibleSection, { title: "Volume & Delta", icon: "chart-bar", enabled: true },
              React.createElement("div", { className: "space-y-4" },
                React.createElement("div", { className: "space-y-1" },
                  React.createElement("div", { className: "flex items-center justify-between" },
                    React.createElement("label", { className: "flex items-center gap-2 cursor-pointer" },
                      React.createElement("input", { type: "checkbox", checked: localSettings.overlays.showVolume, onChange: (e) => updateLocal('overlays.showVolume', e.target.checked), className: "w-3 h-3 accent-accent" }),
                      React.createElement("span", { className: "text-[10px] text-gray-400 uppercase" }, "Show Volume")
                    ),
                    React.createElement("input", { type: "color", value: ensureHex(localSettings.filters.volumeColor, "#10b981"), onChange: (e) => updateLocal('filters.volumeColor', e.target.value), className: "w-8 h-5 bg-transparent border-0" })
                  ),
                  React.createElement(ControlRow, { label: "Volume Opacity" },
                    React.createElement("div", { className: "flex items-center gap-2" },
                      React.createElement("input", { 
                        type: "range", 
                        min: "0", 
                        max: "1", 
                        step: "0.05", 
                        value: localSettings.filters.volumeOpacity ?? 0.8, 
                        onChange: (e) => updateLocal('filters.volumeOpacity', parseFloat(e.target.value)), 
                        className: "w-24 h-1.5 accent-accent bg-white/5 rounded-full appearance-none cursor-pointer" 
                      }),
                      React.createElement("span", { className: "text-[9px] text-gray-400 w-8 text-right font-mono" }, Math.round((localSettings.filters.volumeOpacity ?? 0.8) * 100), "%")
                    )
                  )
                ),
                React.createElement("div", { className: "space-y-2" },
                  React.createElement("div", { className: "flex items-center justify-between" },
                    React.createElement("label", { className: "flex items-center gap-2 cursor-pointer" },
                      React.createElement("input", { type: "checkbox", checked: localSettings.overlays.showDelta, onChange: (e) => updateLocal('overlays.showDelta', e.target.checked), className: "w-3 h-3 accent-accent" }),
                      React.createElement("span", { className: "text-[10px] text-gray-400 uppercase" }, "Show Delta")
                    ),
                    React.createElement("input", { type: "color", value: ensureHex(localSettings.filters.deltaColor, "#3b82f6"), onChange: (e) => updateLocal('filters.deltaColor', e.target.value), className: "w-8 h-5 bg-transparent border-0" })
                  ),
                  React.createElement(ControlRow, { label: "Display Mode" },
                    React.createElement("select", {
                      value: localSettings.filters.deltaDisplayMode || "histogram",
                      onChange: (e) => updateLocal('filters.deltaDisplayMode', e.target.value),
                      className: "text-[10px] bg-white/5 border border-white/10 rounded px-2 py-1 text-white outline-none focus:border-accent/50"
                    },
                      React.createElement("option", { value: "histogram" }, "Histogram"),
                      React.createElement("option", { value: "deltaBars" }, "Delta Table"),
                      React.createElement("option", { value: "cumulativeCandles" }, "Cumulative Candles"),
                      React.createElement("option", { value: "cumulativeLine" }, "Cumulative Line")
                    )
                  ),
                  React.createElement(ControlRow, { label: "Delta Opacity" },
                    React.createElement("div", { className: "flex items-center gap-2" },
                      React.createElement("input", { 
                        type: "range", 
                        min: "0", 
                        max: "1", 
                        step: "0.05", 
                        value: localSettings.filters.deltaOpacity ?? 0.8, 
                        onChange: (e) => updateLocal('filters.deltaOpacity', parseFloat(e.target.value)), 
                        className: "w-24 h-1.5 accent-accent bg-white/5 rounded-full appearance-none cursor-pointer" 
                      }),
                      React.createElement("span", { className: "text-[9px] text-gray-400 w-8 text-right font-mono" }, Math.round((localSettings.filters.deltaOpacity ?? 0.8) * 100), "%")
                    )
                  ),
                  // ── Conditional color controls per display mode ──
                  (localSettings.filters.deltaDisplayMode === "histogram" || localSettings.filters.deltaDisplayMode === "deltaBars" || !localSettings.filters.deltaDisplayMode) &&
                  React.createElement("div", { className: "p-2 bg-black/30 rounded-lg border border-white/5" },
                    React.createElement("p", { className: "text-[9px] text-gray-500 uppercase font-bold tracking-wider mb-2" },
                      localSettings.filters.deltaDisplayMode === "deltaBars" ? "Delta Table Colors" : "Histogram Colors"
                    ),
                    React.createElement("div", { className: "grid grid-cols-2 gap-2" },
                      React.createElement("div", { className: "space-y-1" },
                        React.createElement("label", { className: "text-[8px] text-gray-500 uppercase" }, "Positive \u2191"),
                        React.createElement("input", { type: "color", value: ensureHex(localSettings.filters.deltaPositiveColor, "#26a69a"), onChange: (e) => updateLocal('filters.deltaPositiveColor', e.target.value), className: "w-full h-6 bg-transparent border-0 rounded cursor-pointer" })
                      ),
                      React.createElement("div", { className: "space-y-1" },
                        React.createElement("label", { className: "text-[8px] text-gray-500 uppercase" }, "Negative \u2193"),
                        React.createElement("input", { type: "color", value: ensureHex(localSettings.filters.deltaNegativeColor, "#ef5350"), onChange: (e) => updateLocal('filters.deltaNegativeColor', e.target.value), className: "w-full h-6 bg-transparent border-0 rounded cursor-pointer" })
                      )
                    )
                  ),
                  localSettings.filters.deltaDisplayMode === "cumulativeCandles" &&
                  React.createElement("div", { className: "p-2 bg-black/30 rounded-lg border border-white/5" },
                    React.createElement("p", { className: "text-[9px] text-gray-500 uppercase font-bold tracking-wider mb-2" }, "Cumulative Candle Colors"),
                    React.createElement("div", { className: "grid grid-cols-2 gap-2" },
                      React.createElement("div", { className: "space-y-1" },
                        React.createElement("label", { className: "text-[8px] text-gray-500 uppercase" }, "Up Candle"),
                        React.createElement("input", { type: "color", value: ensureHex(localSettings.filters.deltaCumPositiveColor, "#26a69a"), onChange: (e) => updateLocal('filters.deltaCumPositiveColor', e.target.value), className: "w-full h-6 bg-transparent border-0 rounded cursor-pointer" })
                      ),
                      React.createElement("div", { className: "space-y-1" },
                        React.createElement("label", { className: "text-[8px] text-gray-500 uppercase" }, "Down Candle"),
                        React.createElement("input", { type: "color", value: ensureHex(localSettings.filters.deltaCumNegativeColor, "#ef5350"), onChange: (e) => updateLocal('filters.deltaCumNegativeColor', e.target.value), className: "w-full h-6 bg-transparent border-0 rounded cursor-pointer" })
                      )
                    )
                  ),
                  localSettings.filters.deltaDisplayMode === "cumulativeLine" &&
                  React.createElement("div", { className: "p-2 bg-black/30 rounded-lg border border-white/5" },
                    React.createElement("p", { className: "text-[9px] text-gray-500 uppercase font-bold tracking-wider mb-2" }, "Cumulative Line Style"),
                    React.createElement("div", { className: "grid grid-cols-2 gap-2" },
                      React.createElement("div", { className: "space-y-1" },
                        React.createElement("label", { className: "text-[8px] text-gray-500 uppercase" }, "Color"),
                        React.createElement("input", { type: "color", value: ensureHex(localSettings.filters.deltaCumLineColor, "#3b82f6"), onChange: (e) => updateLocal('filters.deltaCumLineColor', e.target.value), className: "w-full h-6 bg-transparent border-0 rounded cursor-pointer" })
                      ),
                      React.createElement("div", { className: "space-y-1" },
                        React.createElement("label", { className: "text-[8px] text-gray-500 uppercase" }, "Width"),
                        React.createElement("input", { type: "range", min: "1", max: "4", step: "1", value: localSettings.filters.deltaCumLineWidth ?? 2, onChange: (e) => updateLocal('filters.deltaCumLineWidth', parseInt(e.target.value)), className: "w-full accent-accent" })
                      )
                    )
                  )
                )
              )
            ),
            React.createElement(CollapsibleSection, {
              title: "Imbalance Impulse",
              icon: "balance-scale",
              enabled: localSettings.indicators.imbalance.enabled,
              onToggleEnabled: (val) => updateLocal('indicators.imbalance.enabled', val)
            },
              React.createElement("div", { className: "space-y-3" },
                React.createElement("div", { className: `p-3 rounded-xl border transition-all duration-500 overflow-hidden relative ${localSettings.indicators.imbalance.llama ? 'bg-accent/10 border-accent/30 shadow-[0_0_15px_rgba(var(--accent-rgb),0.15)]' : 'bg-white/[0.02] border-white/5'}` },
                  React.createElement("div", { className: "flex items-center justify-between relative z-10" },
                    React.createElement("div", { className: "flex items-center gap-3" },
                      React.createElement("div", { className: `w-8 h-8 rounded-lg flex items-center justify-center transition-colors ${localSettings.indicators.imbalance.llama ? 'bg-accent text-black' : 'bg-white/5 text-gray-500'}` },
                        React.createElement("i", { className: "fas fa-microchip text-xs" })
                      ),
                      React.createElement("div", null,
                        React.createElement("h4", { className: "text-[10px] font-bold uppercase tracking-wider" }, "Inbalance Llama"),
                        React.createElement("p", { className: "text-[8px] text-gray-500 font-medium" }, "Evolutionary Parameter Tuning")
                      )
                    ),
                    React.createElement("div", {
                      className: `w-10 h-5 rounded-full p-1 cursor-pointer transition-colors duration-300 ${localSettings.indicators.imbalance.llama ? 'bg-accent' : 'bg-white/10'}`,
                      onClick: () => {
                        const newVal = !localSettings.indicators.imbalance.llama;
                        updateLocal('indicators.imbalance.llama', newVal);
                        fetch('/api/v2/llama/toggle', {
                          method: 'POST',
                          headers: { 'Content-Type': 'application/json' },
                          body: JSON.stringify({ type: 'inbalance', active: newVal })
                        }).catch(() => { });
                      }
                    },
                      React.createElement("div", { className: `w-3 h-3 bg-white rounded-full transition-transform duration-300 ${localSettings.indicators.imbalance.llama ? 'translate-x-5' : 'translate-x-0'}` })
                    )
                  )
                ),
                React.createElement("div", { className: "p-2 bg-black/30 rounded-lg border border-white/5" },
                  React.createElement("p", { className: "text-[9px] text-gray-500 uppercase font-bold tracking-wider mb-2" }, "Algorithm"),
                  React.createElement("div", { className: "space-y-2" },
                    React.createElement(ControlRow, { label: "Delta Threshold" },
                      React.createElement("input", { type: "number", step: "0.01", min: "0.01", max: "1", value: localSettings.indicators.imbalance.params?.delta_threshold ?? 0.15, onChange: (e) => updateLocal('indicators.imbalance.params.delta_threshold', parseFloat(e.target.value)), className: "w-20 bg-black/40 border border-white/10 rounded px-2 py-1 text-xs text-white" })
                    ),
                    React.createElement(ControlRow, { label: "Vol Multiplier" },
                      React.createElement("input", { type: "number", step: "0.1", min: "0.1", max: "3", value: localSettings.indicators.imbalance.params?.volume_multiplier ?? 0.5, onChange: (e) => updateLocal('indicators.imbalance.params.volume_multiplier', parseFloat(e.target.value)), className: "w-20 bg-black/40 border border-white/10 rounded px-2 py-1 text-xs text-white" })
                    ),
                    React.createElement(ControlRow, { label: "Min Body Ratio" },
                      React.createElement("input", { type: "number", step: "0.05", min: "0.05", max: "1", value: localSettings.indicators.imbalance.params?.min_body_ratio ?? 0.20, onChange: (e) => updateLocal('indicators.imbalance.params.min_body_ratio', parseFloat(e.target.value)), className: "w-20 bg-black/40 border border-white/10 rounded px-2 py-1 text-xs text-white" })
                    ),
                    React.createElement(ControlRow, { label: "Min Bars Between" },
                      React.createElement("input", { type: "number", step: "1", min: "1", max: "50", value: localSettings.indicators.imbalance.params?.min_bars_between ?? 3, onChange: (e) => updateLocal('indicators.imbalance.params.min_bars_between', parseInt(e.target.value)), className: "w-20 bg-black/40 border border-white/10 rounded px-2 py-1 text-xs text-white" })
                    ),
                    React.createElement(ControlRow, { label: "Structure Lookback" },
                      React.createElement("input", { type: "number", step: "1", min: "1", max: "20", value: localSettings.indicators.imbalance.params?.structure_lookback ?? 3, onChange: (e) => updateLocal('indicators.imbalance.params.structure_lookback', parseInt(e.target.value)), className: "w-20 bg-black/40 border border-white/10 rounded px-2 py-1 text-xs text-white" })
                    ),
                    React.createElement(ControlRow, { label: "ATR Multiplier" },
                      React.createElement("input", { type: "number", step: "0.1", min: "0.1", max: "5", value: localSettings.indicators.imbalance.params?.atr_multiplier ?? 0.6, onChange: (e) => updateLocal('indicators.imbalance.params.atr_multiplier', parseFloat(e.target.value)), className: "w-20 bg-black/40 border border-white/10 rounded px-2 py-1 text-xs text-white" })
                    )
                  )
                ),
                React.createElement("div", { className: "p-2 bg-black/30 rounded-lg border border-white/5" },
                  React.createElement("p", { className: "text-[9px] text-gray-500 uppercase font-bold tracking-wider mb-2" }, "Filters"),
                  React.createElement("label", { className: "flex items-center gap-2 cursor-pointer p-1 hover:text-white transition-colors" },
                    React.createElement("input", { type: "checkbox", checked: localSettings.indicators.imbalance.params?.use_structure ?? true, onChange: (e) => updateLocal('indicators.imbalance.params.use_structure', e.target.checked), className: "w-3.5 h-3.5 accent-accent" }),
                    React.createElement("span", { className: "text-[9px] text-gray-400 uppercase" }, "Use Structure Filter")
                  ),
                  React.createElement("label", { className: "flex items-center gap-2 cursor-pointer p-1 hover:text-white transition-colors" },
                    React.createElement("input", { type: "checkbox", checked: localSettings.indicators.imbalance.params?.use_volume_filter ?? true, onChange: (e) => updateLocal('indicators.imbalance.params.use_volume_filter', e.target.checked), className: "w-3.5 h-3.5 accent-accent" }),
                    React.createElement("span", { className: "text-[9px] text-gray-400 uppercase" }, "Use Volume Filter")
                  )
                ),
                React.createElement("div", { className: "p-2 bg-black/30 rounded-lg border border-white/5" },
                  React.createElement("p", { className: "text-[9px] text-gray-500 uppercase font-bold tracking-wider mb-2" }, "Arrows"),
                  React.createElement("div", { className: "grid grid-cols-2 gap-2" },
                    React.createElement("div", { className: "space-y-1" },
                      React.createElement("label", { className: "text-[8px] text-gray-500 uppercase" }, "Buy \u2191"),
                      React.createElement("input", { type: "color", value: ensureHex(localSettings.indicators.imbalance.buyColor, "#22c55e"), onChange: (e) => updateLocal('indicators.imbalance.buyColor', e.target.value), className: "w-full h-6 bg-transparent border-0 rounded cursor-pointer" })
                    ),
                    React.createElement("div", { className: "space-y-1" },
                      React.createElement("label", { className: "text-[8px] text-gray-500 uppercase" }, "Sell \u2193"),
                      React.createElement("input", { type: "color", value: ensureHex(localSettings.indicators.imbalance.sellColor, "#ef4444"), onChange: (e) => updateLocal('indicators.imbalance.sellColor', e.target.value), className: "w-full h-6 bg-transparent border-0 rounded cursor-pointer" })
                    )
                  ),
                  React.createElement(ControlRow, { label: "Signal Size" },
                    React.createElement("input", { type: "range", min: "1", max: "4", step: "1", value: localSettings.indicators.imbalance.signalSize ?? 1, onChange: (e) => updateLocal('indicators.imbalance.signalSize', parseInt(e.target.value)), className: "w-20 accent-accent" }),
                    React.createElement("span", { className: "text-[9px] text-gray-500 w-4" }, localSettings.indicators.imbalance.signalSize ?? 1)
                  )
                )
              )
            ),
            React.createElement(CollapsibleSection, {
              title: "CazaStop PRO",
              icon: "crosshairs",
              enabled: localSettings.indicators.cazastop.enabled,
              onToggleEnabled: (val) => updateLocal('indicators.cazastop.enabled', val)
            },
              React.createElement("div", { className: "space-y-3" },
                React.createElement("div", { className: `p-3 rounded-xl border transition-all duration-500 overflow-hidden relative ${localSettings.indicators.cazastop.llama ? 'bg-accent/10 border-accent/30 shadow-[0_0_15px_rgba(var(--accent-rgb),0.15)]' : 'bg-white/[0.02] border-white/5'}` },
                  React.createElement("div", { className: "flex items-center justify-between relative z-10" },
                    React.createElement("div", { className: "flex items-center gap-3" },
                      React.createElement("div", { className: `w-8 h-8 rounded-lg flex items-center justify-center transition-colors ${localSettings.indicators.cazastop.llama ? 'bg-accent text-black' : 'bg-white/5 text-gray-500'}` },
                        React.createElement("i", { className: "fas fa-microchip text-xs" })
                      ),
                      React.createElement("div", null,
                        React.createElement("h4", { className: "text-[10px] font-bold uppercase tracking-wider" }, "Caza Llama"),
                        React.createElement("p", { className: "text-[8px] text-gray-500 font-medium" }, "Evolutionary Market Structure Adaptation")
                      )
                    ),
                    React.createElement("div", {
                      className: `w-10 h-5 rounded-full p-1 cursor-pointer transition-colors duration-300 ${localSettings.indicators.cazastop.llama ? 'bg-accent' : 'bg-white/10'}`,
                      onClick: () => {
                        const newVal = !localSettings.indicators.cazastop.llama;
                        updateLocal('indicators.cazastop.llama', newVal);
                        fetch('/api/v2/llama/toggle', {
                          method: 'POST',
                          headers: { 'Content-Type': 'application/json' },
                          body: JSON.stringify({ type: 'caza', active: newVal })
                        }).catch(() => { });
                      }
                    },
                      React.createElement("div", { className: `w-3 h-3 bg-white rounded-full transition-transform duration-300 ${localSettings.indicators.cazastop.llama ? 'translate-x-5' : 'translate-x-0'}` })
                    )
                  )
                ),
                React.createElement("div", { className: "p-2 bg-black/30 rounded-lg border border-white/5" },
                  React.createElement("p", { className: "text-[9px] text-gray-500 uppercase font-bold tracking-wider mb-2" }, "Zone Detection"),
                  React.createElement("div", { className: "space-y-2" },
                    React.createElement(ControlRow, { label: "Swing Bars" },
                      React.createElement("input", { type: "number", step: "1", min: "2", max: "20", value: localSettings.indicators.cazastop.params?.swing_bars ?? 5, onChange: (e) => updateLocal('indicators.cazastop.params.swing_bars', parseInt(e.target.value)), className: "w-20 bg-black/40 border border-white/10 rounded px-2 py-1 text-xs text-white" })
                    ),
                    React.createElement(ControlRow, { label: "Lookback" },
                      React.createElement("input", { type: "number", step: "1", min: "5", max: "100", value: localSettings.indicators.cazastop.params?.lookback ?? 10, onChange: (e) => updateLocal('indicators.cazastop.params.lookback', parseInt(e.target.value)), className: "w-20 bg-black/40 border border-white/10 rounded px-2 py-1 text-xs text-white" })
                    ),
                    React.createElement(ControlRow, { label: "Dist Ticks" },
                      React.createElement("input", { type: "number", step: "5", min: "5", max: "500", value: localSettings.indicators.cazastop.params?.dist_ticks ?? 60, onChange: (e) => updateLocal('indicators.cazastop.params.dist_ticks', parseInt(e.target.value)), className: "w-20 bg-black/40 border border-white/10 rounded px-2 py-1 text-xs text-white" })
                    ),
                    React.createElement(ControlRow, { label: "Buffer Ticks" },
                      React.createElement("input", { type: "number", step: "1", min: "1", max: "100", value: localSettings.indicators.cazastop.params?.buffer_ticks ?? 10, onChange: (e) => updateLocal('indicators.cazastop.params.buffer_ticks', parseInt(e.target.value)), className: "w-20 bg-black/40 border border-white/10 rounded px-2 py-1 text-xs text-white" })
                    ),
                    React.createElement(ControlRow, { label: "Max Zone Life" },
                      React.createElement("input", { type: "number", step: "5", min: "5", max: "200", value: localSettings.indicators.cazastop.params?.vida_max ?? 30, onChange: (e) => updateLocal('indicators.cazastop.params.vida_max', parseInt(e.target.value)), className: "w-20 bg-black/40 border border-white/10 rounded px-2 py-1 text-xs text-white" })
                    )
                  ),
                  React.createElement("div", { className: "pt-2 space-y-1" },
                    React.createElement("label", { className: "flex items-center gap-2 cursor-pointer p-1 hover:text-white transition-colors" },
                      React.createElement("input", { type: "checkbox", checked: localSettings.indicators.cazastop.params?.analisis_vol ?? true, onChange: (e) => updateLocal('indicators.cazastop.params.analisis_vol', e.target.checked), className: "w-3.5 h-3.5 accent-accent" }),
                      React.createElement("span", { className: "text-[9px] text-gray-400 uppercase" }, "Volume Analysis")
                    ),
                    React.createElement("label", { className: "flex items-center gap-2 cursor-pointer p-1 hover:text-white transition-colors" },
                      React.createElement("input", { type: "checkbox", checked: localSettings.indicators.cazastop.params?.dibujar_safe ?? true, onChange: (e) => updateLocal('indicators.cazastop.params.dibujar_safe', e.target.checked), className: "w-3.5 h-3.5 accent-accent" }),
                      React.createElement("span", { className: "text-[9px] text-gray-400 uppercase" }, "Draw Safe Zones")
                    )
                  )
                ),
                React.createElement("div", { className: "p-2 bg-black/30 rounded-lg border border-white/5" },
                  React.createElement("div", { className: "flex items-center justify-between mb-2" },
                    React.createElement("p", { className: "text-[9px] text-gray-500 uppercase font-bold tracking-wider" }, "TP / POC Zone"),
                    React.createElement("label", { className: "flex items-center gap-1.5 cursor-pointer" },
                      React.createElement("input", { type: "checkbox", checked: localSettings.indicators.cazastop.params?.mostrar_tp ?? true, onChange: (e) => updateLocal('indicators.cazastop.params.mostrar_tp', e.target.checked), className: "w-3 h-3 accent-accent" }),
                      React.createElement("span", { className: "text-[9px] text-gray-400" }, "Show")
                    )
                  ),
                  (localSettings.indicators.cazastop.params?.mostrar_tp ?? true) &&
                  React.createElement("div", { className: "space-y-2" },
                    React.createElement(ControlRow, { label: "Lookback" },
                      React.createElement("input", { type: "number", step: "10", min: "10", max: "500", value: localSettings.indicators.cazastop.params?.lookback_tp ?? 100, onChange: (e) => updateLocal('indicators.cazastop.params.lookback_tp', parseInt(e.target.value)), className: "w-20 bg-black/40 border border-white/10 rounded px-2 py-1 text-xs text-white" })
                    ),
                    React.createElement(ControlRow, { label: "Ticks Range" },
                      React.createElement("input", { type: "number", step: "1", min: "1", max: "50", value: localSettings.indicators.cazastop.params?.ticks_tp ?? 6, onChange: (e) => updateLocal('indicators.cazastop.params.ticks_tp', parseInt(e.target.value)), className: "w-20 bg-black/40 border border-white/10 rounded px-2 py-1 text-xs text-white" })
                    )
                  )
                ),
                React.createElement("div", { className: "p-2 bg-black/30 rounded-lg border border-white/5" },
                  React.createElement("p", { className: "text-[9px] text-gray-500 uppercase font-bold tracking-wider mb-2" }, "Visual"),
                  React.createElement("div", { className: "grid grid-cols-3 gap-2 mb-3" },
                    React.createElement("div", { className: "space-y-1" },
                      React.createElement("label", { className: "text-[8px] text-gray-500 uppercase" }, "Zone Top"),
                      React.createElement("input", { type: "color", value: ensureHex(localSettings.indicators.cazastop.colorTop, "#ef4444"), onChange: (e) => updateLocal('indicators.cazastop.colorTop', e.target.value), className: "w-full h-6 bg-transparent border-0 rounded cursor-pointer" })
                    ),
                    React.createElement("div", { className: "space-y-1" },
                      React.createElement("label", { className: "text-[8px] text-gray-500 uppercase" }, "Zone Bot"),
                      React.createElement("input", { type: "color", value: ensureHex(localSettings.indicators.cazastop.colorBottom, "#ef4444"), onChange: (e) => updateLocal('indicators.cazastop.colorBottom', e.target.value), className: "w-full h-6 bg-transparent border-0 rounded cursor-pointer" })
                    ),
                    React.createElement("div", { className: "space-y-1" },
                      React.createElement("label", { className: "text-[8px] text-gray-500 uppercase" }, "POC"),
                      React.createElement("input", { type: "color", value: ensureHex(localSettings.indicators.cazastop.colorPoc, "#3b82f6"), onChange: (e) => updateLocal('indicators.cazastop.colorPoc', e.target.value), className: "w-full h-6 bg-transparent border-0 rounded cursor-pointer" })
                    )
                  ),
                  React.createElement(ControlRow, { label: "Line Width" },
                    React.createElement("input", { type: "range", min: "1", max: "5", step: "1", value: localSettings.indicators.cazastop.lineWidth ?? 3, onChange: (e) => updateLocal('indicators.cazastop.lineWidth', parseInt(e.target.value)), className: "w-20 accent-accent" }),
                    React.createElement("span", { className: "text-[9px] text-gray-500 w-4" }, localSettings.indicators.cazastop.lineWidth ?? 3)
                  ),
                  React.createElement(ControlRow, { label: "Line Style" },
                    React.createElement("select", { value: localSettings.indicators.cazastop.lineStyle ?? 0, onChange: (e) => updateLocal('indicators.cazastop.lineStyle', parseInt(e.target.value)), className: "text-[9px] bg-white/5 border border-white/10 rounded px-2 py-1 text-white outline-none" },
                      React.createElement("option", { value: 0 }, "Solid"),
                      React.createElement("option", { value: 1 }, "Dotted"),
                      React.createElement("option", { value: 2 }, "Dashed"),
                      React.createElement("option", { value: 3 }, "Large Dashed")
                    )
                  ),
                  React.createElement("div", { className: "pt-1 space-y-1" },
                    React.createElement("label", { className: "flex items-center gap-2 cursor-pointer p-1 hover:text-white transition-colors" },
                      React.createElement("input", { type: "checkbox", checked: localSettings.indicators.cazastop.showZones ?? true, onChange: (e) => updateLocal('indicators.cazastop.showZones', e.target.checked), className: "w-3.5 h-3.5 accent-accent" }),
                      React.createElement("span", { className: "text-[9px] text-gray-400 uppercase" }, "Show Zones")
                    ),
                    React.createElement("label", { className: "flex items-center gap-2 cursor-pointer p-1 hover:text-white transition-colors" },
                      React.createElement("input", { type: "checkbox", checked: localSettings.indicators.cazastop.pocOnly ?? false, onChange: (e) => updateLocal('indicators.cazastop.pocOnly', e.target.checked), className: "w-3.5 h-3.5 accent-accent" }),
                      React.createElement("span", { className: "text-[9px] text-gray-400 uppercase" }, "POC Only Mode")
                    )
                  )
                )
              )
            )
          ),
          activeTab === "layout" &&
          React.createElement("div", { className: "space-y-4 animate-in fade-in slide-in-from-left-2 duration-300" },
            React.createElement("div", { className: "p-4 bg-white/[0.02] border border-white/5 rounded-xl" },
              React.createElement("h4", { className: "text-[10px] font-black text-accent uppercase tracking-[0.2em] mb-4" }, "Panels Visibility"),
              React.createElement("div", { className: "space-y-3" },
                React.createElement("div", { className: "flex items-center justify-between p-2 bg-white/5 rounded-lg border border-white/5" },
                  React.createElement("span", { className: "text-[10px] text-gray-300 uppercase font-bold" }, "Order Entry"),
                  React.createElement("div", { className: "flex items-center gap-4" },
                    React.createElement("div", { className: "flex items-center gap-1 bg-black/40 p-0.5 rounded border border-white/10" },
                      ["LEFT", "RIGHT"].map(s => 
                        React.createElement("button", {
                          key: s,
                          onClick: () => updateLocal('layout.orderEntrySide', s.toLowerCase()),
                          className: `px-2 py-0.5 rounded text-[8px] font-black transition-all ${ (localSettings.layout.orderEntrySide || 'right') === s.toLowerCase() ? "bg-accent text-black" : "text-gray-500 hover:text-white"}`
                        }, s)
                      )
                    ),
                    React.createElement("div", { className: "flex items-center gap-2" },
                      React.createElement("span", { className: "text-[9px] text-gray-500" }, "WIDTH"),
                      React.createElement("input", { type: "number", step: "10", value: localSettings.layout.orderEntryWidth || 320, onChange: (e) => updateLocal('layout.orderEntryWidth', parseInt(e.target.value)), className: "w-16 bg-black/40 border border-white/10 rounded px-2 py-1 text-[10px] text-white" })
                    ),
                    React.createElement("input", { type: "checkbox", checked: localSettings.layout.showOrderEntry, onChange: (e) => updateLocal('layout.showOrderEntry', e.target.checked), className: "w-4 h-4 accent-accent" })
                  )
                ),
                React.createElement("div", { className: "flex items-center justify-between p-2 bg-white/5 rounded-lg border border-white/5" },
                  React.createElement("span", { className: "text-[10px] text-gray-300 uppercase font-bold" }, "Market Tape"),
                  React.createElement("div", { className: "flex items-center gap-4" },
                    React.createElement("div", { className: "flex items-center gap-1 bg-black/40 p-0.5 rounded border border-white/10" },
                      ["LEFT", "RIGHT"].map(s => 
                        React.createElement("button", {
                          key: s,
                          onClick: () => updateLocal('layout.tapeSide', s.toLowerCase()),
                          className: `px-2 py-0.5 rounded text-[8px] font-black transition-all ${ (localSettings.layout.tapeSide || 'left') === s.toLowerCase() ? "bg-accent text-black" : "text-gray-500 hover:text-white"}`
                        }, s)
                      )
                    ),
                    React.createElement("div", { className: "flex items-center gap-2" },
                      React.createElement("span", { className: "text-[9px] text-gray-500" }, "WIDTH"),
                      React.createElement("input", { type: "number", step: "10", value: localSettings.layout.tapeWidth || 220, onChange: (e) => updateLocal('layout.tapeWidth', parseInt(e.target.value)), className: "w-16 bg-black/40 border border-white/10 rounded px-2 py-1 text-[10px] text-white" })
                    ),
                    React.createElement("input", { type: "checkbox", checked: localSettings.layout.showTape, onChange: (e) => updateLocal('layout.showTape', e.target.checked), className: "w-4 h-4 accent-accent" })
                  )
                ),
                React.createElement("div", { className: "flex items-center justify-between p-2 bg-white/5 rounded-lg border border-white/5" },
                  React.createElement("span", { className: "text-[10px] text-gray-300 uppercase font-bold" }, "Depth of Market"),
                  React.createElement("div", { className: "flex items-center gap-4" },
                    React.createElement("div", { className: "flex items-center gap-1 bg-black/40 p-0.5 rounded border border-white/10" },
                      ["LEFT", "RIGHT"].map(s => 
                        React.createElement("button", {
                          key: s,
                          onClick: () => updateLocal('layout.domSide', s.toLowerCase()),
                          className: `px-2 py-0.5 rounded text-[8px] font-black transition-all ${ (localSettings.layout.domSide || 'left') === s.toLowerCase() ? "bg-accent text-black" : "text-gray-500 hover:text-white"}`
                        }, s)
                      )
                    ),
                    React.createElement("div", { className: "flex items-center gap-2" },
                      React.createElement("span", { className: "text-[9px] text-gray-500" }, "WIDTH"),
                      React.createElement("input", { type: "number", step: "10", value: localSettings.layout.domWidth || 250, onChange: (e) => updateLocal('layout.domWidth', parseInt(e.target.value)), className: "w-16 bg-black/40 border border-white/10 rounded px-2 py-1 text-[10px] text-white" })
                    ),
                    React.createElement("input", { type: "checkbox", checked: localSettings.layout.showDom, onChange: (e) => updateLocal('layout.showDom', e.target.checked), className: "w-4 h-4 accent-accent" })
                  )
                ),
                React.createElement("div", { className: "flex items-center justify-between p-2 bg-white/5 rounded-lg border border-white/5" },
                  React.createElement("span", { className: "text-[10px] text-gray-300 uppercase font-bold" }, "Volume Pane"),
                  React.createElement("div", { className: "flex items-center gap-4" },
                    React.createElement("div", { className: "flex items-center gap-2" },
                      React.createElement("span", { className: "text-[9px] text-gray-500" }, "HEIGHT %"),
                      React.createElement("input", { type: "number", step: "1", min: "5", max: "50", value: localSettings.layout.volumeHeight || 15, onChange: (e) => updateLocal('layout.volumeHeight', parseInt(e.target.value)), className: "w-16 bg-black/40 border border-white/10 rounded px-2 py-1 text-[10px] text-white" })
                    ),
                    React.createElement("input", { type: "checkbox", checked: localSettings.overlays.showVolume, onChange: (e) => updateLocal('overlays.showVolume', e.target.checked), className: "w-4 h-4 accent-accent" })
                  )
                ),
                React.createElement("div", { className: "flex items-center justify-between p-2 bg-white/5 rounded-lg border border-white/5" },
                  React.createElement("span", { className: "text-[10px] text-gray-300 uppercase font-bold" }, "Delta Pane"),
                  React.createElement("div", { className: "flex items-center gap-4" },
                    React.createElement("div", { className: "flex items-center gap-2" },
                      React.createElement("span", { className: "text-[9px] text-gray-500" }, "HEIGHT %"),
                      React.createElement("input", { type: "number", step: "1", min: "5", max: "50", value: localSettings.layout.deltaHeight || 15, onChange: (e) => updateLocal('layout.deltaHeight', parseInt(e.target.value)), className: "w-16 bg-black/40 border border-white/10 rounded px-2 py-1 text-[10px] text-white" })
                    ),
                    React.createElement("input", { type: "checkbox", checked: localSettings.overlays.showDelta, onChange: (e) => updateLocal('overlays.showDelta', e.target.checked), className: "w-4 h-4 accent-accent" })
                  )
                )
              )
            ),
            React.createElement(CollapsibleSection, { title: "Overlays Visibility", icon: "eye", enabled: true },
              React.createElement("div", { className: "space-y-2" },
                React.createElement("div", { className: "flex items-center justify-between p-2 bg-white/5 rounded-lg border border-white/5" },
                  React.createElement("span", { className: "text-[10px] text-gray-300 uppercase font-bold" }, "Big Trades Overlay"),
                  React.createElement("input", { type: "checkbox", checked: localSettings.indicators.bigTrades.enabled, onChange: (e) => updateLocal('indicators.bigTrades.enabled', e.target.checked), className: "w-4 h-4 accent-accent" })
                ),
                React.createElement("div", { className: "flex items-center justify-between p-2 bg-white/5 rounded-lg border border-white/5" },
                  React.createElement("span", { className: "text-[10px] text-gray-300 uppercase font-bold" }, "Show Positions"),
                  React.createElement("input", { type: "checkbox", checked: localSettings.overlays.showPositions, onChange: (e) => updateLocal('overlays.showPositions', e.target.checked), className: "w-4 h-4 accent-accent" })
                ),
                React.createElement("div", { className: "flex items-center justify-between p-2 bg-white/5 rounded-lg border border-white/5" },
                  React.createElement("span", { className: "text-[10px] text-gray-300 uppercase font-bold" }, "Show Drawings"),
                  React.createElement("input", { type: "checkbox", checked: localSettings.overlays.showDrawings, onChange: (e) => updateLocal('overlays.showDrawings', e.target.checked), className: "w-4 h-4 accent-accent" })
                ),
                React.createElement("div", { className: "flex items-center justify-between p-2 bg-white/5 rounded-lg border border-white/5" },
                  React.createElement("span", { className: "text-[10px] text-gray-300 uppercase font-bold" }, "DOM Histogram"),
                  React.createElement("input", { type: "checkbox", checked: localSettings.overlays.showDomHistogram, onChange: (e) => updateLocal('overlays.showDomHistogram', e.target.checked), className: "w-4 h-4 accent-accent" })
                )
              )
            ),
            React.createElement(CollapsibleSection, { title: "Global Notifications", icon: "bell-slash", enabled: true },
              React.createElement("div", { className: "space-y-2" },
                React.createElement("div", { className: "flex items-center justify-between p-2 bg-white/5 rounded-lg border border-white/5" },
                  React.createElement("div", { className: "flex flex-col" },
                    React.createElement("span", { className: "text-[10px] text-gray-300 uppercase font-bold" }, "Mute Save Alerts"),
                    React.createElement("span", { className: "text-[8px] text-gray-500 italic" }, "Hide \"Workspace Saved\" messages")
                  ),
                  React.createElement("input", {
                    type: "checkbox",
                    checked: localStorage.getItem('muteSaveNotifications') === 'true',
                    onChange: (e) => {
                      localStorage.setItem('muteSaveNotifications', e.target.checked);
                      updateLocal('layout.muteSaveNotifications', e.target.checked);
                    },
                    className: "w-4 h-4 accent-accent"
                  }
                  )
                ),
                React.createElement("div", { className: "flex items-center justify-between p-2 bg-white/5 rounded-lg border border-white/5" },
                  React.createElement("div", { className: "flex flex-col" },
                    React.createElement("span", { className: "text-[10px] text-gray-300 uppercase font-bold" }, "Mute Trading Alerts"),
                    React.createElement("span", { className: "text-[8px] text-gray-500 italic" }, "Hide order execution messages")
                  ),
                  React.createElement("input", {
                    type: "checkbox",
                    checked: localStorage.getItem('muteTradingNotifications') === 'true',
                    onChange: (e) => {
                      localStorage.setItem('muteTradingNotifications', e.target.checked);
                      updateLocal('layout.muteTradingNotifications', e.target.checked);
                    },
                    className: "w-4 h-4 accent-accent"
                  }
                  )
                )
              )
            ),
            React.createElement(CollapsibleSection, { title: "DOM Settings", icon: "layer-group", enabled: true },
              React.createElement("div", { className: "space-y-3" },
                React.createElement(ControlRow, { label: "Levels" },
                  React.createElement("input", { type: "number", value: localSettings.dom.levels, onChange: (e) => updateLocal('dom.levels', parseInt(e.target.value)), className: "w-20 bg-black/40 border border-white/10 rounded px-1 py-1 text-xs text-white" })
                ),
                React.createElement(ControlRow, { label: "Width (px)", info: "Compact DOM towards price axis" },
                  React.createElement("div", { className: "flex items-center gap-2" },
                    React.createElement("input", { type: "range", min: "100", max: "800", step: "10", value: localSettings.dom.maxWidth || 400, onChange: (e) => updateLocal('dom.maxWidth', parseInt(e.target.value)), className: "w-20 accent-accent" }),
                    React.createElement("span", { className: "text-[9px] text-gray-500 w-6" }, localSettings.dom.maxWidth || 400)
                  )
                ),
                React.createElement(ControlRow, { label: "Bar Thickness" },
                  React.createElement("div", { className: "flex items-center gap-2" },
                    React.createElement("input", { type: "range", min: "0.1", max: "1.0", step: "0.05", value: localSettings.dom.barThickness || 0.92, onChange: (e) => updateLocal('dom.barThickness', parseFloat(e.target.value)), className: "w-20 accent-accent" }),
                    React.createElement("span", { className: "text-[9px] text-gray-500 w-6" }, (localSettings.dom.barThickness || 0.92).toFixed(2))
                  )
                ),
                React.createElement(ControlRow, { label: "Show Labels" },
                  React.createElement("input", { type: "checkbox", checked: localSettings.dom.showLabels !== false, onChange: (e) => updateLocal('dom.showLabels', e.target.checked), className: "w-4 h-4 accent-accent" })
                ),
                React.createElement(ControlRow, { label: "Render Style" },
                  React.createElement("select", { value: localSettings.dom.renderStyle, onChange: (e) => updateLocal('dom.renderStyle', e.target.value), className: "text-[10px] bg-white/5 border border-white/10 rounded px-2 py-1 text-white outline-none" },
                    React.createElement("option", { value: "heatmap" }, "Heatmap"),
                    React.createElement("option", { value: "bars" }, "Bars")
                  )
                ),
                React.createElement(ControlRow, { label: "Opacity" },
                  React.createElement("input", { type: "range", min: "0", max: "1", step: "0.1", value: localSettings.dom.opacity, onChange: (e) => updateLocal('dom.opacity', parseFloat(e.target.value)), className: "w-20 accent-accent" })
                ),
                React.createElement("div", { className: "grid grid-cols-2 gap-4" },
                  React.createElement("div", { className: "space-y-1" },
                    React.createElement("label", { className: "text-[9px] text-gray-500 uppercase" }, "Bid Color"),
                    React.createElement("input", { type: "color", value: ensureHex(localSettings.dom.bidColor, "#10b981"), onChange: (e) => updateLocal('dom.bidColor', e.target.value), className: "w-full h-6 rounded bg-transparent border-0" })
                  ),
                  React.createElement("div", { className: "space-y-1" },
                    React.createElement("label", { className: "text-[9px] text-gray-500 uppercase" }, "Ask Color"),
                    React.createElement("input", { type: "color", value: ensureHex(localSettings.dom.askColor, "#ef5350"), onChange: (e) => updateLocal('dom.askColor', e.target.value), className: "w-full h-6 rounded bg-transparent border-0" })
                  )
                )
              )
            ),
            React.createElement(CollapsibleSection, { title: "Bookmap (Heatmap)", icon: "fire", enabled: true },
              React.createElement("div", { className: "space-y-3" },
                React.createElement(ControlRow, { label: "Enable Heatmap", info: "Draw historical DOM map behind price" },
                  React.createElement("input", { type: "checkbox", checked: localSettings.overlays.showBookmap, onChange: (e) => updateLocal('overlays.showBookmap', e.target.checked), className: "w-4 h-4 accent-accent" })
                ),
                React.createElement(ControlRow, { label: "Update Rate (ms)", info: "Lower is smoother but uses more CPU" },
                  React.createElement("input", { type: "number", step: "50", min: "100", max: "2000", value: localSettings.bookmap.updateInterval || 500, onChange: (e) => updateLocal('bookmap.updateInterval', parseInt(e.target.value)), className: "w-20 bg-black/40 border border-white/10 rounded px-1 py-1 text-xs text-white" })
                ),
                React.createElement(ControlRow, { label: "History Limit", info: "How many snapshots to remember" },
                  React.createElement("input", { type: "number", step: "100", min: "100", max: "5000", value: localSettings.bookmap.historySize || 500, onChange: (e) => updateLocal('bookmap.historySize', parseInt(e.target.value)), className: "w-20 bg-black/40 border border-white/10 rounded px-1 py-1 text-xs text-white" })
                ),
                React.createElement(ControlRow, { label: "Min Volume Cutoff", info: "Ignore tiny limit orders to reduce noise" },
                  React.createElement("input", { type: "number", step: "1", min: "0", value: localSettings.bookmap.minVolumeFilter || 0, onChange: (e) => updateLocal('bookmap.minVolumeFilter', parseInt(e.target.value)), className: "w-20 bg-black/40 border border-white/10 rounded px-1 py-1 text-xs text-white" })
                ),
                React.createElement(ControlRow, { label: "Intensity Contrast", info: "Amplify visual signature of orders" },
                  React.createElement("div", { className: "flex items-center gap-2" },
                    React.createElement("input", { type: "range", min: "0.1", max: "3.0", step: "0.1", value: localSettings.bookmap.maxIntensityFactor || 1.0, onChange: (e) => updateLocal('bookmap.maxIntensityFactor', parseFloat(e.target.value)), className: "w-20 accent-accent" }),
                    React.createElement("span", { className: "text-[9px] text-gray-500 w-6" }, (localSettings.bookmap.maxIntensityFactor || 1.0).toFixed(1))
                  )
                ),
                React.createElement(ControlRow, { label: "Color Theme" },
                  React.createElement("select", { value: localSettings.bookmap.colorTheme || 'llama', onChange: (e) => updateLocal('bookmap.colorTheme', e.target.value), className: "text-[10px] bg-white/5 border border-white/10 rounded px-2 py-1 text-white outline-none" },
                    React.createElement("option", { value: "classic" }, "Bookmap Classic"),
                    React.createElement("option", { value: "llama" }, "LLama Bookmap (Hot/Cold)"),
                    React.createElement("option", { value: "grayscale" }, "Monochrome X-Ray")
                  )
                ),
                React.createElement(ControlRow, { label: "Opacity" },
                  React.createElement("input", { type: "range", min: "0", max: "1", step: "0.1", value: localSettings.bookmap.opacity !== undefined ? localSettings.bookmap.opacity : 1.0, onChange: (e) => updateLocal('bookmap.opacity', parseFloat(e.target.value)), className: "w-20 accent-accent" })
                )
              )
            )
          ),
          activeTab === "filters" &&
          React.createElement("div", { className: "space-y-4 animate-in fade-in slide-in-from-left-2 duration-300" },
            React.createElement("div", { className: "p-4 bg-white/[0.02] border border-white/5 rounded-xl" },
              React.createElement("h4", { className: "text-[10px] font-black text-accent uppercase tracking-[0.2em] mb-4" }, "Market Filters"),
              React.createElement("div", { className: "space-y-3" },
                React.createElement(ControlRow, { label: "Global Min Vol", info: "Minimum volume for standard candles" },
                  React.createElement("input", { type: "number", value: localSettings.filters.minVol, onChange: (e) => updateLocal('filters.minVol', parseInt(e.target.value)), className: "w-20 bg-black/40 border border-white/10 rounded px-2 py-1 text-xs text-white" })
                ),
                React.createElement("div", { className: "grid grid-cols-2 gap-4 pt-2" },
                  React.createElement("div", { className: "space-y-1" },
                    React.createElement("label", { className: "text-[9px] text-gray-500 uppercase" }, "Volume Color"),
                    React.createElement("input", { type: "color", value: ensureHex(localSettings.filters.volumeColor, "#10b981"), onChange: (e) => updateLocal('filters.volumeColor', e.target.value), className: "w-full h-6 rounded bg-transparent border-0" })
                  ),
                  React.createElement("div", { className: "space-y-1" },
                    React.createElement("label", { className: "text-[9px] text-gray-500 uppercase" }, "Delta Color"),
                    React.createElement("input", { type: "color", value: ensureHex(localSettings.filters.deltaColor, "#3b82f6"), onChange: (e) => updateLocal('filters.deltaColor', e.target.value), className: "w-full h-6 rounded bg-transparent border-0" })
                  )
                )
              )
            ),
            React.createElement("div", { className: "p-4 bg-black/40 border border-white/5 rounded-xl" },
              React.createElement("h4", { className: "text-[10px] font-black text-white/50 uppercase tracking-widest mb-2" }, "Overlays"),
              React.createElement("div", { className: "grid grid-cols-2 gap-3" },
                React.createElement("label", { className: "flex items-center gap-2 cursor-pointer p-2 bg-white/5 rounded hover:bg-white/10 transition-colors border border-white/5" },
                  React.createElement("input", { type: "checkbox", checked: localSettings.overlays.showDrawings, onChange: (e) => updateLocal('overlays.showDrawings', e.target.checked), className: "w-3 h-3 accent-accent" }),
                  React.createElement("span", { className: "text-[9px] text-gray-300 uppercase" }, "Drawings")
                ),
                React.createElement("label", { className: "flex items-center gap-2 cursor-pointer p-2 bg-white/5 rounded hover:bg-white/10 transition-colors border border-white/5" },
                  React.createElement("input", { type: "checkbox", checked: localSettings.overlays.showPositions, onChange: (e) => updateLocal('overlays.showPositions', e.target.checked), className: "w-3 h-3 accent-accent" }),
                  React.createElement("span", { className: "text-[9px] text-gray-300 uppercase" }, "Positions")
                ),
                React.createElement("label", { className: "flex items-center gap-2 cursor-pointer p-2 bg-white/5 rounded hover:bg-white/10 transition-colors border border-white/5" },
                  React.createElement("input", { type: "checkbox", checked: localSettings.overlays.showBigTrades, onChange: (e) => updateLocal('overlays.showBigTrades', e.target.checked), className: "w-3 h-3 accent-accent" }),
                  React.createElement("span", { className: "text-[9px] text-gray-300 uppercase" }, "Big Trades")
                ),
                React.createElement("label", { className: "flex items-center gap-2 cursor-pointer p-2 bg-white/5 rounded hover:bg-white/10 transition-colors border border-white/5" },
                  React.createElement("input", { type: "checkbox", checked: localSettings.overlays.showOrderFlow, onChange: (e) => updateLocal('overlays.showOrderFlow', e.target.checked), className: "w-3 h-3 accent-accent" }),
                  React.createElement("span", { className: "text-[9px] text-gray-300 uppercase" }, "Order Flow")
                ),
                React.createElement("label", { className: "flex items-center gap-2 cursor-pointer p-2 bg-white/5 rounded hover:bg-white/10 transition-colors border border-white/5" },
                  React.createElement("input", { type: "checkbox", checked: localSettings.overlays.showDomHistogram, onChange: (e) => updateLocal('overlays.showDomHistogram', e.target.checked), className: "w-3 h-3 accent-accent" }),
                  React.createElement("span", { className: "text-[9px] text-gray-300 uppercase" }, "DOM Hist")
                ),
                React.createElement("label", { className: "flex items-center gap-2 cursor-pointer p-2 bg-white/5 rounded hover:bg-white/10 transition-colors border border-white/5" },
                  React.createElement("input", { type: "checkbox", checked: localSettings.overlays.showBookmap, onChange: (e) => updateLocal('overlays.showBookmap', e.target.checked), className: "w-3 h-3 accent-accent" }),
                  React.createElement("span", { className: "text-[9px] text-gray-300 uppercase" }, "Bookmap")
                )
              )
            )
          ),
          activeTab === "timer" &&
          React.createElement("div", { className: "space-y-4 animate-in fade-in slide-in-from-left-2 duration-300" },
            React.createElement("div", { className: "p-4 bg-white/[0.02] border border-white/5 rounded-xl" },
              React.createElement("h4", { className: "text-[10px] font-black text-accent uppercase tracking-[0.2em] mb-4" }, "Candle Timer"),
              React.createElement("div", { className: "space-y-3" },
                React.createElement(ControlRow, { label: "Enable Timer", info: "Countdown to next candle close" },
                  React.createElement("input", { type: "checkbox", checked: localSettings.timer?.enabled ?? true, onChange: (e) => updateLocal('timer.enabled', e.target.checked), className: "w-4 h-4 accent-accent cursor-pointer" })
                ),
                localSettings.timer?.enabled !== false &&
                React.createElement(React.Fragment, null,
                  React.createElement(ControlRow, { label: "Position", info: "Where to show on chart" },
                    React.createElement("select", { value: localSettings.timer?.position || 'bottom', onChange: (e) => updateLocal('timer.position', e.target.value), className: "bg-black/40 border border-white/10 rounded px-2 py-1 text-[10px] text-white focus:border-accent/50 outline-none" },
                      React.createElement("option", { value: "top" }, "Top"),
                      React.createElement("option", { value: "bottom" }, "Bottom")
                    )
                  ),
                  React.createElement("div", { className: "flex items-center justify-between" },
                    React.createElement("div", null,
                      React.createElement("span", { className: "text-[9px] text-gray-400 uppercase font-bold" }, "Size")
                    ),
                    React.createElement("div", { className: "flex gap-1" },
                      ["small", "medium", "large"].map((s) =>
                        React.createElement("button", {
                          key: s,
                          onClick: () => updateLocal('timer.size', s),
                          className: `px-3 py-1 rounded text-[9px] font-bold uppercase transition-all border ${(localSettings.timer?.size || 'medium') === s ?
                            "bg-accent/20 text-accent border-accent/30" :
                            "bg-black/40 text-gray-500 border-white/5 hover:text-white hover:border-white/10"}`
                        },
                          s[0].toUpperCase()
                        )
                      )
                    )
                  ),
                  React.createElement("div", { className: "grid grid-cols-2 gap-3 pt-1" },
                    React.createElement("div", { className: "space-y-1" },
                      React.createElement("label", { className: "text-[9px] text-gray-500 uppercase font-bold" }, "Color"),
                      React.createElement("input", { type: "color", value: ensureHex(localSettings.timer?.color, "#fbbf24"), onChange: (e) => updateLocal('timer.color', e.target.value), className: "w-full h-6 rounded bg-transparent border-0 cursor-pointer" })
                    ),
                    React.createElement("div", { className: "space-y-1" },
                      React.createElement("label", { className: "text-[9px] text-gray-500 uppercase font-bold" }, "Progress Bar"),
                      React.createElement("label", { className: "flex items-center gap-2 cursor-pointer p-1.5 bg-white/5 rounded hover:bg-white/10 transition-colors border border-white/5" },
                        React.createElement("input", { type: "checkbox", checked: localSettings.timer?.showProgress ?? true, onChange: (e) => updateLocal('timer.showProgress', e.target.checked), className: "w-3 h-3 accent-accent" }),
                        React.createElement("span", { className: "text-[9px] text-gray-300" }, localSettings.timer?.showProgress !== false ? "On" : "Off")
                      )
                    )
                  )
                )
              )
            ),
            React.createElement("style", null, `
              .no-scrollbar::-webkit-scrollbar { display: none !important; }
              .no-scrollbar { -ms-overflow-style: none !important; scrollbar-width: none !important; }
            `)
          ),
          React.createElement("div", { className: "px-6 py-4 bg-white/5 border-t border-white/5 flex items-center justify-between" },
            React.createElement("button", {
              type: "button",
              onClick: handleReset,
              className: "text-[10px] font-black text-gray-500 hover:text-gray-300 uppercase tracking-widest transition-colors flex items-center gap-2"
            },
              React.createElement("i", { className: "fas fa-undo-alt text-[9px]" }), "Reset"
            ),
            React.createElement("div", { className: "flex gap-3" },
              React.createElement("button", {
                type: "button",
                onClick: onClose,
                className: "px-4 py-2 text-[10px] font-black text-gray-400 hover:text-white uppercase tracking-widest transition-colors"
              },
                "Cancel"
              ),
              React.createElement("button", {
                type: "button",
                onClick: handleApply,
                className: "px-8 py-2 bg-accent hover:bg-accent/80 text-[#111] text-[10px] font-black uppercase tracking-[0.2em] rounded-lg shadow-[0_5px_15px_rgba(var(--accent-rgb),0.3)] transition-all hover:-translate-y-0.5"
              },
                "Apply"
              )
            )
          )
        )
      )
    ));
};
function getDefaultChartSettings() {
  return {
    indicators: {
      cazastop: {
        enabled: false,
        params: {
          sensitivity: 5,
          swing_bars: 5,
          lookback: 10,
          dist_ticks: 60,
          buffer_ticks: 10,
          vida_max: 30,
          lookback_tp: 100,
          ticks_tp: 6,
          mostrar_tp: true,
          analisis_vol: true,
          dibujar_safe: true
        },
        colorTop: "#ef4444",
        colorBottom: "#ef4444",
        colorPoc: "#3b82f6",
        lineWidth: 3,
        lineStyle: 0,
        showZones: true,
        pocOnly: false
      },
      orderflow: {
        enabled: false,
        showVwap: true,
        showVwapBands: false,
        showCumDelta: true,
        vwapColor: "#fbbf24",
        vwapWidth: 2,
        band1Color: "rgba(251, 191, 36, 0.4)",
        band2Color: "rgba(251, 191, 36, 0.2)",
        bandWidth: 1,
        cumDeltaColor: "#3b82f6",
        cumDeltaWidth: 2,
        limit: 5000
      },
      imbalance: {
        enabled: false,
        params: {
          delta_threshold: 0.15,
          volume_multiplier: 0.5,
          min_body_ratio: 0.20,
          min_bars_between: 3,
          structure_lookback: 3,
          atr_multiplier: 0.6,
          use_structure: true,
          use_volume_filter: true
        },
        buyColor: "#22c55e",
        sellColor: "#ef4444",
        signalSize: 1
      },
      volumeProfile: {
        enabled: false,
        params: {
          rangeMode: "session",
          sessionType: "24h",
          hourlyBlock: 60,
          profileMode: "volume",
          bucketCount: 100,
          vaPercent: 70,
          histogramWidth: 30,
          histogramSide: "left",
          colorUp: "rgba(38, 166, 154, 0.7)",
          colorDown: "rgba(239, 83, 80, 0.7)",
          colorBid: "rgba(239, 83, 80, 0.7)",
          colorAsk: "rgba(38, 166, 154, 0.7)",
          colorDeltaPos: "rgba(38, 166, 154, 0.7)",
          colorDeltaNeg: "rgba(239, 83, 80, 0.7)",
          colorPoc: "#ffeb3b",
          colorVah: "rgba(255, 255, 255, 0.3)",
          colorVal: "rgba(255, 255, 255, 0.3)",
          colorVaFill: "rgba(255, 255, 255, 0)",
          pocLineWidth: 2,
          vaLineWidth: 1,
          vaLineStyle: 2,
          showPoc: true,
          showVa: true,
          showLabels: true,
          showHistogram: true,
          noiseThreshold: 0
        }
      },
      bigTrades: {
        enabled: false,
        mode: "both",
        displayLimit: 100,
        real: {
          enabled: true,
          threshold: 100,
          buyColor: "#10b981",
          sellColor: "#ef4444",
          bubbleScale: 1.0,
          textSize: 1.2,
          opacity: 0.4,
          showValue: true
        },
        cumulative: {
          enabled: true,
          threshold: 500,
          window: 1000,
          buyColor: "#3b82f6",
          sellColor: "#f59e0b",
          bubbleScale: 1.2,
          textSize: 1.2,
          opacity: 0.6,
          showValue: true
        }
      },
      tpo: {
        sessionPeriod: "1d",
        blockPeriod: 30,
        rowSize: 0,
        colorVA: "rgba(59, 130, 246, 0.5)",
        colorTPO: "rgba(107, 114, 128, 0.3)",
        colorPOC: "#ef4444",
        colorIB: "rgba(234, 179, 8, 0.8)",
        showIB: true,
        showPOC: true,
        showSinglePrints: true
      }
    },
    overlays: {
      showVolume: false,
      showDelta: false,
      showBigTrades: false,
      showPositions: true,
      showDrawings: true,
      showOrderFlow: false,
      showDomHistogram: false,
      showBookmap: false
    },
    bookmap: {
      updateInterval: 500,
      historySize: 500,
      minVolumeFilter: 0,
      maxIntensityFactor: 1.0,
      colorTheme: 'llama',
      opacity: 1.0
    },
    filters: {
      minVol: 100,
      volumeColor: "#10b981",
      deltaColor: "#3b82f6",
      volumeOpacity: 0.8,
      deltaOpacity: 0.8,
      deltaDisplayMode: "histogram",
      deltaPositiveColor: "#26a69a",
      deltaNegativeColor: "#ef5350",
      deltaCumPositiveColor: "#26a69a",
      deltaCumNegativeColor: "#ef5350",
      deltaCumLineColor: "#3b82f6",
      deltaCumLineWidth: 2
    },
    layout: {
      showOrderEntry: false,
      showTape: false,
      showDom: false,
      orderEntryWidth: 320,
      tapeWidth: 220,
      domWidth: 250,
      volumeHeight: 15,
      deltaHeight: 15,
      showGrid: (localStorage.getItem("chart_show_grid") ?? "true") === "true",
      showWatermark: (localStorage.getItem("chart_show_watermark") ?? "true") === "true",
      muteSaveNotifications: localStorage.getItem("muteSaveNotifications") === "true",
      muteTradingNotifications: localStorage.getItem("muteTradingNotifications") === "true"
    },
    appearance: {
      backgroundColor: localStorage.getItem("global_chart_bg_color") || "#050505",
      upColor: localStorage.getItem("global_candle_up_color") || "#26a69a",
      downColor: localStorage.getItem("global_candle_down_color") || "#ef5350",
      borderUpColor: localStorage.getItem("global_candle_border_color") || "#4b5563",
      borderDownColor: localStorage.getItem("global_candle_border_color") || "#4b5563",
      borderVisible: (localStorage.getItem("global_candle_border_visible") ?? "true") !== "false",
      priceLine: {
        enabled: true,
        color: "#ffffff",
        lineWidth: 1,
        lineStyle: 0,
        fullWidth: false
      }
    },
    bookmap: {
      levels: 1000,
      opacity: 1.0,
      updateInterval: 250,
      colorTheme: 'classic',
      minVolumeFilter: 0,
      maxIntensityFactor: 1.0,
      historySize: 600
    },
    dom: {
      levels: 1000,
      updateInterval: 100,
      scaleMode: 'linear',
      cumulative: false,
      compact: false,
      showVolumes: true,
      showLabels: true,
      maxWidth: 400,
      renderStyle: 'heatmap',
      opacity: 0.85,
      bidColor: '#10b981',
      askColor: '#ef5350'
    },
    timer: {
      enabled: true,
      position: 'bottom',
      size: 'medium',
      color: '#fbbf24',
      showProgress: true
    },
    footprint: {
      enabled: false,
      mode: "off",
      showWicks: true,
      wickThickness: 1,
      showPOC: true,
      pocColor: "#fbbf24",
      buyColor: "#10b981",
      sellColor: "#ef4444",
      fontSize: 10,
      syncWithChartColors: true,
      bodyBullColor: "#00dc6e",
      bodyBearColor: "#e6284b",
      bodyBullOpacity: 55,
      bodyBearOpacity: 55
    },
    stats: {
      enabled: true,
      type: 'percent',
      position: 'above-timer',
      fontSize: 14,
      opacity: 0.9,
      showLabel: true
    },
    chartType: localStorage.getItem("chart_type") || "candle"
  };
}
window.ChartSettingsModal = ChartSettingsModal;
window.getDefaultChartSettings = getDefaultChartSettings;