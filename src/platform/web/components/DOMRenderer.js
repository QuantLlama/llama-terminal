(function () {
  'use strict';
  function fmtPrice(p) {
    if (p === 0 || p == null) return '—';
    if (window.formatPrice) return window.formatPrice(p);
    if (p >= 10000) return p.toFixed(1);
    if (p >= 1000) return p.toFixed(2);
    if (p >= 1) return p.toFixed(4);
    return p.toFixed(6);
  }
  function fmtVol(v) {
    if (v == null || isNaN(v)) return '—';
    if (v >= 1e6) return (v / 1e6).toFixed(2) + 'M';
    if (v >= 1e3) return (v / 1e3).toFixed(2) + 'K';
    if (v >= 100) return v.toFixed(1);
    if (v >= 1) return v.toFixed(3);
    return v.toFixed(4);
  }
  function parseRGB(c) {
    if (!c) return [255, 255, 255];
    if (c.startsWith('#')) {
      const h = c.length === 4 ?
      c.slice(1).split('').map((x) => parseInt(x + x, 16)) :
      [parseInt(c.slice(1, 3), 16), parseInt(c.slice(3, 5), 16), parseInt(c.slice(5, 7), 16)];
      return h;
    }
    const m = c.match(/rgba?\((\d+),\s*(\d+),\s*(\d+)/);
    return m ? [+m[1], +m[2], +m[3]] : [255, 255, 255];
  }
  function rgba(r, g, b, a) {
    return `rgba(${r},${g},${b},${(+a).toFixed(3)})`;
  }
  function percentile(arr, p) {
    if (!arr.length) return 1;
    const s = arr.slice().sort((a, b) => a - b);
    return s[Math.min(Math.floor(s.length * p), s.length - 1)] || 1;
  }
  class DOMRenderer {
    constructor(container) {
      this._container = container;
      this._canvas = null;
      this._ctx = null;
      this._dpr = window.devicePixelRatio || 1;
      this._W = 0;
      this._H = 0;
      this._lastData = null;
      this._destroyed = false;
      this._renderN = 0;
      this._loThreshold = null;
      this._sizesBuf = [];
      this._colorCache = new Map();
      this._cfg = {
        bidColor: '#0ea371',
        askColor: '#e03535',
        bgColor: '#0c0c0c',
        headerBg: '#111111',
        rowOdd: '#0c0c0c',
        rowEven: '#111111',
        gridLine: '#1c1c1c',
        midColor: '#f59e0b',
        spreadBg: '#161100',
        mutedColor: '#3d4f5f',
        textColor: '#d4dde8',
        spoofColor: '#f59e0b',
        fontSize: 11,
        fontMono: "'JetBrains Mono','Consolas',monospace",
        rowH: 20,
        compact: false,
        barFill: 0.90,
        showVolumes: true,
        volumeHeatmap: true,
        highlightLargeOrders: true,
        largeOrderThreshold: 0,
        showSpoofingAlerts: true,
        showGhosts: true,
        showActivityFlash: true,
        showRowHighlight: true
      };
      this._mount();
    }
    _getCachedColor(hex) {
      if (!hex) return [255, 255, 255];
      let c = this._colorCache.get(hex);
      if (!c) {
        c = parseRGB(hex);
        this._colorCache.set(hex, c);
      }
      return c;
    }
    _mount() {
      if (!this._container) return;
      this._canvas = document.createElement('canvas');
      this._canvas.style.cssText = 'width:100%;height:100%;display:block;';
      this._container.appendChild(this._canvas);
      this._ctx = this._canvas.getContext('2d');
      this._ro = new ResizeObserver(() => {if (!this._destroyed) this._resize();});
      this._ro.observe(this._container);
      this._resize();
    }
    _resize() {
      if (!this._canvas || !this._container) return;
      const dpr = window.devicePixelRatio || 1;
      const rect = this._container.getBoundingClientRect();
      const w = Math.floor(rect.width) || 1;
      const h = Math.floor(rect.height) || 1;
      if (w === this._W && h === this._H && dpr === this._dpr) return;
      this._dpr = dpr;
      this._canvas.width = w * dpr;
      this._canvas.height = h * dpr;
      this._canvas.style.width = w + 'px';
      this._canvas.style.height = h + 'px';
      this._ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      this._W = w;
      this._H = h;
      if (this._lastData) this.render(this._lastData);
    }
    render(data) {
      if (this._destroyed || !this._ctx || !data) return;
      this._lastData = data;
      const ctx = this._ctx;
      const W = this._W;
      const H = this._H;
      const cfg = this._cfg;
      if (!W || !H) return;
      ctx.globalAlpha = 1;
      ctx.setLineDash([]);
      ctx.fillStyle = cfg.bgColor;
      ctx.fillRect(0, 0, W, H);
      const { bids = [], asks = [], spread, ghosts } = data;
      if (!bids.length && !asks.length) {
        this._noData(ctx, W, H);
        return;
      }
      const rowH = cfg.compact ? 16 : cfg.rowH;
      const HEAD = 40;
      const FOOT = 28;
      const SPREAD = 20;
      const bodyH = H - HEAD - FOOT;
      const priceW = Math.max(70, Math.min(100, W * 0.30));
      const halfW = (W - priceW) / 2;
      const priceX = halfW;
      const spreadY = HEAD + bodyH / 2 - SPREAD / 2;
      
      const [bR, bG, bB] = this._getCachedColor(cfg.bidColor);
      const [aR, aG, aB] = this._getCachedColor(cfg.askColor);
      const [mR, mG, mB] = this._getCachedColor(cfg.midColor);
      
      let loThr = cfg.largeOrderThreshold;
      if (loThr <= 0) {
        if (this._loThreshold === null || this._renderN % 30 === 0) {
          this._sizesBuf.length = 0;
          for (let i = 0; i < bids.length; i++) this._sizesBuf.push(bids[i].size);
          for (let i = 0; i < asks.length; i++) this._sizesBuf.push(asks[i].size);
          this._loThreshold = this._sizesBuf.length > 5 ?
          percentile(this._sizesBuf, 0.90) :
          this._sizesBuf[this._sizesBuf.length - 1] || 1;
        }
        loThr = this._loThreshold;
      }
      this._renderN++;
      this._header(ctx, W, HEAD, data, priceX, priceW, halfW);
      if (cfg.showGhosts && ghosts?.length) {
        this._ghosts(ctx, data, ghosts, HEAD, spreadY, SPREAD, rowH, priceX, priceW, halfW);
      }
      const maxA = Math.floor((spreadY - HEAD) / rowH);
      const showA = asks.length > maxA ? asks.slice(0, maxA) : asks;
      for (let i = 0; i < showA.length; i++) {
        const lv = showA[i];
        const y = spreadY - (i + 1) * rowH;
        if (y < HEAD) continue;
        this._row(ctx, W, y, rowH, i, lv, 'ask',
        aR, aG, aB, mR, mG, mB,
        priceX, priceW, halfW,
        cfg.highlightLargeOrders && lv.size >= loThr, i === 0);
      }
      this._spread(ctx, W, spreadY, SPREAD, spread, mR, mG, mB);
      const spreadBot = spreadY + SPREAD;
      const maxB = Math.floor((H - FOOT - spreadBot) / rowH);
      const showB = bids.length > maxB ? bids.slice(0, maxB) : bids;
      for (let i = 0; i < showB.length; i++) {
        const lv = showB[i];
        const y = spreadBot + i * rowH;
        if (y + rowH > H - FOOT) continue;
        this._row(ctx, W, y, rowH, i, lv, 'bid',
        bR, bG, bB, mR, mG, mB,
        priceX, priceW, halfW,
        cfg.highlightLargeOrders && lv.size >= loThr, i === 0);
      }
      this._footer(ctx, W, H, FOOT, data, bR, bG, bB, aR, aG, aB);
      ctx.globalAlpha = 1;
      ctx.setLineDash([]);
    }
    _row(ctx, W, y, rowH, idx, lv, side,
    cR, cG, cB, mR, mG, mB,
    priceX, priceW, halfW, isLarge, isBest) {
      const cfg = this._cfg;
      const isBid = side === 'bid';
      const norm = Math.min(1, lv.normalizedSize || 0);
      ctx.globalAlpha = 1;
      ctx.fillStyle = idx % 2 === 0 ? cfg.rowEven : cfg.rowOdd;
      ctx.fillRect(0, y, W, rowH);
      if (norm > 0.003) {
        const barW = Math.max(2, norm * halfW * cfg.barFill);
        const barX = isBid ? priceX - barW : priceX + priceW;
        ctx.fillStyle = rgba(cR, cG, cB, 0.55);
        ctx.fillRect(barX, y, barW, rowH);
        const spineX = isBid ? priceX - barW : priceX + priceW + barW - 2;
        ctx.fillStyle = rgba(cR, cG, cB, 0.90);
        ctx.fillRect(spineX, y, 2, rowH);
      }
      if (isBest) {
        ctx.fillStyle = rgba(cR, cG, cB, 0.14);
        ctx.fillRect(0, y, W, rowH);
        const edgeX = isBid ? 0 : W - 2;
        ctx.fillStyle = rgba(cR, cG, cB, 1.0);
        ctx.fillRect(edgeX, y, 2, rowH);
      }
      if (isLarge) {
        const acX = isBid ? priceX - 3 : priceX + priceW + 1;
        ctx.fillStyle = rgba(cR, cG, cB, 1.0);
        ctx.fillRect(acX, y, 3, rowH);
        ctx.fillStyle = rgba(cR, cG, cB, 0.10);
        ctx.fillRect(0, y, W, rowH);
      }
      if (cfg.showSpoofingAlerts && lv.spoofRisk > 0) {
        const sp = Math.min(1, lv.spoofRisk);
        const pulse = 0.5 + 0.5 * Math.sin(Date.now() / 130);
        const bgA = sp * (0.12 + 0.22 * pulse);
        const txtA = sp * (0.55 + 0.45 * pulse);
        const zoneX = isBid ? priceX + priceW : 0;
        const zoneW = halfW;
        const cy2 = y + rowH / 2;
        ctx.fillStyle = `rgba(245,158,11,${bgA.toFixed(3)})`;
        ctx.fillRect(zoneX, y, zoneW, rowH);
        const borderX = isBid ? priceX + priceW : priceX - 1;
        ctx.fillStyle = `rgba(245,158,11,${(sp * 0.90 * (0.6 + 0.4 * pulse)).toFixed(3)})`;
        ctx.fillRect(borderX, y, 2, rowH);
        const pullQty = lv.spoofedSize != null ? lv.spoofedSize : lv.size;
        const pullTxt = `▼ ${fmtVol(pullQty)}`;
        ctx.font = `bold ${cfg.fontSize - 1}px ${cfg.fontMono}`;
        ctx.fillStyle = `rgba(245,158,11,${txtA.toFixed(3)})`;
        ctx.textBaseline = 'middle';
        if (isBid) {
          ctx.textAlign = 'right';
          ctx.fillText(pullTxt, W - 5, cy2);
        } else {
          ctx.textAlign = 'left';
          ctx.fillText(pullTxt, 5, cy2);
        }
        ctx.fillStyle = `rgba(245,158,11,${(sp * 0.50).toFixed(3)})`;
        ctx.fillRect(0, y + rowH - 1, W, 1);
      }
      if (cfg.showActivityFlash && lv.lastUpdate) {
        const age = Date.now() - lv.lastUpdate;
        if (age < 300) {
          const a = (1 - age / 300) * 0.35;
          ctx.fillStyle = rgba(cR, cG, cB, a);
          ctx.fillRect(0, y, W, rowH);
        }
      }
      const cy = y + rowH / 2;
      ctx.textBaseline = 'middle';
      ctx.globalAlpha = 1;
      ctx.textAlign = 'center';
      if (isBest) {
        ctx.font = `bold ${cfg.fontSize}px ${cfg.fontMono}`;
        ctx.fillStyle = rgba(cR, cG, cB, 1.0);
      } else {
        ctx.font = `${cfg.fontSize}px ${cfg.fontMono}`;
        ctx.fillStyle = cfg.textColor;
      }
      ctx.fillText(fmtPrice(lv.price), priceX + priceW / 2, cy);
      if (cfg.showVolumes) {
        const volTxt = fmtVol(lv.size);
        const isSpoofed = cfg.showSpoofingAlerts && lv.spoofRisk > 0;
        ctx.font = `${cfg.fontSize - 1}px ${cfg.fontMono}`;
        ctx.fillStyle = isSpoofed ?
        rgba(cR, cG, cB, 0.80) :
        isLarge ?
        '#f59e0b' :
        isBest ?
        rgba(cR, cG, cB, 0.95) :
        rgba(cR, cG, cB, 0.70);
        if (isBid) {
          ctx.textAlign = 'left';
          ctx.fillText(volTxt, 5, cy);
        } else {
          ctx.textAlign = 'right';
          ctx.fillText(volTxt, W - 5, cy);
        }
      }
      ctx.fillStyle = cfg.gridLine;
      ctx.fillRect(0, y + rowH - 1, W, 1);
    }
    _spread(ctx, W, y, h, spread, mR, mG, mB) {
      const cfg = this._cfg;
      ctx.globalAlpha = 1;
      ctx.fillStyle = cfg.spreadBg;
      ctx.fillRect(0, y, W, h);
      ctx.fillStyle = rgba(mR, mG, mB, 0.50);
      ctx.fillRect(0, y, W, 1);
      ctx.fillRect(0, y + h - 1, W, 1);
      ctx.font = `bold 10px ${cfg.fontMono}`;
      ctx.fillStyle = rgba(mR, mG, mB, 1.0);
      ctx.textAlign = 'center';
      ctx.textBaseline = 'middle';
      ctx.fillText(`SPREAD  ${fmtPrice(spread || 0)}`, W / 2, y + h / 2);
    }
    _header(ctx, W, HEAD, data, priceX, priceW, halfW) {
      const cfg = this._cfg;
      const TITLE = 24;
      const LABELS = HEAD - TITLE;
      ctx.globalAlpha = 1;
      ctx.fillStyle = cfg.headerBg;
      ctx.fillRect(0, 0, W, TITLE);
      ctx.font = `bold 11px ${cfg.fontMono}`;
      ctx.fillStyle = cfg.textColor;
      ctx.textAlign = 'left';
      ctx.textBaseline = 'middle';
      ctx.fillText(`DOM · ${data.symbol || '—'}`, 8, TITLE / 2);
      const levels = (data.bids?.length || 0) + (data.asks?.length || 0);
      ctx.textAlign = 'right';
      ctx.font = `10px ${cfg.fontMono}`;
      ctx.fillStyle = cfg.mutedColor;
      ctx.fillText(`${levels} levels`, W - 8, TITLE / 2);
      ctx.fillStyle = cfg.gridLine;
      ctx.fillRect(0, TITLE - 1, W, 1);
      ctx.fillStyle = '#161616';
      ctx.fillRect(0, TITLE, W, LABELS);
      ctx.font = `9px ${cfg.fontMono}`;
      ctx.fillStyle = cfg.mutedColor;
      ctx.textBaseline = 'middle';
      const ly = TITLE + LABELS / 2;
      ctx.textAlign = 'left';
      ctx.fillText('QTY', 5, ly);
      ctx.textAlign = 'center';
      ctx.fillText('PRICE', priceX + priceW / 2, ly);
      ctx.textAlign = 'right';
      ctx.fillText('QTY', W - 5, ly);
      ctx.fillStyle = cfg.gridLine;
      ctx.fillRect(0, HEAD - 1, W, 1);
      ctx.fillStyle = '#1e1e1e';
      ctx.fillRect(priceX, TITLE, 1, LABELS);
      ctx.fillRect(priceX + priceW, TITLE, 1, LABELS);
    }
    _footer(ctx, W, H, FOOT, data, bR, bG, bB, aR, aG, aB) {
      const cfg = this._cfg;
      const y = H - FOOT;
      ctx.globalAlpha = 1;
      ctx.fillStyle = cfg.headerBg;
      ctx.fillRect(0, y, W, FOOT);
      ctx.fillStyle = cfg.gridLine;
      ctx.fillRect(0, y, W, 1);
      const cy = y + FOOT / 2;
      ctx.font = `10px ${cfg.fontMono}`;
      ctx.textBaseline = 'middle';
      ctx.fillStyle = cfg.mutedColor;
      ctx.textAlign = 'left';
      ctx.fillText('SPR', 6, cy);
      ctx.fillStyle = cfg.textColor;
      ctx.fillText(fmtPrice(data.spread || 0), 32, cy);
      const imb = data.imbalance || 0;
      const bw = 60;
      const bh = 6;
      const bx = W / 2 - bw / 2;
      const by = cy - bh / 2;
      ctx.fillStyle = '#1a1a1a';
      ctx.fillRect(bx, by, bw, bh);
      if (imb > 0) {
        ctx.fillStyle = rgba(bR, bG, bB, 0.85);
        ctx.fillRect(W / 2, by, imb * (bw / 2), bh);
      } else if (imb < 0) {
        const fw = Math.abs(imb) * (bw / 2);
        ctx.fillStyle = rgba(aR, aG, aB, 0.85);
        ctx.fillRect(W / 2 - fw, by, fw, bh);
      }
      ctx.fillStyle = '#333';
      ctx.fillRect(W / 2 - 0.5, by - 1, 1, bh + 2);
      const pct = (Math.abs(imb) * 100).toFixed(1);
      const lbl = imb > 0 ? `B +${pct}%` : imb < 0 ? `A +${pct}%` : 'BAL';
      ctx.textAlign = 'right';
      ctx.fillStyle = imb > 0 ?
      rgba(bR, bG, bB, 1) :
      imb < 0 ?
      rgba(aR, aG, aB, 1) :
      cfg.mutedColor;
      ctx.fillText(lbl, W - 6, cy);
    }
    _ghosts(ctx, data, ghosts, HEAD, spreadY, SPREAD, rowH, priceX, priceW, halfW) {
      const cfg = this._cfg;
      const now = Date.now();
      const LIFE = 2500;
      const [sR, sG, sB] = parseRGB(cfg.spoofColor);
      ctx.save();
      for (const g of ghosts) {
        const age = now - g.timestamp;
        const life = Math.max(0, 1 - age / LIFE);
        if (life <= 0) continue;
        const isAsk = g.type === 'ask';
        let rowY;
        if (isAsk) {
          const ref = data.asks;
          const step = ref[1]?.price - ref[0]?.price || 0.01;
          const idx = ref.findIndex((a) => a.price === g.price);
          rowY = idx !== -1 ?
          spreadY - (idx + 1) * rowH :
          spreadY - ((g.price - ref[0]?.price) / step + 1) * rowH;
        } else {
          const ref = data.bids;
          const step = ref[0]?.price - ref[1]?.price || 0.01;
          const idx = ref.findIndex((b) => b.price === g.price);
          rowY = idx !== -1 ?
          spreadY + SPREAD + idx * rowH :
          spreadY + SPREAD + (ref[0]?.price - g.price) / step * rowH;
        }
        if (rowY < HEAD || rowY > this._H - 28) continue;
        const norm = data.maxVolume > 0 ? g.size / data.maxVolume : 0;
        const barW = Math.max(4, norm * halfW * cfg.barFill);
        const pulse = 0.5 + 0.5 * Math.sin(now / 160);
        let barX;
        if (isAsk) {
          barX = Math.max(0, priceX - barW);
        } else {
          barX = priceX + priceW;
        }
        ctx.globalAlpha = life * (0.35 + 0.20 * pulse);
        ctx.setLineDash([3, 3]);
        ctx.strokeStyle = rgba(sR, sG, sB, 1);
        ctx.lineWidth = 1;
        ctx.strokeRect(barX + 1, rowY + 2, barW - 2, rowH - 4);
        ctx.setLineDash([]);
        ctx.fillStyle = rgba(sR, sG, sB, 0.12 + 0.10 * pulse);
        ctx.fillRect(barX, rowY, barW, rowH);
        ctx.globalAlpha = life * (0.65 + 0.35 * pulse);
        ctx.font = `bold 8px ${cfg.fontMono}`;
        ctx.fillStyle = rgba(sR, sG, sB, 1);
        ctx.textBaseline = 'middle';
        const cy = rowY + rowH / 2;
        if (isAsk) {
          ctx.textAlign = 'left';
          ctx.fillText(`↙ ${fmtVol(g.size)}`, barX + 2, cy);
        } else {
          ctx.textAlign = 'right';
          ctx.fillText(`${fmtVol(g.size)} ↗`, barX + barW - 2, cy);
        }
      }
      ctx.globalAlpha = 1;
      ctx.setLineDash([]);
      ctx.restore();
    }
    _noData(ctx, W, H) {
      const cfg = this._cfg;
      ctx.globalAlpha = 1;
      ctx.font = `12px ${cfg.fontMono}`;
      ctx.fillStyle = cfg.mutedColor;
      ctx.textAlign = 'center';
      ctx.textBaseline = 'middle';
      ctx.fillText('No DOM data available', W / 2, H / 2 - 10);
      ctx.font = `10px ${cfg.fontMono}`;
      ctx.fillText('Waiting for order book…', W / 2, H / 2 + 10);
    }
    setConfig(u) {
      const c = this._cfg;
      const norm = (val) => val ?? undefined;
      if (u.bidColor != null) c.bidColor = u.bidColor;
      if (u.askColor != null) c.askColor = u.askColor;
      if (u.bgColor != null) c.bgColor = u.bgColor;
      if (u.spoofColor != null) c.spoofColor = u.spoofColor;
      if (u.midpointColor != null) c.midColor = u.midpointColor;
      if (u.textColor != null) c.textColor = u.textColor;
      if (u.rowBgEven != null) c.rowEven = u.rowBgEven;
      if (u.compact != null) c.compact = u.compact;
      if (u.showVolumes != null) c.showVolumes = u.showVolumes;
      if (u.volumeHeatmap != null) c.volumeHeatmap = u.volumeHeatmap;
      if (u.highlightLargeOrders != null) c.highlightLargeOrders = u.highlightLargeOrders;
      if (u.largeOrderThreshold != null) c.largeOrderThreshold = u.largeOrderThreshold;
      if (u.showSpoofingAlerts != null) c.showSpoofingAlerts = u.showSpoofingAlerts;
      if (u.showGhosts != null) c.showGhosts = u.showGhosts;
      if (u.showActivityFlash != null) c.showActivityFlash = u.showActivityFlash;
      if (u.showRowHighlight != null) c.showRowHighlight = u.showRowHighlight;
      if (u.rowHeight != null) c.rowH = u.rowHeight;
      this._loThreshold = null;
      if (this._lastData) this.render(this._lastData);
    }
    getConfig() {return { ...this._cfg };}
    destroy() {
      this._destroyed = true;
      this._ro?.disconnect();
      this._canvas?.parentNode?.removeChild(this._canvas);
      this._canvas = null;
      this._ctx = null;
      this._lastData = null;
    }
  }
  window.DOMRenderer = DOMRenderer;
})();