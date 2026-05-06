const { useState, useEffect, useRef, useCallback } = React;
const GridSplitter = ({ direction = 'vertical', onResize, index }) => {
  const [isDragging, setIsDragging] = useState(false);
  const rafRef = useRef(null);
  const handleMouseDown = useCallback((e) => {
    e.preventDefault();
    setIsDragging(true);
    document.body.style.cursor = direction === 'vertical' ? 'col-resize' : 'row-resize';
    document.body.classList.add('resizing-active');
  }, [direction]);
  useEffect(() => {
    if (!isDragging) return;
    const handleMouseMove = (e) => {
      if (rafRef.current) cancelAnimationFrame(rafRef.current);
      rafRef.current = requestAnimationFrame(() => {
        const pos = direction === 'vertical' ? e.clientX : e.clientY;
        onResize(index, pos);
      });
    };
    const handleMouseUp = () => {
      setIsDragging(false);
      document.body.style.cursor = 'default';
      document.body.classList.remove('resizing-active');
    };
    window.addEventListener('mousemove', handleMouseMove);
    window.addEventListener('mouseup', handleMouseUp);
    return () => {
      window.removeEventListener('mousemove', handleMouseMove);
      window.removeEventListener('mouseup', handleMouseUp);
    };
  }, [isDragging, direction, onResize, index]);
  return (
    React.createElement("div", { className: `relative group ${direction === 'vertical' ? 'h-full w-[12px]' : 'w-full h-[12px]'} bg-transparent hover:bg-white/[0.02] overflow-visible transition-colors` },
    React.createElement("div", {
      onMouseDown: handleMouseDown,
      className: `absolute inset-0 cursor-${direction === 'vertical' ? 'col-resize' : 'row-resize'} z-[100]` }
    ),
    React.createElement("div", { className: `absolute ${direction === 'vertical' ? 'inset-y-0 left-1/2 -translate-x-1/2 w-[2px] group-hover:w-[4px]' : 'inset-x-0 top-1/2 -translate-y-1/2 h-[2px] group-hover:h-[4px]'} bg-border group-hover:bg-accent transition-all duration-200 pointer-events-none` })
    ));
};
window.GridSplitter = GridSplitter;