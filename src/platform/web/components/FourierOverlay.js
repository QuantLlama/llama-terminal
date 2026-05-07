const FourierOverlay = ({ chart, series, fourierData, visible = true }) => {
  const { useState, useEffect, useRef, useMemo, useCallback } = React;
  const canvasRef = useRef();
  useEffect(() => {
    if (!chart || !series || !fourierData || !visible) {
      return;
    }
    const updateCanvas = () => {
      const canvas = canvasRef.current;
      if (!canvas) return;
      const container = canvas.parentElement;
      if (container) {
        canvas.width = container.clientWidth;
        canvas.height = container.clientHeight;
      }
      const ctx = canvas.getContext('2d');
      const timeScale = chart.timeScale();
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      if (fourierData.projection && fourierData.projection.length > 0) {
        const visibleRange = timeScale.getVisibleLogicalRange();
        if (!visibleRange) return;
        const barSpacing = canvas.width / (visibleRange.to - visibleRange.from);
        const rightmostX = canvas.width;
        ctx.beginPath();
        ctx.setLineDash([]);
        ctx.strokeStyle = '#FBBF24';
        ctx.lineWidth = 2;
        const startX = canvas.width * 0.75;
        const projectionWidth = canvas.width * 0.25;
        const projectionBarSpacing = projectionWidth / (fourierData.projection.length - 1);
        fourierData.projection.forEach((p, i) => {
          const x = startX + i * projectionBarSpacing;
          const y = series.priceToCoordinate(p.value);
          if (y !== null && x <= canvas.width) {
            if (i === 0) ctx.moveTo(x, y);else
            ctx.lineTo(x, y);
          }
        });
        ctx.stroke();
        ctx.setLineDash([]);
      }
      if (fourierData.reconstruction && fourierData.reconstruction.length > 0) {
        ctx.beginPath();
        ctx.strokeStyle = '#22D3EE';
        ctx.lineWidth = 1.5;
        ctx.setLineDash([]);
        fourierData.reconstruction.forEach((p, i) => {
          let x = timeScale.timeToCoordinate(p.time);
          if (x === null) {
            x = timeScale.timeToCoordinate(p.time * 1000);
          }
          if (x === null) {
            x = timeScale.timeToCoordinate(p.time / 1000);
          }
          const y = series.priceToCoordinate(p.value);
          if (x !== null && y !== null) {
            if (i === 0) ctx.moveTo(x, y);else
            ctx.lineTo(x, y);
          }
        });
        ctx.stroke();
      }
      if (fourierData.harmonics && fourierData.harmonics.length > 0) {
        fourierData.harmonics.forEach((h, idx) => {
          if (!h.points) return;
          const colors = [
          'rgba(34, 197, 94, 0.5)',
          'rgba(239, 68, 68, 0.5)',
          'rgba(59, 130, 246, 0.4)',
          'rgba(168, 85, 247, 0.4)'];
          const color = colors[idx % colors.length];
          ctx.beginPath();
          ctx.strokeStyle = color;
          ctx.lineWidth = 1;
          ctx.setLineDash([]);
          h.points.forEach((p, i) => {
            let x = timeScale.timeToCoordinate(p.time);
            if (x === null) {
              x = timeScale.timeToCoordinate(p.time * 1000);
            }
            if (x === null) {
              x = timeScale.timeToCoordinate(p.time / 1000);
            }
            const y = series.priceToCoordinate(p.value);
            if (x !== null && y !== null) {
              if (i === 0) ctx.moveTo(x, y);else
              ctx.lineTo(x, y);
            }
          });
          ctx.stroke();
        });
      }
      ctx.setLineDash([]);
    };
    const handleResize = () => {
      if (canvasRef.current && chart.chartElement) {
        canvasRef.current.width = chart.chartElement().clientWidth;
        canvasRef.current.height = chart.chartElement().clientHeight;
        updateCanvas();
      }
    };
    chart.timeScale().subscribeVisibleTimeRangeChange(updateCanvas);
    const interval = setInterval(updateCanvas, 100);
    handleResize();
    window.addEventListener('resize', handleResize);
    return () => {
      chart.timeScale().unsubscribeVisibleTimeRangeChange(updateCanvas);
      clearInterval(interval);
      window.removeEventListener('resize', handleResize);
    };
  }, [chart, series, fourierData, visible]);
  if (!visible) return null;
  return (
    React.createElement(React.Fragment, null,
    React.createElement("canvas", {
      ref: canvasRef,
      className: "absolute inset-0 pointer-events-none",
      style: { opacity: 1.0, zIndex: 5 } }
    ),
    visible && fourierData &&
    React.createElement("div", { className: "absolute top-[75px] left-2 bg-gray-900/90 border border-gray-700 rounded-lg p-3 text-xs z-10 pointer-events-auto",
      style: { maxWidth: '280px' } },
    React.createElement("div", { className: "font-bold text-white mb-2 flex items-center gap-2" },
    React.createElement("svg", { className: "w-4 h-4", fill: "none", stroke: "currentColor", viewBox: "0 0 24 24" },
    React.createElement("path", { strokeLinecap: "round", strokeLinejoin: "round", strokeWidth: 2, d: "M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" })
    ), "An\xE1lisis de Fourier"
    ),
    React.createElement("div", { className: "space-y-1.5" },
    React.createElement("div", { className: "flex items-center gap-2" },
    React.createElement("div", { className: "w-8 h-0.5", style: { backgroundColor: '#FBBF24' } }),
    React.createElement("span", { className: "text-gray-300" }, "Proyecci\xF3n Futura")
    ),
    React.createElement("div", { className: "flex items-center gap-2" },
    React.createElement("div", { className: "w-8 h-0.5", style: { backgroundColor: '#22D3EE' } }),
    React.createElement("span", { className: "text-gray-300" }, "Reconstrucci\xF3n Hist\xF3rica")
    ),
    React.createElement("div", { className: "flex items-center gap-2" },
    React.createElement("div", { className: "w-8 h-0.5", style: { backgroundColor: 'rgba(34, 197, 94, 0.8)' } }),
    React.createElement("span", { className: "text-gray-300" }, "Bandas Arm\xF3nicas")
    )
    )
    )
    ));
};