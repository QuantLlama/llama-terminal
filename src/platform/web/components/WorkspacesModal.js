const { useState, useEffect, useRef } = React;

const WorkspacesModal = ({ isOpen, onClose, onSave, onLoad, activeSymbol, workspaces: propWorkspaces }) => {
  const [workspaces, setWorkspaces] = useState({});
  const [newName, setNewName] = useState("");
  const [loading, setLoading] = useState(false);
  const [deleting, setDeleting] = useState(null);
  const { addNotification } = window.useNotification();
  const [pos, setPos] = useState({ x: 100, y: 100 });
  const [isDragging, setIsDragging] = useState(false);
  const dragRef = useRef(null);
  const offsetRef = useRef({ x: 0, y: 0 });

  const fetchWorkspaces = async () => {
    setLoading(true);
    try {
      console.log("[WorkspacesModal] Fetching workspaces...");
      const res = await fetch("/api/workspaces");
      if (res.ok) {
        const data = await res.json();
        console.log("[WorkspacesModal] Received data:", data);
        setWorkspaces(data || {});
      } else {
        console.error("[WorkspacesModal] Fetch failed with status:", res.status);
      }
    } catch (e) {
      console.error("[WorkspacesModal] Failed to fetch workspaces:", e);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (isOpen) {
      console.log("[WorkspacesModal] Modal opened. Prop workspaces:", propWorkspaces);
      if (propWorkspaces && Object.keys(propWorkspaces).length > 0) {
        setWorkspaces(propWorkspaces);
      } else {
        fetchWorkspaces();
      }
      setPos({ x: (window.innerWidth - 500) / 2, y: 150 });
      setNewName("");
    }
  }, [isOpen, propWorkspaces]);

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

  const handleSave = async () => {
    const name = newName.trim();
    if (!name) {
      addNotification("error", "Error", "Por favor ingrese un nombre para el espacio de trabajo");
      return;
    }
    
    setLoading(true);
    try {
      await onSave(name);
      setNewName("");
      await fetchWorkspaces();
      addNotification("success", "Éxito", `Espacio de trabajo '${name}' guardado correctamente`);
    } catch (e) {
      addNotification("error", "Error", "No se pudo guardar el espacio de trabajo");
    } finally {
      setLoading(false);
    }
  };

  const handleDelete = async (name) => {
    if (!confirm(`¿Está seguro de que desea eliminar el espacio de trabajo '${name}'?`)) return;
    
    setDeleting(name);
    try {
      const res = await fetch(`/api/workspace/${encodeURIComponent(name)}`, { method: "DELETE" });
      if (res.ok) {
        await fetchWorkspaces();
        addNotification("success", "Eliminado", `Espacio de trabajo '${name}' eliminado`);
      } else {
        addNotification("error", "Error", "No se pudo eliminar el espacio de trabajo");
      }
    } catch (e) {
      addNotification("error", "Error", "Error de conexión");
    } finally {
      setDeleting(null);
    }
  };

  if (!isOpen) return null;

  return (
    React.createElement("div", { className: "fixed inset-0 z-[10001] pointer-events-none font-sans" },
      React.createElement("div", {
        ref: dragRef,
        style: {
          position: "absolute",
          left: `${pos.x}px`,
          top: `${pos.y}px`,
          width: "500px",
          maxHeight: "70vh"
        },
        className: "bg-[#0a0a0a]/95 border border-white/10 rounded-xl shadow-[0_25px_60px_rgba(0,0,0,0.9)] overflow-hidden flex flex-col pointer-events-auto backdrop-blur-2xl animate-in fade-in zoom-in duration-300"
      },
        // Header
        React.createElement("div", {
          onMouseDown: handleMouseDown,
          className: "drag-handle flex items-center justify-between px-6 py-4 bg-white/5 border-b border-white/5 cursor-move select-none"
        },
          React.createElement("div", { className: "flex items-center gap-3" },
            React.createElement("div", { className: "w-8 h-8 rounded-lg bg-accent/20 flex items-center justify-center border border-accent/30" },
              React.createElement("i", { className: "fas fa-th-large text-accent text-sm" })
            ),
            React.createElement("div", null,
              React.createElement("h2", { className: "text-xs font-black text-white uppercase tracking-widest" }, "Workspaces"),
              React.createElement("p", { className: "text-[9px] text-zinc-500 font-bold uppercase tracking-tighter" }, "Cloud Persistence \u2022 Management")
            )
          ),
          React.createElement("button", {
            onClick: onClose,
            className: "w-8 h-8 flex items-center justify-center rounded-full hover:bg-white/10 text-zinc-500 hover:text-white transition-all"
          },
            React.createElement("i", { className: "fas fa-times" })
          )
        ),

        // Body
        React.createElement("div", { className: "p-6 space-y-6 overflow-y-auto" },
          // Save Section
          React.createElement("div", { className: "space-y-3" },
            React.createElement("label", { className: "text-[10px] font-black text-zinc-400 uppercase tracking-widest block" }, "Save Current Environment"),
            React.createElement("div", { className: "flex gap-2" },
              React.createElement("input", {
                type: "text",
                value: newName,
                onChange: (e) => setNewName(e.target.value),
                placeholder: "Nombre del espacio (ej: Crypto Scalping, Futures 4-Chart...)",
                className: "flex-1 bg-black/50 border border-white/10 rounded-lg px-4 py-2.5 text-xs text-white focus:border-accent outline-none transition-all placeholder:text-zinc-600 select-text",
                onKeyPress: (e) => e.key === 'Enter' && handleSave()
              }),
              React.createElement("button", {
                onClick: handleSave,
                disabled: loading || !newName.trim(),
                className: "bg-accent hover:bg-yellow-400 disabled:opacity-50 disabled:hover:bg-accent text-black text-[10px] font-black px-6 py-2 rounded-lg transition-all flex items-center gap-2 shadow-lg shadow-accent/10"
              },
                loading ? React.createElement("i", { className: "fas fa-circle-notch fa-spin" }) : React.createElement("i", { className: "fas fa-save" }),
                "SAVE"
              )
            )
          ),

          // List Section
          React.createElement("div", { className: "space-y-3 pt-4 border-t border-white/5" },
            React.createElement("div", { className: "flex items-center justify-between" },
              React.createElement("label", { className: "text-[10px] font-black text-zinc-400 uppercase tracking-widest block" }, "Saved Configurations"),
              loading && React.createElement("i", { className: "fas fa-circle-notch fa-spin text-accent text-[10px]" })
            ),
            React.createElement("div", { className: "grid gap-2" },
              Object.keys(workspaces).length === 0 ? 
                React.createElement("div", { className: "py-8 text-center bg-white/[0.02] rounded-xl border border-dashed border-white/10" },
                  React.createElement("i", { className: "fas fa-cloud-upload-alt text-zinc-700 text-2xl mb-2" }),
                  React.createElement("p", { className: "text-[10px] text-zinc-500 font-bold uppercase tracking-widest" }, "No Workspaces Found")
                ) :
                Object.entries(workspaces)
                  .sort((a, b) => {
                    const dateA = (a[1] && a[1].updated_at) ? new Date(a[1].updated_at).getTime() : 0;
                    const dateB = (b[1] && b[1].updated_at) ? new Date(b[1].updated_at).getTime() : 0;
                    return dateB - dateA;
                  })
                  .map(([name, ws]) => (
                    React.createElement("div", {
                      key: name,
                      className: "group bg-white/[0.02] hover:bg-white/[0.04] border border-white/5 hover:border-white/20 p-4 rounded-xl transition-all duration-300 flex items-center justify-between"
                    },
                      React.createElement("div", { className: "flex items-center gap-4" },
                        React.createElement("div", { className: "w-10 h-10 rounded-lg bg-black/60 flex items-center justify-center border border-white/10 group-hover:border-accent/30 transition-colors" },
                          React.createElement("i", { className: "fas fa-columns text-zinc-500 group-hover:text-accent transition-colors" })
                        ),
                        React.createElement("div", null,
                          React.createElement("h4", { className: "text-xs font-black text-white uppercase tracking-tight group-hover:text-accent transition-colors" }, name),
                          React.createElement("div", { className: "flex items-center gap-2 mt-0.5" },
                            React.createElement("span", { className: "text-[8px] text-zinc-500 font-bold uppercase" }, ws.layout || "single"),
                            React.createElement("span", { className: "w-1 h-1 rounded-full bg-zinc-800" }),
                            React.createElement("span", { className: "text-[8px] text-zinc-500 font-mono" }, ws.updated_at ? new Date(ws.updated_at).toLocaleString() : "N/A")
                          )
                        )
                      ),
                      React.createElement("div", { className: "flex items-center gap-2" },
                        React.createElement("button", {
                          onClick: () => {
                            onLoad(name, ws);
                            onClose();
                          },
                          className: "px-4 py-2 bg-white/5 hover:bg-white/10 text-white text-[9px] font-black uppercase rounded-lg border border-white/10 transition-all hover:scale-105"
                        }, "LOAD"),
                        React.createElement("button", {
                          onClick: () => handleDelete(name),
                          disabled: deleting === name,
                          className: "w-9 h-9 flex items-center justify-center bg-red-500/5 hover:bg-red-500/10 text-red-500/60 hover:text-red-500 rounded-lg border border-red-500/10 transition-all"
                        },
                          deleting === name ? React.createElement("i", { className: "fas fa-circle-notch fa-spin" }) : React.createElement("i", { className: "fas fa-trash-alt text-[10px]" })
                        )
                      )
                    )
                  ))
            )
          )
        ),

        // Footer
        React.createElement("div", { className: "px-6 py-4 bg-black/40 border-t border-white/5 flex items-center justify-between" },
          React.createElement("div", { className: "flex items-center gap-2" },
            React.createElement("i", { className: "fas fa-info-circle text-[10px] text-accent/50" }),
            React.createElement("span", { className: "text-[9px] text-zinc-500 font-bold uppercase tracking-tighter" }, "Settings persist per workspace")
          ),
          React.createElement("button", {
            onClick: onClose,
            className: "text-[9px] text-zinc-500 hover:text-white font-black uppercase tracking-widest transition-colors"
          }, "CLOSE")
        )
      )
    )
  );
};

window.WorkspacesModal = WorkspacesModal;
