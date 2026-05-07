import React from 'react';
const ATMPanel = ({
  atmEnabled,
  setAtmEnabled,
  atmStrategy,
  setAtmStrategy,
  atmParams,
  setAtmParams,
  atmStatus,
  atmLog,
  getDefaultATMParams
}) => {
  const { useState } = React;
  return (
    React.createElement("div", { className: "flex-1 flex flex-col overflow-hidden" },
    React.createElement("div", { className: "px-3 py-2 border-b border-border/30" },
    React.createElement("div", { className: "flex items-center justify-between mb-2" },
    React.createElement("span", { className: "font-bold text-[11px] text-white" }, "Automated Trade Management"),
    React.createElement("label", { className: "relative inline-flex items-center cursor-pointer" },
    React.createElement("input", {
      type: "checkbox",
      className: "sr-only peer",
      checked: atmEnabled,
      onChange: (e) => setAtmEnabled(e.target.checked) }
    ),
    React.createElement("div", { className: "w-8 h-4 bg-gray-700 peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-gray-400 after:rounded-full after:h-3 after:w-3 after:transition-all peer-checked:bg-green-600 peer-checked:after:bg-white" })
    )
    ),
    React.createElement("div", { className: `text-[9px] px-2 py-1 rounded ${atmEnabled ? 'bg-green-500/20 text-green-400' : 'bg-gray-500/20 text-gray-400'}` }, "Status: ",
    atmStatus.toUpperCase()
    )
    ),
    React.createElement("div", { className: "px-3 py-2 border-b border-border/30" },
    React.createElement("label", { className: "block text-muted mb-1 text-[9px]" }, "Strategy"),
    React.createElement("div", { className: "grid grid-cols-3 gap-1" },
    ['conservative', 'aggressive', 'custom'].map((strat) =>
    React.createElement("button", {
      key: strat,
      onClick: () => {
        setAtmStrategy(strat);
        if (strat !== 'custom') {
          setAtmParams(getDefaultATMParams(strat));
        }
      },
      className: `py-1 rounded text-[9px] font-bold transition-colors ${atmStrategy === strat ?
      'bg-accent/20 text-accent' :
      'bg-[#222] text-muted hover:bg-[#333]'}` },
    strat.toUpperCase()
    )
    )
    )
    ),
    React.createElement("div", { className: "flex-1 overflow-y-auto px-3 py-2 border-b border-border/30" },
    React.createElement("h4", { className: "text-muted font-bold mb-2 text-[9px]" }, "PARAMETERS"),
    React.createElement("div", { className: "space-y-2" },
    React.createElement("div", { className: "grid grid-cols-2 gap-2" },
    React.createElement("div", { className: "bg-black/20 rounded p-1.5 border border-white/5" },
    React.createElement("label", { className: "text-muted text-[8px] block mb-1" }, "Entry Size"),
    React.createElement("input", {
      type: "number",
      value: atmParams.entrySize,
      onChange: (e) => setAtmParams({ ...atmParams, entrySize: parseFloat(e.target.value) || 0 }),
      step: 0.1,
      className: "w-full bg-transparent border-none text-white text-[10px] font-mono outline-none text-center" }
    )
    ),
    React.createElement("div", { className: "bg-black/20 rounded p-1.5 border border-white/5" },
    React.createElement("label", { className: "text-muted text-[8px] block mb-1" }, "Scale-In Levels"),
    React.createElement("input", {
      type: "number",
      value: atmParams.scaleInLevels,
      onChange: (e) => setAtmParams({ ...atmParams, scaleInLevels: parseFloat(e.target.value) || 0 }),
      step: 1,
      className: "w-full bg-transparent border-none text-white text-[10px] font-mono outline-none text-center" }
    )
    )
    ),
    React.createElement("div", { className: "grid grid-cols-2 gap-2" },
    React.createElement("div", { className: "bg-black/20 rounded p-1.5 border border-white/5" },
    React.createElement("label", { className: "text-muted text-[8px] block mb-1" }, "Scale-In Distance (pts)"),
    React.createElement("input", {
      type: "number",
      value: atmParams.scaleInDistance,
      onChange: (e) => setAtmParams({ ...atmParams, scaleInDistance: parseFloat(e.target.value) || 0 }),
      step: 5,
      className: "w-full bg-transparent border-none text-white text-[10px] font-mono outline-none text-center" }
    )
    ),
    React.createElement("div", { className: "bg-black/20 rounded p-1.5 border border-white/5" },
    React.createElement("label", { className: "text-muted text-[8px] block mb-1" }, "Scale-Out Levels"),
    React.createElement("input", {
      type: "number",
      value: atmParams.scaleOutLevels,
      onChange: (e) => setAtmParams({ ...atmParams, scaleOutLevels: parseFloat(e.target.value) || 0 }),
      step: 1,
      className: "w-full bg-transparent border-none text-white text-[10px] font-mono outline-none text-center" }
    )
    )
    ),
    React.createElement("div", { className: "grid grid-cols-3 gap-1" },
    React.createElement("div", { className: "bg-green-900/10 rounded p-1.5 border border-green-500/10" },
    React.createElement("label", { className: "text-muted text-[8px] block mb-1" }, "TP1 (pts)"),
    React.createElement("input", {
      type: "number",
      value: atmParams.profitTarget1,
      onChange: (e) => setAtmParams({ ...atmParams, profitTarget1: parseFloat(e.target.value) || 0 }),
      step: 5,
      className: "w-full bg-transparent border-none text-white text-[10px] font-mono outline-none text-center" }
    )
    ),
    React.createElement("div", { className: "bg-green-900/10 rounded p-1.5 border border-green-500/10" },
    React.createElement("label", { className: "text-muted text-[8px] block mb-1" }, "TP2 (pts)"),
    React.createElement("input", {
      type: "number",
      value: atmParams.profitTarget2,
      onChange: (e) => setAtmParams({ ...atmParams, profitTarget2: parseFloat(e.target.value) || 0 }),
      step: 5,
      className: "w-full bg-transparent border-none text-white text-[10px] font-mono outline-none text-center" }
    )
    ),
    React.createElement("div", { className: "bg-green-900/10 rounded p-1.5 border border-green-500/10" },
    React.createElement("label", { className: "text-muted text-[8px] block mb-1" }, "TP3 (pts)"),
    React.createElement("input", {
      type: "number",
      value: atmParams.profitTarget3,
      onChange: (e) => setAtmParams({ ...atmParams, profitTarget3: parseFloat(e.target.value) || 0 }),
      step: 5,
      className: "w-full bg-transparent border-none text-white text-[10px] font-mono outline-none text-center" }
    )
    )
    ),
    React.createElement("div", { className: "grid grid-cols-2 gap-2" },
    React.createElement("div", { className: "bg-blue-900/10 rounded p-1.5 border border-blue-500/10" },
    React.createElement("label", { className: "text-muted text-[8px] block mb-1" }, "Trailing Stop (pts)"),
    React.createElement("input", {
      type: "number",
      value: atmParams.trailingStop,
      onChange: (e) => setAtmParams({ ...atmParams, trailingStop: parseFloat(e.target.value) || 0 }),
      step: 5,
      className: "w-full bg-transparent border-none text-white text-[10px] font-mono outline-none text-center" }
    )
    ),
    React.createElement("div", { className: "bg-red-900/10 rounded p-1.5 border border-red-500/10" },
    React.createElement("label", { className: "text-muted text-[8px] block mb-1" }, "Max Drawdown ($)"),
    React.createElement("input", {
      type: "number",
      value: atmParams.maxDrawdown,
      onChange: (e) => setAtmParams({ ...atmParams, maxDrawdown: parseFloat(e.target.value) || 0 }),
      step: 10,
      className: "w-full bg-transparent border-none text-white text-[10px] font-mono outline-none text-center" }
    )
    )
    )
    )
    ),
    React.createElement("div", { className: "flex-1 overflow-y-auto px-3 py-2" },
    React.createElement("h4", { className: "text-muted font-bold mb-2 text-[9px]" }, "LOG"),
    atmLog.length === 0 ?
    React.createElement("p", { className: "text-gray-600 text-[8px] italic" }, "Waiting for ATM events...") :
    atmLog.map((log, idx) =>
    React.createElement("div", { key: idx, className: "text-[8px] text-gray-400 mb-1 font-mono" },
    log
    )
    )
    )
    ));
};
export default ATMPanel;