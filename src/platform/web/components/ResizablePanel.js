const ResizablePanel = ({
  children,
  width,
  height,
  onResize,
  minWidth = 200,
  maxWidth = 600,
  minHeight = 100,
  maxHeight = 800,
  side = 'left',
  className = ''
}) => {
  const { useEffect, useRef } = React;
  const isResizing = useRef(false);
  const lastX = useRef(0);
  const lastY = useRef(0);
  const currentWidth = useRef(width || 0);
  const currentHeight = useRef(height || 0);
  const rafRef = useRef(null);
  useEffect(() => {currentWidth.current = width || 0;}, [width]);
  useEffect(() => {currentHeight.current = height || 0;}, [height]);
  useEffect(() => {
    const handleMouseMove = (e) => {
      if (!isResizing.current) return;
      if (rafRef.current) cancelAnimationFrame(rafRef.current);
      rafRef.current = requestAnimationFrame(() => {
        if (side === 'left') {
          const deltaX = lastX.current - e.clientX;
          const newWidth = currentWidth.current + deltaX;
          if (newWidth >= minWidth && newWidth <= maxWidth) {
            currentWidth.current = newWidth;
            onResize(newWidth);
          }
          lastX.current = e.clientX;
        } else if (side === 'right') {
          const deltaX = e.clientX - lastX.current;
          const newWidth = currentWidth.current + deltaX;
          if (newWidth >= minWidth && newWidth <= maxWidth) {
            currentWidth.current = newWidth;
            onResize(newWidth);
          }
          lastX.current = e.clientX;
        } else if (side === 'bottom') {
          const deltaY = e.clientY - lastY.current;
          const newHeight = currentHeight.current + deltaY;
          if (newHeight >= minHeight && newHeight <= maxHeight) {
            currentHeight.current = newHeight;
            onResize(newHeight);
          }
          lastY.current = e.clientY;
        }
      });
    };
    const handleMouseUp = () => {
      if (!isResizing.current) return;
      isResizing.current = false;
      document.body.style.cursor = '';
      document.body.style.userSelect = '';
      document.body.style.pointerEvents = '';
    };
    document.addEventListener('mousemove', handleMouseMove, { passive: true });
    document.addEventListener('mouseup', handleMouseUp);
    return () => {
      document.removeEventListener('mousemove', handleMouseMove);
      document.removeEventListener('mouseup', handleMouseUp);
      if (rafRef.current) cancelAnimationFrame(rafRef.current);
    };
  }, [onResize, minWidth, maxWidth, minHeight, maxHeight, side]);
  const handleMouseDown = (e) => {
    e.preventDefault();
    e.stopPropagation();
    isResizing.current = true;
    lastX.current = e.clientX;
    lastY.current = e.clientY;
    currentWidth.current = width || 0;
    currentHeight.current = height || 0;
    document.body.style.cursor = side === 'bottom' ? 'row-resize' : 'col-resize';
    document.body.style.userSelect = 'none';
    document.body.style.pointerEvents = 'none';
    e.currentTarget.style.pointerEvents = 'auto';
  };
  const style = {};
  if (width) style.width = `${width}px`;
  if (height) style.height = `${height}px`;
  return (
    React.createElement("div", { className: `relative flex flex-col shrink-0 ${className}`, style: style },
    side === 'left' &&
    React.createElement("div", {
      className: "absolute left-0 top-0 bottom-0 w-[12px] -translate-x-1/2 cursor-col-resize z-50 group overflow-visible",
      style: { pointerEvents: 'auto' },
      onMouseDown: handleMouseDown },
    React.createElement("div", { className: "absolute inset-y-0 left-1/2 -translate-x-1/2 w-[2px] bg-white/10 group-hover:w-[3px] group-hover:bg-accent/70 transition-all duration-150" }),
    React.createElement("div", { className: "absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 flex flex-col gap-1 opacity-0 group-hover:opacity-100 transition-opacity duration-150" },
    React.createElement("div", { className: "w-[3px] h-[3px] rounded-full bg-accent/80" }),
    React.createElement("div", { className: "w-[3px] h-[3px] rounded-full bg-accent/80" }),
    React.createElement("div", { className: "w-[3px] h-[3px] rounded-full bg-accent/80" })
    )
    ),
    React.createElement("div", { className: "flex-1 w-full h-full overflow-hidden flex flex-col" },
    children
    ),
    side === 'right' &&
    React.createElement("div", {
      className: "absolute right-0 top-0 bottom-0 w-[12px] translate-x-1/2 cursor-col-resize z-50 group overflow-visible",
      style: { pointerEvents: 'auto' },
      onMouseDown: handleMouseDown },
    React.createElement("div", { className: "absolute inset-y-0 left-1/2 -translate-x-1/2 w-[2px] bg-white/10 group-hover:w-[3px] group-hover:bg-accent/70 transition-all duration-150" }),
    React.createElement("div", { className: "absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 flex flex-col gap-1 opacity-0 group-hover:opacity-100 transition-opacity duration-150" },
    React.createElement("div", { className: "w-[3px] h-[3px] rounded-full bg-accent/80" }),
    React.createElement("div", { className: "w-[3px] h-[3px] rounded-full bg-accent/80" }),
    React.createElement("div", { className: "w-[3px] h-[3px] rounded-full bg-accent/80" })
    )
    ),
    side === 'bottom' &&
    React.createElement("div", {
      className: "absolute bottom-0 left-0 right-0 h-[12px] translate-y-1/2 cursor-row-resize z-50 group overflow-visible",
      style: { pointerEvents: 'auto' },
      onMouseDown: handleMouseDown },
    React.createElement("div", { className: "absolute inset-x-0 top-1/2 -translate-y-1/2 h-[2px] bg-white/10 group-hover:h-[3px] group-hover:bg-accent/70 transition-all duration-150" })
    )
    ));
};
window.ResizablePanel = ResizablePanel;