const FootprintRenderer = (() => {
  const IMBALANCE_RATIO = 3.0;
  const MIN_VOL = 1e-12;
  const LABEL_MICRO_PX = 7;
  const LABEL_SINGLE_PX = 11;
  const LABEL_DUAL_PX = 15;
  const FONT_MIN = 6;
  const FONT_ASPECT = 0.58;
  const TRI_SIZE = 7;
  const STACK_MIN = 2;
  const C = {
    textBid: 'rgba(255,  96,  96, 0.95)',
    textAsk: 'rgba(  0, 221, 136, 0.95)',
    textBidImb: '#FF40F0',
    textAskImb: '#00E8FF',
    textNormal: 'rgba(255,255,255, 0.92)',
    textDim: 'rgba(255,255,255, 0.50)',
    textMicro: 'rgba(255,255,255, 0.38)',
    textPOC: 'rgba(  0,  0,  0, 0.92)',
    sep: 'rgba(255,255,255, 0.35)',
    cellBase: 'rgba(  8, 12, 22, 0.72)',
    cellBorder: 'rgba(255,255,255, 0.045)',
    cellPocBg: '#FFB300',
    cellPocBorder: '#FFCC00',
    bidFill: [200, 50, 60],
    askFill: [30, 160, 90],
    heatA: [[0.00, [15, 35, 180]],
    [0.25, [0, 180, 200]],
    [0.50, [60, 200, 0]],
    [0.75, [240, 140, 0]],
    [1.00, [240, 0, 25]]],
    wick: 'rgba(180,185,200, 0.40)',
    bodyBull: 'rgba(  0,220,110, 0.85)',
    bodyBear: 'rgba(230, 40, 75, 0.85)',
    imbTriBuy: '#00E8FF',
    imbTriSell: '#FF40F0',
    imbStackBuy: 'rgba(  0,232,255, 0.18)',
    imbStackSell: 'rgba(255, 64,240, 0.18)',
    curBg: 'rgba(  0,232,255, 0.020)',
    curStrip: 'rgba(  0,232,255, 0.80)',
    deltaPos: 'rgba(  0,220,110, 0.90)',
    deltaNeg: 'rgba(230, 40, 75, 0.90)',
    priceLine: 'rgba(255,215,  0, 0.55)'
  };
  function _rgba([r, g, b], a) {return `rgba(${r},${g},${b},${a.toFixed(3)})`;}
  function _lerpRgb(c1, c2, t) {
    return [c1[0] + (c2[0] - c1[0]) * t | 0, c1[1] + (c2[1] - c1[1]) * t | 0, c1[2] + (c2[2] - c1[2]) * t | 0];
  }
  function _heatColor(r) {
    const stops = C.heatA;
    let s0 = stops[0],s1 = stops[stops.length - 1];
    for (let i = 1; i < stops.length; i++) {
      if (r <= stops[i][0]) {s0 = stops[i - 1];s1 = stops[i];break;}
    }
    const span = s1[0] - s0[0];
    const t = span < 1e-9 ? 0 : (r - s0[0]) / span;
    const c = _lerpRgb(s0[1], s1[1], t);
    return `rgba(${c[0]},${c[1]},${c[2]},${(0.20 + r * 0.80).toFixed(3)})`;
  }
  function hexToRgb(hex) {
    const m = /^#?([a-f\d]{2})([a-f\d]{2})([a-f\d]{2})$/i.exec(hex);
    return m ? [parseInt(m[1], 16), parseInt(m[2], 16), parseInt(m[3], 16)] : null;
  }
  function _buildFills(bidRgb, askRgb) {
    const bid = new Array(256);
    const ask = new Array(256);
    for (let i = 0; i < 256; i++) {
      const a = 0.08 + i / 255 * 0.55;
      bid[i] = _rgba(bidRgb, a);
      ask[i] = _rgba(askRgb, a);
    }
    return { bid, ask };
  }
  function fmtATAS(v, digits = 0) {
    if (v === 0 || v === null || v === undefined) return '0';
    const sign = v < 0 ? '-' : '';
    const a = v < 0 ? -v : v;
    if (a >= 1_000_000_000) return sign + (a / 1_000_000_000).toFixed(1).replace(/\.0$/, '') + 'B';
    if (a >= 1_000_000) return sign + (a / 1_000_000).toFixed(1).replace(/\.0$/, '') + 'M';
    if (a >= 10_000) return sign + (a / 1_000 | 0) + 'k';
    if (a >= 1_000) return sign + (a / 1_000).toFixed(1).replace(/\.0$/, '') + 'k';
    if (a >= 1) return sign + (digits > 0 ? a.toFixed(digits) : (a | 0).toString());
    return sign + a.toFixed(Math.min(digits + 2, 8)).replace(/\.?0+$/, '');
  }
  function fmtMicro(v) {
    if (v === 0 || v === null || v === undefined) return '0';
    const sign = v < 0 ? '-' : '';
    const a = v < 0 ? -v : v;
    if (a >= 1_000_000) return sign + (a / 1_000_000 | 0) + 'M';
    if (a >= 1_000) return sign + (a / 1_000 | 0) + 'k';
    return sign + (a | 0).toString();
  }
  class Renderer {
    constructor() {
      this.canvas = null;
      this.ctx = null;
      this._bgCanvas = null;
      this._bgCtx = null;
      this.chart = null;
      this.mainSeries = null;
      this.footprintData = null;
      this.mode = 'bidask';
      this.enabled = false;
      this.tickSize = 0.25;
      this.fontSize = 11;
      this.showWicks = true;
      this.showPOC = true;
      this.showDelta = true;
      this.wickThickness = 1;
      this.digits = 0;
      this._buyRgb = [0, 200, 100];
      this._sellRgb = [200, 50, 60];
      this._pocRgb = [255, 179, 0];
      this._fills = _buildFills(this._sellRgb, this._buyRgb);
      this._bodyBullColor = 'rgba(0,220,110,0.55)';
      this._bodyBearColor = 'rgba(230,40,75,0.55)';
      this._rafId = null;
      this._isRunning = false;
      this._resizeObs = null;
      this._liveState = null;
      this._bgKey = '';
      this._lastLiveKey = '';
      this._isInteract = false;
      this._interactT = null;
      this._lastViewKey = '';
      this._p2yA = 0;
      this._p2yB = 0;
      this._W = 0;
      this._H = 0;
      this._yTopsBuf = new Int32Array(4096);
      this._imbBuf = new Array(4096).fill(null).map(() => ({ buy: false, sell: false, stackBuy: false, stackSell: false }));
      this._fonts = new Map();
    }
    init(container, chart, mainSeries) {
      if (this.canvas) this.destroy();
      this.chart = chart;
      this.mainSeries = mainSeries;
      this.canvas = document.createElement('canvas');
      Object.assign(this.canvas.style, {
        position: 'absolute', top: '0', left: '0',
        width: '100%', height: '100%',
        pointerEvents: 'none', zIndex: '2000'
      });
      container.appendChild(this.canvas);
      this.ctx = this.canvas.getContext('2d', { alpha: true, desynchronized: true });
      this._bgCanvas = document.createElement('canvas');
      this._bgCtx = this._bgCanvas.getContext('2d', { alpha: true });
      this._syncSize();
      this._resizeObs = new ResizeObserver(() => this._syncSize());
      this._resizeObs.observe(container);
      this._isRunning = true;
      this._tick();
    }
    destroy() {
      this._isRunning = false;
      if (this._rafId) cancelAnimationFrame(this._rafId);
      if (this._resizeObs) this._resizeObs.disconnect();
      if (this.canvas?.parentNode) this.canvas.parentNode.removeChild(this.canvas);
      this.canvas = null;this.ctx = null;
      this._bgCanvas = null;this._bgCtx = null;
    }
    setData(d) {
      if (!d) {
        this.footprintData = null;
        this._liveState = null;
        this._bgKey = '';
        if (this._bgCtx) this._bgCtx.clearRect(0, 0, this._W, this._H);
        return;
      }
      const oldLen = this.footprintData?.candles?.length || 0;
      const newLen = d.candles?.length || 0;
      const lastOld = oldLen > 0 ? this.footprintData.candles[oldLen - 1].time : 0;
      const lastNew = newLen > 0 ? d.candles[newLen - 1].time : 0;
      this.footprintData = d;
      this.tickSize = d.tick_size || 0.25;
      this.digits = d.digits || 0;
      if (this._liveState && d.candles?.length) {
        const lastC = d.candles[d.candles.length - 1];
        if (lastC.time >= this._liveState.time) this._liveState = null;
      }
      if (oldLen !== newLen || lastOld !== lastNew) this._invalidateBg();
    }
    updateLiveState(time, price, volume, side) {
      if (!this.footprintData?.candles?.length) return;
      const lastC = this.footprintData.candles[this.footprintData.candles.length - 1];
      if (!this._liveState || time > this._liveState.time) {
        const prevClose = this._liveState && this._liveState.close !== 0 ?
        this._liveState.close : lastC.close;
        this._liveState = {
          time, open: prevClose,
          high: price, low: price, close: price,
          vol: 0, delta: 0,
          levelsMap: new Map(), levelsSorted: []
        };
        if (time === lastC.time) {
          Object.assign(this._liveState, {
            open: lastC.open, high: lastC.high, low: lastC.low,
            close: lastC.close, vol: lastC.volume || 0, delta: lastC.delta || 0
          });
          if (lastC.levels) {
            for (const l of lastC.levels) {
              const lv = { ...l };
              this._liveState.levelsMap.set(l.price, lv);
              this._liveState.levelsSorted.push(lv);
            }
            this._liveState.levelsSorted.sort((a, b) => a.price - b.price);
          }
        }
      }
      const s = this._liveState;
      if (price > s.high) s.high = price;
      if (price < s.low) s.low = price;
      s.close = price;
      s.vol += volume;
      const isBuy = side === 'buy';
      s.delta += isBuy ? volume : -volume;
      let pKey = price;
      if (this.tickSize > 0) {
        const inv = 1.0 / this.tickSize;
        pKey = Math.round(price * inv) / inv;
        if (this.digits > 0) {
          const f = Math.pow(10, this.digits);
          pKey = Math.round(pKey * f) / f;
        }
      }
      let lv = s.levelsMap.get(pKey);
      if (!lv) {
        lv = { price: pKey, bid: 0, ask: 0, total: 0 };
        s.levelsMap.set(pKey, lv);
        s.levelsSorted.push(lv);
        s.levelsSorted.sort((a, b) => a.price - b.price);
      }
      if (isBuy) lv.ask += volume;else lv.bid += volume;
      lv.total += volume;
      lv._fmtDirty = true;
    }
    setLivePrice() {}
    setMode(v) {this.mode = v;this._invalidateBg();}
    setFontSize(v) {this.fontSize = v;this._fonts.clear();this._invalidateBg();}
    setShowWicks(v) {this.showWicks = v;this._invalidateBg();}
    setShowPOC(v) {this.showPOC = v;this._invalidateBg();}
    setShowDelta(v) {this.showDelta = v;this._invalidateBg();}
    setWickThickness(v) {this.wickThickness = v;this._invalidateBg();}
    setColors(c) {
      if (c.buy) this._buyRgb = hexToRgb(c.buy) || this._buyRgb;
      if (c.sell) this._sellRgb = hexToRgb(c.sell) || this._sellRgb;
      if (c.poc) this._pocRgb = hexToRgb(c.poc) || this._pocRgb;
      if (c.bodyBull) this._bodyBullColor = c.bodyBull;
      if (c.bodyBear) this._bodyBearColor = c.bodyBear;
      this._fills = _buildFills(this._sellRgb, this._buyRgb);
      this._invalidateBg();
    }
    setEnabled(v) {
      this.enabled = v;
      if (this.canvas) this.canvas.style.display = v ? 'block' : 'none';
      if (v) this._invalidateBg();
    }
    _draw() {this._invalidateBg();}
    _invalidateBg() {this._bgKey = '';}
    _syncSize() {
      if (!this.canvas) return;
      const dpr = window.devicePixelRatio || 1;
      const rect = this.canvas.parentNode.getBoundingClientRect();
      const W = rect.width | 0,H = rect.height | 0;
      if (!W || !H) return;
      const pw = W * dpr | 0,ph = H * dpr | 0;
      this.canvas.width = pw;this.canvas.height = ph;
      this._bgCanvas.width = pw;this._bgCanvas.height = ph;
      this.canvas.style.width = `${W}px`;
      this.canvas.style.height = `${H}px`;
      this.ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      this._bgCtx.setTransform(dpr, 0, 0, dpr, 0, 0);
      this._W = W;this._H = H;
      this._invalidateBg();
    }
    _tick() {
      if (!this._isRunning) return;
      try {this._renderFrame();} catch (e) {console.error('[FP v4.0]', e);}
      this._rafId = requestAnimationFrame(() => this._tick());
    }
    _buildTransform(H) {
      const s = this.mainSeries;
      if (!s) return false;
      const yM = H / 2,yT = H * 0.05,yB = H * 0.95;
      const pM = s.coordinateToPrice(yM),pT = s.coordinateToPrice(yT),pB = s.coordinateToPrice(yB);
      if (pM === null || pT === null || pB === null) return false;
      const dp = pB - pT;
      if (Math.abs(dp) < 1e-12) return false;
      const b = (yB - yT) / dp;
      if (b >= 0) return false;
      this._p2yB = b;this._p2yA = yT - pT * b;
      return true;
    }
    _renderFrame() {
      const { ctx, chart, mainSeries, footprintData } = this;
      if (!this.enabled || !ctx || !chart || !mainSeries || !footprintData?.candles?.length) {
        ctx?.clearRect(0, 0, this._W, this._H);return;
      }
      const ts = chart.timeScale();
      const vlr = ts.getVisibleLogicalRange();
      if (!vlr) return;
      const W = this._W,H = this._H;
      if (!W || !H) return;
      const barSpacing = ts.options().barSpacing;
      const candles = footprintData.candles;
      const lastIdx = candles.length - 1;
      const lastC = candles[lastIdx];
      if (!this._buildTransform(H)) {ctx.clearRect(0, 0, W, H);return;}
      const p2yF = (p) => this._p2yA + p * this._p2yB;
      let drawCandle = lastC;
      let isSynthetic = false;
      if (this._liveState && this._liveState.time >= lastC.time) {
        drawCandle = {
          time: this._liveState.time,
          open: this._liveState.open,
          high: this._liveState.high,
          low: this._liveState.low,
          close: this._liveState.close,
          volume: this._liveState.vol,
          delta: this._liveState.delta,
          levels: this._liveState.levelsSorted
        };
        if (drawCandle.time > lastC.time) isSynthetic = true;
      }
      const liveHigh = drawCandle.high;
      const liveLow = drawCandle.low;
      const liveClose = drawCandle.close;
      const pHigh = mainSeries.coordinateToPrice(0);
      const pLow = mainSeries.coordinateToPrice(H);
      if (pHigh === null || pLow === null) return;
      const pMax = Math.max(pHigh, pLow) + this.tickSize * 8;
      const pMin = Math.min(pHigh, pLow) - this.tickSize * 8;
      const fromR = Math.round(vlr.from * 2) / 2;
      const toR = Math.round(vlr.to * 2) / 2;
      const spacR = Math.round(barSpacing * 2) / 2;
      const pHighT = this.tickSize > 0 ? Math.round(pHigh / this.tickSize) : pHigh | 0;
      const pLowT = this.tickSize > 0 ? Math.round(pLow / this.tickSize) : pLow | 0;
      const viewKey = `${fromR}|${toR}|${W}|${H}|${spacR}`;
      if (viewKey !== this._lastViewKey) {
        this._lastViewKey = viewKey;
        this._isInteract = true;
        clearTimeout(this._interactT);
        this._interactT = setTimeout(() => {
          this._isInteract = false;
          this._invalidateBg();
        }, 80);
        this._invalidateBg();
      }
      const bgKey = [
      viewKey, candles.length, this.mode, this.tickSize,
      this.showPOC, this.showWicks, this.showDelta, this.fontSize, this.wickThickness,
      this._buyRgb.join(), this._sellRgb.join(), this._pocRgb.join(),
      pHighT, pLowT].
      join('|');
      const liveKey = `${drawCandle.time}|${liveClose}|${liveHigh}|${liveLow}|${drawCandle.volume}`;
      const bgDirty = bgKey !== this._bgKey;
      const liveDirty = liveKey !== this._lastLiveKey;
      if (!bgDirty && !liveDirty) return;
      const visT0 = ts.coordinateToTime(-barSpacing * 2) || candles[0].time;
      let si = 0;
      {
        let lo = 0,hi = candles.length - 1;
        while (lo <= hi) {
          const m = lo + hi >>> 1;
          if (candles[m].time < visT0) lo = m + 1;else
          {si = m;hi = m - 1;}
        }
        si = Math.max(0, si - 1);
      }
      const cellW = Math.max(2, barSpacing - 1) | 0;
      const halfW = cellW / 2 | 0;
      if (bgDirty) {
        this._bgKey = bgKey;
        const bg = this._bgCtx;
        bg.globalAlpha = 1;
        bg.imageSmoothingEnabled = false;
        bg.setLineDash([]);
        bg.lineWidth = 1;
        bg.clearRect(0, 0, W, H);
        if (this.showWicks) {
          bg.strokeStyle = C.wick;
          bg.lineWidth = this.wickThickness;
          bg.beginPath();
          const wickEnd = isSynthetic ? lastIdx + 1 : lastIdx;
          for (let i = si; i < wickEnd; i++) {
            const c = candles[i];
            const xc = ts.timeToCoordinate(c.time);
            if (xc === null || xc < -cellW) continue;
            if (xc > W + cellW) break;
            const xi = Math.round(xc);
            bg.moveTo(xi, Math.round(p2yF(c.high)));
            bg.lineTo(xi, Math.round(p2yF(c.low)));
          }
          bg.stroke();
        }
        const histEnd = isSynthetic ? lastIdx + 1 : lastIdx;
        for (let i = si; i < histEnd; i++) {
          const candle = candles[i];
          const xc = ts.timeToCoordinate(candle.time);
          if (xc === null || xc < -cellW) continue;
          if (xc > W + cellW) break;
          this._drawCandleFull(
            bg, candle, candle.high, candle.low,
            Math.round(xc - halfW), xc, cellW, p2yF, pMin, pMax, false, H
          );
        }
      }
      if (bgDirty || liveDirty) {
        this._lastLiveKey = liveKey;
        ctx.globalAlpha = 1;
        ctx.imageSmoothingEnabled = false;
        ctx.setLineDash([]);
        ctx.lineWidth = 1;
        ctx.clearRect(0, 0, W, H);
        ctx.drawImage(this._bgCanvas, 0, 0, W, H, 0, 0, W, H);
        const xcLast = ts.timeToCoordinate(drawCandle.time);
        if (xcLast !== null && xcLast >= -cellW && xcLast <= W + cellW) {
          const x = Math.round(xcLast - halfW);
          if (this.showWicks) {
            ctx.strokeStyle = C.wick;
            ctx.lineWidth = this.wickThickness;
            ctx.beginPath();
            ctx.moveTo(Math.round(xcLast), Math.round(p2yF(liveHigh)));
            ctx.lineTo(Math.round(xcLast), Math.round(p2yF(liveLow)));
            ctx.stroke();
          }
          this._drawCandleFull(
            ctx, drawCandle, liveHigh, liveLow,
            x, xcLast, cellW, p2yF, pMin, pMax, true, H
          );
        }
      }
    }
    _drawCandleFull(ctx, candle, high, low, x, xc, cellW, p2yF, pMin, pMax, isCurrent, H) {
      const isBull = candle.close >= candle.open;
      const yHighC = Math.round(p2yF(high));
      const yLowC = Math.round(p2yF(low));
      ctx.fillStyle = isBull ? 'rgba(0,220,110,0.07)' : 'rgba(230,40,75,0.07)';
      ctx.fillRect(x, yHighC, cellW, Math.max(1, yLowC - yHighC));
      const levels = candle.levels || [];
      if (!levels.length) {
        const yO = Math.round(p2yF(candle.open));
        const yC = Math.round(p2yF(candle.close));
        const top = Math.min(yO, yC);
        ctx.fillStyle = isBull ? 'rgba(0,220,110,0.8)' : 'rgba(230,40,75,0.8)';
        ctx.fillRect(x, top, cellW, Math.max(2, Math.abs(yC - yO)));
        return;
      }
      let localMax = MIN_VOL;
      for (let j = 0; j < levels.length; j++) {
        if (levels[j].total > localMax) localMax = levels[j].total;
      }
      let pocPrice = null;
      if (this.showPOC) {
        if (candle.poc != null) {
          pocPrice = candle.poc;
        } else {
          let mx = -1;
          for (let j = 0; j < levels.length; j++) {
            if (levels[j].total > mx) {mx = levels[j].total;pocPrice = levels[j].price;}
          }
        }
      }
      if (isCurrent) this._drawLiveHighlight(ctx, high, low, x, xc, cellW, p2yF, H);
      const N = levels.length;
      if (N >= this._imbBuf.length) {
        const nl = N + 512;
        const ol = this._imbBuf.length;
        this._yTopsBuf = new Int32Array(nl + 1);
        for (let i = ol; i < nl; i++) this._imbBuf[i] = { buy: false, sell: false, stackBuy: false, stackSell: false };
      }
      const imbs = this._imbBuf;
      for (let j = 0; j < N; j++) {
        const imb = imbs[j];
        const lv = levels[j];
        const ask = lv.ask || 0,bid = lv.bid || 0;
        imb.buy = false;imb.sell = false;imb.stackBuy = false;imb.stackSell = false;
        if (j < N - 1) {
          const aboveBid = levels[j + 1].bid || 0;
          if (ask > MIN_VOL && aboveBid > MIN_VOL && ask >= aboveBid * IMBALANCE_RATIO)
          imb.buy = true;
        }
        if (j > 0) {
          const belowAsk = levels[j - 1].ask || 0;
          if (bid > MIN_VOL && belowAsk > MIN_VOL && bid >= belowAsk * IMBALANCE_RATIO)
          imb.sell = true;
        }
      }
      let runBuy = 0,runSell = 0;
      for (let j = 0; j < N; j++) {
        runBuy = imbs[j].buy ? runBuy + 1 : 0;
        runSell = imbs[j].sell ? runSell + 1 : 0;
        if (runBuy >= STACK_MIN) {
          for (let k = j - runBuy + 1; k <= j; k++) imbs[k].stackBuy = true;
        }
        if (runSell >= STACK_MIN) {
          for (let k = j - runSell + 1; k <= j; k++) imbs[k].stackSell = true;
        }
      }
      const yTops = this._yTopsBuf;
      for (let j = 0; j < N; j++) {
        yTops[j] = Math.round(p2yF(levels[j].price + this.tickSize));
      }
      yTops[N] = Math.round(p2yF(levels[0].price));
      for (let j = N - 1; j >= 0; j--) {
        const lv = levels[j];
        const yTop = yTops[j];
        const yBot = j === 0 ? yTops[N] : yTops[j - 1];
        const h = Math.max(1, yBot - yTop);
        if (lv.price + this.tickSize < pMin || lv.price > pMax) continue;
        if (yTop + h < 0 || yTop > H) continue;
        const intensity = lv.total / localMax;
        const idx255 = Math.min(255, intensity * 255 + 0.5 | 0);
        const isPOC = pocPrice !== null && Math.abs(lv.price - pocPrice) < this.tickSize * 0.05;
        this._drawCell(ctx, x, yTop, cellW, h, lv, idx255, intensity, isPOC);
        const imb = imbs[j];
        if (imb.stackBuy) {ctx.fillStyle = C.imbStackBuy;ctx.fillRect(x, yTop, cellW, Math.max(1, h - 1));}
        if (imb.stackSell) {ctx.fillStyle = C.imbStackSell;ctx.fillRect(x, yTop, cellW, Math.max(1, h - 1));}
        if (imb.buy || imb.sell) {
          this._drawImbTriangle(ctx, x, yTop, cellW, h, imb.buy);
        }
        this._drawLabels(ctx, x, yTop, cellW, h, lv, imb, isPOC);
      }
      if (this.showWicks) this._drawBody(ctx, candle, x, cellW, p2yF);
      if (this.showDelta && candle.delta !== undefined && candle.delta !== null) {
        this._drawDelta(ctx, candle.delta, x, cellW, high, low, p2yF, H);
      }
    }
    _drawImbTriangle(ctx, x, yTop, w, h, isBuy) {
      const sz = Math.min(TRI_SIZE, Math.floor(Math.min(w, h) * 0.45));
      if (sz < 2) return;
      ctx.save();
      ctx.beginPath();
      if (isBuy) {
        ctx.moveTo(x + w - sz, yTop);
        ctx.lineTo(x + w, yTop);
        ctx.lineTo(x + w, yTop + sz);
        ctx.closePath();
        ctx.fillStyle = C.imbTriBuy;
      } else {
        ctx.moveTo(x, yTop + h);
        ctx.lineTo(x + sz, yTop + h);
        ctx.lineTo(x, yTop + h - sz);
        ctx.closePath();
        ctx.fillStyle = C.imbTriSell;
      }
      ctx.fill();
      ctx.restore();
    }
    _drawLiveHighlight(ctx, high, low, x, xc, cellW, p2yF, H) {
      if (!isFinite(high) || !isFinite(low)) return;
      const yTopF = p2yF(high),yBotF = p2yF(low);
      const yTop = Math.max(0, Math.round(Math.min(yTopF, yBotF)));
      const yBot = Math.min(H, Math.round(Math.max(yTopF, yBotF)));
      const ht = Math.max(1, yBot - yTop);
      ctx.save();
      ctx.setLineDash([]);
      ctx.fillStyle = C.curBg;
      ctx.fillRect(x, yTop, cellW, ht);
      const stripX = x + cellW + 2;
      if (stripX + 3 <= this._W) {
        ctx.fillStyle = C.curStrip;
        ctx.fillRect(stripX, yTop, 3, ht);
      }
      ctx.restore();
    }
    _drawBody(ctx, candle, x, cellW, p2yF) {
      const open = candle.open,close = candle.close;
      if (!isFinite(open) || !isFinite(close)) return;
      const yO = Math.round(p2yF(open));
      const yC = Math.round(p2yF(close));
      const top = Math.min(yO, yC);
      const ht = Math.max(2, Math.abs(yC - yO));
      if (top + ht < 0 || top > this._H) return;
      ctx.save();
      ctx.strokeStyle = close >= open ? this._bodyBullColor : this._bodyBearColor;
      ctx.lineWidth = 1.5;
      ctx.setLineDash([]);
      ctx.strokeRect(x + 0.5, top + 0.5, cellW - 1, ht - 1);
      ctx.restore();
    }
    _drawDelta(ctx, delta, x, cellW, high, low, p2yF, H) {
      if (!delta && delta !== 0) return;
      const txt = (delta >= 0 ? '+' : '') + fmtATAS(delta, 0);
      const fSz = Math.max(FONT_MIN, Math.min(10, (cellW - 2) * 0.40 | 0));
      const isPos = delta >= 0;
      const yHigh = Math.round(p2yF(high));
      const yLow = Math.round(p2yF(low));
      const yCand = isPos ? yHigh - 3 : yLow + fSz + 1;
      const yFin = Math.max(fSz + 2, Math.min(H - 2, yCand));
      ctx.save();
      ctx.font = `bold ${fSz}px "JetBrains Mono",ui-monospace,Consolas,monospace`;
      ctx.textAlign = 'center';
      ctx.textBaseline = 'bottom';
      ctx.fillStyle = isPos ? C.deltaPos : C.deltaNeg;
      ctx.fillText(txt, x + cellW * 0.5 + 0.5 | 0, yFin);
      ctx.restore();
    }
    _drawCell(ctx, x, y, w, h, lv, idx255, intensity, isPOC) {
      if (h < 1 || w < 1) return;
      ctx.fillStyle = C.cellBase;
      ctx.fillRect(x, y, w, h);
      if (isPOC) {
        ctx.fillStyle = C.cellPocBg;
        ctx.fillRect(x, y, w, h);
      } else {
        if (this.mode === 'bidask') {
          const total = Math.max(lv.total, MIN_VOL);
          const bidFrac = (lv.bid || 0) / total;
          const bidW = bidFrac * w + 0.5 | 0;
          const askW = w - bidW;
          if (bidW > 0) {ctx.fillStyle = this._fills.bid[idx255];ctx.fillRect(x, y, bidW, h);}
          if (askW > 0) {ctx.fillStyle = this._fills.ask[idx255];ctx.fillRect(x + bidW, y, askW, h);}
        } else if (this.mode === 'delta') {
          const delta = (lv.ask || 0) - (lv.bid || 0);
          const ratio = Math.min(Math.abs(delta) / Math.max(lv.total, MIN_VOL), 1);
          const ri = Math.min(255, ratio * 255 + 0.5 | 0);
          ctx.fillStyle = delta >= 0 ? this._fills.ask[ri] : this._fills.bid[ri];
          ctx.fillRect(x, y, w, h);
        } else {
          ctx.fillStyle = _heatColor(intensity);
          ctx.fillRect(x, y, w, h);
        }
      }
      if (h >= 3) {
        if (isPOC) {
          ctx.strokeStyle = C.cellPocBorder;
          ctx.lineWidth = 1.5;
          ctx.strokeRect(x + 0.75, y + 0.75, w - 1.5, h - 1.5);
        } else {
          ctx.strokeStyle = C.cellBorder;
          ctx.lineWidth = 0.5;
          ctx.strokeRect(x + 0.25, y + 0.25, w - 0.5, h - 0.5);
        }
      }
    }
    _drawLabels(ctx, x, y, cellW, h, lv, imb, isPOC) {
      if (h < LABEL_MICRO_PX || cellW < 6) return;
      if (lv._fmtDirty || lv.sB === undefined) {
        lv.sB = fmtATAS(lv.bid || 0, this.digits);
        lv.sA = fmtATAS(lv.ask || 0, this.digits);
        lv.sT = fmtATAS(lv.total || 0, this.digits);
        lv.sD = fmtATAS((lv.ask || 0) - (lv.bid || 0), this.digits);
        lv.sMicro = fmtMicro(lv.total || 0);
        lv._fmtDirty = false;
      }
      let mode;
      if (h >= LABEL_DUAL_PX && this.mode === 'bidask') mode = 'dual';else
      if (h >= LABEL_SINGLE_PX) mode = 'single';else
      mode = 'micro';
      const fontCap = Math.min(this.fontSize, h - 1);
      let finalSz;
      if (mode === 'dual') {
        const chars = lv.sB.length + 3 + lv.sA.length;
        const szW = (cellW - 4) / (chars * FONT_ASPECT);
        const szC = Math.min(fontCap, szW);
        if (szC < 7) {
          mode = 'single';
          const txt2 = this.mode === 'delta' ? lv.sD : lv.sT;
          const sz2 = Math.min(fontCap, (cellW - 2) / (txt2.length * FONT_ASPECT));
          finalSz = Math.max(FONT_MIN, Math.floor(sz2));
          if (finalSz < FONT_MIN) return;
        } else {
          finalSz = Math.max(FONT_MIN, Math.floor(szC));
        }
      } else if (mode === 'single') {
        const txt = this.mode === 'delta' ? lv.sD : lv.sT;
        const sz = Math.min(fontCap, (cellW - 2) / ((txt.length || 1) * FONT_ASPECT));
        finalSz = Math.max(FONT_MIN, Math.floor(sz));
      } else {
        const sz = Math.min(fontCap, (cellW - 1) / ((lv.sMicro.length || 1) * FONT_ASPECT));
        finalSz = Math.max(FONT_MIN, Math.floor(sz));
      }
      if (finalSz < FONT_MIN) return;
      let fc = this._fonts.get(finalSz);
      if (!fc) {
        const f = `${finalSz}px "JetBrains Mono",ui-monospace,Consolas,monospace`;
        fc = { n: f, b: `bold ${f}` };
        this._fonts.set(finalSz, fc);
      }
      ctx.textBaseline = 'middle';
      const xm = x + cellW * 0.5 + 0.5 | 0;
      const ym = y + h * 0.5 + 0.5 | 0;
      const baseText = isPOC ? C.textPOC : C.textNormal;
      if (mode === 'micro') {
        ctx.font = fc.n;
        ctx.fillStyle = isPOC ? C.textPOC : C.textMicro;
        ctx.textAlign = 'center';
        ctx.fillText(lv.sMicro, xm, ym);
      } else if (mode === 'single') {
        const txt = this.mode === 'delta' ? lv.sD : lv.sT;
        ctx.font = fc.n;
        ctx.fillStyle = baseText;
        ctx.textAlign = 'center';
        ctx.fillText(txt, xm, ym);
      } else {
        const bidBold = imb.sell;
        const askBold = imb.buy;
        let bidColor, askColor;
        if (isPOC) {
          bidColor = askColor = C.textPOC;
        } else {
          bidColor = bidBold ? C.textBidImb : C.textBid;
          askColor = askBold ? C.textAskImb : C.textAsk;
        }
        const gapHalf = finalSz * 0.30 | 0;
        ctx.font = bidBold ? fc.b : fc.n;
        ctx.fillStyle = bidColor;
        ctx.textAlign = 'right';
        ctx.fillText(lv.sB, xm - gapHalf, ym);
        ctx.font = fc.n;
        ctx.fillStyle = isPOC ? C.textPOC : C.sep;
        ctx.textAlign = 'center';
        ctx.fillText('×', xm, ym);
        ctx.font = askBold ? fc.b : fc.n;
        ctx.fillStyle = askColor;
        ctx.textAlign = 'left';
        ctx.fillText(lv.sA, xm + gapHalf, ym);
      }
    }
  }
  return { create: () => new Renderer() };
})();
window.FootprintRenderer = FootprintRenderer;