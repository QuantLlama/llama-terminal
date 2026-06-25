class VolumeProfileRenderer {
  constructor(chart, chartContainer) {
    this.chart = chart;
    this.container = chartContainer;
    this.canvas = document.createElement("canvas");
    this.canvas.className = "volume-profile-overlay";
    this.canvas.style.cssText = `
        position: absolute;
        top: 0;
        left: 0;
        width: 100%;
        height: 100%;
        pointer-events: none;
        z-index: 5;
    `;
    this.container.appendChild(this.canvas);
    this.ctx = this.canvas.getContext("2d");
    this._pixelRatio = window.devicePixelRatio || 1;
    this._rafId = null;
    this.scheduleRender = this.scheduleRender.bind(this);
    this._drawScheduled = this._drawScheduled.bind(this);
    
    this.chart.timeScale().subscribeVisibleLogicalRangeChange(this.scheduleRender);
    this.chart.timeScale().subscribeVisibleTimeRangeChange(this.scheduleRender);
    this.chart.subscribeCrosshairMove(this.scheduleRender);
    this._isDrawing = false;
    this._needsRedraw = false;
    this._lastPriceCoord = null;
    this._lastTimeCoord = null;
    this._monitorRaf = null;
    this._priceScale = null;
    const monitorScale = () => {
        if (this._destroyed) return;
        if (this.chart && this._latestSeries) {
            try {
                const pc = this._latestSeries.priceToCoordinate(0) || this._latestSeries.priceToCoordinate(100);
                const logicalRange = this.chart.timeScale().getVisibleLogicalRange();
                const tc = logicalRange ? logicalRange.from : null;
                if (pc !== this._lastPriceCoord || tc !== this._lastTimeCoord) {
                    this._lastPriceCoord = pc;
                    this._lastTimeCoord = tc;
                    this.scheduleRender();
                }
            } catch(e) {}
        }
        this._monitorRaf = requestAnimationFrame(monitorScale);
    };
    this._monitorRaf = requestAnimationFrame(monitorScale);
  }
  render(profiles, params, series) {
    if (this._latestSeries !== series) {
      try {
        this._priceScale?.unsubscribeVisiblePriceRangeChange?.(this.scheduleRender);
      } catch (e) {}
      this._priceScale = null;
      try {
        this._priceScale = series?.priceScale?.() || null;
        this._priceScale?.subscribeVisiblePriceRangeChange?.(this.scheduleRender);
      } catch (e) {}
    }
    this._latestProfiles = profiles;
    this._latestParams = params;
    this._latestSeries = series;
    this.scheduleRender();
  }
  scheduleRender() {
    if (this._destroyed) return;
    if (this._rafId) {
      this._needsRedraw = true;
      return;
    }
    this._rafId = requestAnimationFrame(() => {
      this._rafId = null;
      this._isDrawing = true;
      try { this._drawScheduled(); } catch(e) {}
      this._isDrawing = false;
      if (this._needsRedraw) {
        this._needsRedraw = false;
        this.scheduleRender();
      }
    });
  }
  _drawScheduled() {
    if (this._destroyed) return;
    if (this._latestProfiles && this._latestParams && this._latestSeries) {
      this._drawFrame(this._latestProfiles, this._latestParams, this._latestSeries);
    }
  }
  _drawFrame(profiles, params, series) {
    const rect = this.container.getBoundingClientRect();
    if (this.canvas.width !== rect.width * this._pixelRatio || this.canvas.height !== rect.height * this._pixelRatio) {
      this.canvas.width = rect.width * this._pixelRatio;
      this.canvas.height = rect.height * this._pixelRatio;
    }
    this.ctx.save();
    this.ctx.scale(this._pixelRatio, this._pixelRatio);
    this.ctx.clearRect(0, 0, rect.width, rect.height);
    const timeScale = this.chart.timeScale();
    const width = rect.width;
    for (const profile of profiles) {
      this._renderSingleProfile(profile, params, series, width, timeScale);
    }
    this.ctx.restore();
  }
  _renderSingleProfile(profile, params, series, canvasW, timeScale) {
    const { buckets, pocIndex, priceMin, priceMax, vahPrice, valPrice, pocPrice } = profile;
    const profileId = profile.id || profile.timeStart;
    
    let maxVol = buckets[pocIndex]?.volumeTotal || 1;
    if (maxVol === 0) maxVol = 1;

    let xStart = 0;
    let xEnd = canvasW;
    if (params.rangeMode !== "visible" && timeScale) {
      let visibleRange = null;
      let tStart = null;
      let tEnd = null;
      try {
        visibleRange = timeScale.getVisibleRange();
        if (!visibleRange) return;
        tStart = timeScale.timeToCoordinate(profile.timeStart);
        tEnd = timeScale.timeToCoordinate(profile.timeEnd);
      } catch (e) {
        return;
      }
      xStart = tStart ?? (profile.timeStart < visibleRange.from ? 0 : canvasW);
      xEnd = tEnd ?? (profile.timeEnd > visibleRange.to ? canvasW : 0);
      if (xEnd <= xStart) return;
    }
    const profileWidth = xEnd - xStart;
    // Estilo ATAS: Los perfiles no suelen ocupar toda la pantalla. 35% por defecto.
    const histW = profileWidth * ((params.histogramWidth || 35) / 100);
    const isLeft = params.histogramSide === "left";
    
    if (params.showHistogram !== false) {
      this.ctx.save();
      
      // Crear gradiente espectral horizontal (Estilo ATAS Spectral)
      const grad = this.ctx.createLinearGradient(
        isLeft ? xStart : xEnd, 
        0, 
        isLeft ? xStart + histW : xEnd - histW, 
        0
      );
      grad.addColorStop(0.0, "rgba(30, 58, 138, 0.95)");  // Deep Blue
      grad.addColorStop(0.2, "rgba(6, 182, 212, 0.95)");  // Cyan
      grad.addColorStop(0.5, "rgba(16, 185, 129, 0.95)"); // Emerald Green
      grad.addColorStop(0.8, "rgba(245, 158, 11, 0.95)"); // Amber/Yellow
      grad.addColorStop(1.0, "rgba(239, 68, 68, 0.95)");  // Red

      for (let i = 0; i < buckets.length; i++) {
        const bucket = buckets[i];
        if (params.noiseThreshold > 0) {
          if (bucket.volumeTotal / maxVol * 100 < params.noiseThreshold) continue;
        }
        const yTop = series.priceToCoordinate(bucket.priceMax);
        const yBot = series.priceToCoordinate(bucket.priceMin);
        if (yTop === null || yBot === null) continue;
        
        // Ajuste para evitar gaps entre barras y dar estilo sólido profesional
        const h = Math.max(1.8, Math.abs(yBot - yTop));
        const y = Math.min(yTop, yBot);
        
        const ratio = bucket.volumeTotal / maxVol;
        // Escala No-Lineal (Gamma): Evita que un POC extremo aplaste y deforme visualmente 
        // los demás nodos hacia atrás, manteniendo la campana de volumen visible y estructurada.
        const adjustedRatio = Math.pow(ratio, 0.55);
        const barW = histW * adjustedRatio;
        const x = isLeft ? xStart : xEnd - barW;
        
        let color = grad;
        // Si el usuario eligió estilo sólido o estamos en modo delta
        if (params.colorStyle === "solid" && params.profileMode !== "delta") {
          color = bucket.volumeUp < bucket.volumeDown ? (params.colorDown || "#ef5350") : (params.colorUp || "#26a69a");
        } else if (params.profileMode === "delta") {
          color = bucket.delta >= 0 ? params.colorDeltaPos || "#26a69a" : params.colorDeltaNeg || "#ef5350";
        }
        
        // Estilo ATAS: Resaltar Nodos de Valor (Value Area) reduciendo opacidad afuera
        const isVA = bucket.priceMax <= vahPrice && bucket.priceMin >= valPrice;
        this.ctx.globalAlpha = isVA ? (params.opacity ?? 0.85) : (params.opacity ?? 0.85) * 0.20;
        
        this.ctx.fillStyle = color;
        this.ctx.fillRect(x, Math.floor(y), barW, Math.ceil(h));
      }
      this.ctx.restore();
    }
    
    const renderVah = vahPrice;
    const renderVal = valPrice;
    // Si están extendidas, van hasta el final de la pantalla (canvasW)
    // Si no, van hasta el final de la sesión (xEnd) para cubrir toda la duración del perfil
    const lineEndX = params.extendLines ? canvasW : xEnd;
    
    if (params.showVa !== false && renderVah && renderVal) {
      const vahY = series.priceToCoordinate(renderVah);
      const valY = series.priceToCoordinate(renderVal);
      if (vahY !== null && valY !== null) {
        this.ctx.strokeStyle = params.colorVah || "rgba(255, 255, 255, 0.4)";
        this.ctx.lineWidth = params.vaLineWidth || 1;
        this.ctx.setLineDash(params.vaLineStyle === 2 ? [4, 4] : []);
        this.ctx.beginPath();
        this.ctx.moveTo(xStart, vahY);
        this.ctx.lineTo(lineEndX, vahY);
        this.ctx.stroke();
        
        this.ctx.strokeStyle = params.colorVal || "rgba(255, 255, 255, 0.4)";
        this.ctx.beginPath();
        this.ctx.moveTo(xStart, valY);
        this.ctx.lineTo(lineEndX, valY);
        this.ctx.stroke();
        this.ctx.setLineDash([]);
        
        if (params.showLabels) {
          this.ctx.font = "9px Inter, sans-serif";
          this.ctx.fillStyle = "rgba(255, 255, 255, 0.6)";
          this.ctx.fillText(`VAH ${renderVah.toFixed(2)}`, xStart + 5, vahY - 3);
          this.ctx.fillText(`VAL ${renderVal.toFixed(2)}`, xStart + 5, valY + 11);
        }
      }
    }
    const renderPoc = pocPrice;
    if (params.showPoc !== false && renderPoc) {
      const yPoc = series.priceToCoordinate(renderPoc);
      if (yPoc !== null) {
        this.ctx.beginPath();
        this.ctx.strokeStyle = params.colorPoc || "#fbbf24"; // Amarillo dorado más llamativo
        this.ctx.lineWidth = 2;
        this.ctx.setLineDash([]);
        this.ctx.moveTo(xStart, yPoc);
        this.ctx.lineTo(lineEndX, yPoc);
        this.ctx.stroke();
        
        // Destello central POC
        this.ctx.fillStyle = params.colorPoc || "#fbbf24";
        this.ctx.fillRect(isLeft ? xStart : xStart + histW - 3, yPoc - 1.5, 3, 3);
        
        if (params.showLabels) {
          this.ctx.font = "bold 10px Inter, sans-serif";
          this.ctx.fillStyle = params.colorPoc || "#fbbf24";
          this.ctx.fillText(`POC ${renderPoc.toFixed(2)}`, xStart + 5, yPoc - 4);
        }
      }
    }
  }
  clear() {
    const rect = this.container.getBoundingClientRect();
    this.ctx.clearRect(0, 0, rect.width, rect.height);
  }
  destroy() {
    this._destroyed = true;
    try {
      this._priceScale?.unsubscribeVisiblePriceRangeChange?.(this.scheduleRender);
    } catch (e) {}
    if (this.chart) {
      this.chart.timeScale().unsubscribeVisibleLogicalRangeChange(this.scheduleRender);
      this.chart.timeScale().unsubscribeVisibleTimeRangeChange(this.scheduleRender);
      this.chart.unsubscribeCrosshairMove(this.scheduleRender);
    }
    if (this._rafId) cancelAnimationFrame(this._rafId);
    if (this._monitorRaf) cancelAnimationFrame(this._monitorRaf);
    if (this.canvas && this.canvas.parentNode) {
      this.canvas.parentNode.removeChild(this.canvas);
    }
  }
}
window.VolumeProfileRenderer = VolumeProfileRenderer;
