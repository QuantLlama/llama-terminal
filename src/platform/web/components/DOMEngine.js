(function () {
  'use strict';
  class DOMEngine {
    constructor() {
      this._bids = [];
      this._asks = [];
      this._spread = 0;
      this._midpoint = 0;
      this._maxVolume = 0;
      this._totalBidVol = 0;
      this._totalAskVol = 0;
      this._timestamp = 0;
      this._symbol = '';
      this._prevBids = new Map();
      this._prevAsks = new Map();
      this._lastUpdateTs = new Map();
      this._scaleMode = 'linear';
      this._cumulative = false;
      this._minVolumeFilter = 0;
      this._history = new Map();
      this._ghosts = [];
      this._spoofConfig = {
        enabled: true,
        sensitivity: 0.5,
        persistenceThreshold: 3000,
        minSizeRatio: 2.0
      };
    }
    processSnapshot(data) {
      if (!data) return null;
      
      // console.log("[DOM_ENGINE] Processing snapshot:", {
      //   symbol: data?.symbol,
      //   bids: data?.bids?.length,
      //   asks: data?.asks?.length
      // });

      // CRITICAL FIX: Ensure bids and asks are valid arrays before processing lengths
      if (!Array.isArray(data.bids) || !Array.isArray(data.asks)) {
        console.warn("[DOM_ENGINE] Rejected snapshot: missing or invalid bids/asks array", data);
        return null;
      }

      this._symbol = data.symbol || '';
      this._timestamp = data.timestamp || Date.now() / 1000;
      this._spread = data.spread || 0;
      this._midpoint = data.midpoint || 0;

      const minVol = this._minVolumeFilter;
      const cumulative = this._cumulative;
      let maxVol = 0;
      let totalBidVol = 0;
      let totalAskVol = 0;

      // PASS 1: Filter, Map, Total Vol, Max Vol
      const processedBids = [];
      let cumBid = 0;
      for (let i = 0; i < data.bids.length; i++) {
        const b = data.bids[i];
        if (b.size < minVol) continue;
        
        const size = cumulative ? (cumBid += b.size) : b.size;
        processedBids.push({ price: b.price, size: size, count: b.count || 1 });
        totalBidVol += b.size;
        if (size > maxVol) maxVol = size;
      }

      const processedAsks = [];
      let cumAsk = 0;
      for (let i = 0; i < data.asks.length; i++) {
        const a = data.asks[i];
        if (a.size < minVol) continue;

        const size = cumulative ? (cumAsk += a.size) : a.size;
        processedAsks.push({ price: a.price, size: size, count: a.count || 1 });
        totalAskVol += a.size;
        if (size > maxVol) maxVol = size;
      }

      this._maxVolume = maxVol || 1;
      this._totalBidVol = totalBidVol;
      this._totalAskVol = totalAskVol;

      const scaleMode = this._scaleMode;
      const normalize = (size) => {
        if (maxVol === 0) return 0;
        if (scaleMode === 'logarithmic') {
          return Math.log1p(size) / Math.log1p(maxVol);
        }
        return size / maxVol;
      };

      const now = Date.now();
      
      // PASS 2: Bids (Normalization & Delta)
      for (let i = 0; i < processedBids.length; i++) {
        const b = processedBids[i];
        const prevSize = this._prevBids.get(b.price) || 0;
        let deltaType = null;
        if (b.size > prevSize && prevSize > 0) deltaType = 'increase';
        else if (b.size < prevSize) deltaType = 'decrease';
        
        if (deltaType) this._lastUpdateTs.set(b.price, now);
        this._prevBids.set(b.price, b.size);
        
        b.normalizedSize = normalize(b.size);
        b.deltaType = deltaType;
        b.lastUpdate = this._lastUpdateTs.get(b.price) || 0;
      }
      this._bids = processedBids;

      // PASS 2: Asks (Normalization & Delta)
      for (let i = 0; i < processedAsks.length; i++) {
        const a = processedAsks[i];
        const prevSize = this._prevAsks.get(a.price) || 0;
        let deltaType = null;
        if (a.size > prevSize && prevSize > 0) deltaType = 'increase';
        else if (a.size < prevSize) deltaType = 'decrease';
        
        if (deltaType) this._lastUpdateTs.set(a.price, now);
        this._prevAsks.set(a.price, a.size);
        
        a.normalizedSize = normalize(a.size);
        a.deltaType = deltaType;
        a.lastUpdate = this._lastUpdateTs.get(a.price) || 0;
      }
      this._asks = processedAsks;

      this._updateSpoofingAnalysis();

      return {
        symbol: this._symbol,
        timestamp: this._timestamp,
        bids: this._bids,
        asks: this._asks,
        spread: this._spread,
        midpoint: this._midpoint,
        maxVolume: this._maxVolume,
        totalBidVolume: this._totalBidVol,
        totalAskVolume: this._totalAskVol,
        imbalance: this.getImbalance(),
        ghosts: this._ghosts.filter((g) => Date.now() - g.timestamp < 2000)
      };
    }
    _updateSpoofingAnalysis() {
      if (!this._spoofConfig.enabled) return;
      const now = Date.now();
      const currentLevels = new Map();
      const allLevels = [...this._bids, ...this._asks];
      allLevels.forEach((lvl) => {
        currentLevels.set(lvl.price, lvl.size);
      });
      this._history.forEach((data, price) => {
        const currentSize = currentLevels.get(price);
        if (currentSize === undefined) {
          const delta = data.size;
          const duration = now - data.timestamp;
          const isGiant = data.size > this._maxVolume * 0.4;
          const isQuick = duration < this._spoofConfig.persistenceThreshold;
          const proximity = Math.abs(price - this._midpoint) / this._midpoint;
          const isNear = proximity < 0.005;
          if (isGiant && isQuick && isNear) {
            data.score = Math.min(1.0, data.size / this._maxVolume * (1.1 - proximity * 10));
            if (data.score > 0.3) {
              this._ghosts.push({
                price,
                size: data.size,
                type: price < this._midpoint ? 'bid' : 'ask',
                timestamp: now,
                score: data.score
              });
            }
          }
          this._history.delete(price);
        } else if (currentSize < data.size) {
          const reduction = data.size - currentSize;
          if (reduction > this._maxVolume * 0.25) {
            data.lastUpdate = now;
          }
          data.size = currentSize;
        } else {
          data.size = currentSize;
          data.lastUpdate = now;
        }
      });
      const tagLevel = (lvl) => {
        const hist = this._history.get(lvl.price);
        if (hist) {
          const proximity = Math.abs(lvl.price - this._midpoint) / this._midpoint;
          const isGiant = lvl.size > this._maxVolume * 0.7;
          const isNear = proximity < 0.003;
          if (isGiant && isNear) {
            lvl.spoofRisk = Math.min(1.0, lvl.size / this._maxVolume);
          }
        } else {
          this._history.set(lvl.price, {
            size: lvl.size,
            timestamp: now,
            lastUpdate: now,
            score: 0
          });
        }
      };
      this._bids.forEach(tagLevel);
      this._asks.forEach(tagLevel);
      if (this._ghosts.length > 50) {
        this._ghosts = this._ghosts.slice(-50);
      }
    }
    getImbalance() {
      const total = this._totalBidVol + this._totalAskVol;
      if (total === 0) return 0;
      return (this._totalBidVol - this._totalAskVol) / total;
    }
    setScaleMode(mode) {
      this._scaleMode = mode === 'logarithmic' ? 'logarithmic' : 'linear';
    }
    setCumulative(enabled) {
      this._cumulative = !!enabled;
    }
    setMinVolumeFilter(minVol) {
      this._minVolumeFilter = Math.max(0, minVol || 0);
    }
    setSpoofConfig(cfg) {
      this._spoofConfig = { ...this._spoofConfig, ...cfg };
    }
    get bids() {return this._bids;}
    get asks() {return this._asks;}
    get spread() {return this._spread;}
    get midpoint() {return this._midpoint;}
    get maxVolume() {return this._maxVolume;}
    get symbol() {return this._symbol;}
    get timestamp() {return this._timestamp;}
  }
  window.DOMEngine = DOMEngine;
})();