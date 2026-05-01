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
    this._profilesState = new Map();
    this._latestProfiles = null;
    this._latestParams = null;
    this._latestSeries = null;
    this._rafId = null;
    this._animate = this._animate.bind(this);
    this._rafId = requestAnimationFrame(this._animate);
  }
  render(profiles, params, series) {
    this._latestProfiles = profiles;
    this._latestParams = params;
    this._latestSeries = series;
  }
  _animate() {
    if (this._destroyed) return;
    if (this._latestProfiles && this._latestParams && this._latestSeries) {
      this._drawFrame(this._latestProfiles, this._latestParams, this._latestSeries);
    }
    this._rafId = requestAnimationFrame(this._animate);
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
    const { buckets, pocIndex, priceMin, priceMax, vahPrice, valPrice } = profile;
    const profileId = profile.id || profile.timeStart;
    let state = this._profilesState.get(profileId);
    if (!state) {
      const initialMaxVol = buckets[pocIndex]?.volumeTotal || 1;
      state = {
        maxVol: initialMaxVol,
        pocPrice: profile.pocPrice,
        vahPrice: profile.vahPrice || 0,
        valPrice: profile.valPrice || 0,
        frameCount: 0
      };
      this._profilesState.set(profileId, state);
    }
    state.frameCount++;
    const smoothing = state.frameCount < 5 ? 1.0 : 0.15;
    let targetMaxVol = buckets[pocIndex]?.volumeTotal || 1;
    if (targetMaxVol === 0) targetMaxVol = 1;
    state.maxVol += (targetMaxVol - state.maxVol) * smoothing;
    if (profile.pocPrice) state.pocPrice += (profile.pocPrice - state.pocPrice) * smoothing;
    if (profile.vahPrice) state.vahPrice += (profile.vahPrice - state.vahPrice) * smoothing;
    if (profile.valPrice) state.valPrice += (profile.valPrice - state.valPrice) * smoothing;
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
    const histW = profileWidth * ((params.histogramWidth || 70) / 100);
    const isLeft = params.histogramSide === "left";
    if (params.showHistogram !== false) {
      this.ctx.save();
      this.ctx.globalAlpha = params.opacity ?? 0.65;
      for (let i = 0; i < buckets.length; i++) {
        const bucket = buckets[i];
        if (params.noiseThreshold > 0) {
          if (bucket.volumeTotal / state.maxVol * 100 < params.noiseThreshold) continue;
        }
        const yTop = series.priceToCoordinate(bucket.priceMax);
        const yBot = series.priceToCoordinate(bucket.priceMin);
        if (yTop === null || yBot === null) continue;
        const h = Math.abs(yBot - yTop);
        const y = Math.min(yTop, yBot);
        const ratio = bucket.volumeTotal / state.maxVol;
        const barW = histW * ratio;
        const x = isLeft ? xStart : xEnd - barW;
        let color = params.colorUp || "#26a69a";
        if (params.profileMode === "delta") {
          color = bucket.delta >= 0 ? params.colorDeltaPos || "#26a69a" : params.colorDeltaNeg || "#ef5350";
        } else if (bucket.volumeUp < bucket.volumeDown) {
          color = params.colorDown || "#ef5350";
        }
        this.ctx.fillStyle = color;
        this.ctx.fillRect(x, y, barW, h);
      }
      this.ctx.restore();
    }
    const renderVah = state.vahPrice;
    const renderVal = state.valPrice;
    if (params.showVa !== false && renderVah && renderVal) {
      const vahY = series.priceToCoordinate(renderVah);
      const valY = series.priceToCoordinate(renderVal);
      if (vahY !== null && valY !== null) {
        this.ctx.strokeStyle = params.colorVah || "rgba(255, 255, 255, 0.3)";
        this.ctx.lineWidth = params.vaLineWidth || 1;
        if (params.vaLineStyle === 2) this.ctx.setLineDash([4, 4]);else
        this.ctx.setLineDash([]);
        this.ctx.beginPath();
        this.ctx.moveTo(xStart, vahY);
        this.ctx.lineTo(xStart + profileWidth, vahY);
        this.ctx.stroke();
        this.ctx.strokeStyle = params.colorVal || "rgba(255, 255, 255, 0.3)";
        this.ctx.beginPath();
        this.ctx.moveTo(xStart, valY);
        this.ctx.lineTo(xStart + profileWidth, valY);
        this.ctx.stroke();
        this.ctx.setLineDash([]);
        if (params.showLabels) {
          this.ctx.font = "9px Inter, sans-serif";
          this.ctx.fillStyle = "rgba(255, 255, 255, 0.5)";
          this.ctx.fillText(`VAH ${renderVah.toFixed(2)}`, xStart + 5, vahY - 3);
          this.ctx.fillText(`VAL ${renderVal.toFixed(2)}`, xStart + 5, valY + 11);
        }
      }
    }
    const renderPoc = state.pocPrice;
    if (params.showPoc !== false && renderPoc) {
      const yPoc = series.priceToCoordinate(renderPoc);
      if (yPoc !== null) {
        this.ctx.beginPath();
        this.ctx.strokeStyle = params.colorPoc || "#3b82f6";
        this.ctx.lineWidth = 2;
        this.ctx.setLineDash([]);
        this.ctx.moveTo(xStart, yPoc);
        this.ctx.lineTo(xEnd, yPoc);
        this.ctx.stroke();
        if (params.showLabels) {
          this.ctx.font = "bold 10px Inter, sans-serif";
          this.ctx.fillStyle = params.colorPoc || "#3b82f6";
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
    if (this._rafId) cancelAnimationFrame(this._rafId);
    if (this.canvas && this.canvas.parentNode) {
      this.canvas.parentNode.removeChild(this.canvas);
    }
  }
}
window.VolumeProfileRenderer = VolumeProfileRenderer;