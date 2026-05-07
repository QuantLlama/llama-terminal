class VolumeProfileEngine {
  constructor() {
    this.profiles = new Map();
    this.config = null;
  }
  setConfig(config) {
    this.config = config;
  }
  getActiveProfiles(bars, rangeMode, params) {
    if (!bars || bars.length === 0) return [];
    const ranges = this._getRanges(bars, rangeMode, params);
    const activeProfiles = [];
    for (const range of ranges) {
      const id = `${rangeMode}_${range.start}`;
      let profile = this.profiles.get(id);
      const isLive = range.isLive;
      if (!profile || isLive) {
        profile = this._computeProfile(range.bars, id, rangeMode, params);
        profile.timeStart = range.start;
        profile.timeEnd = range.end;
        profile.isLive = isLive;
        this.profiles.set(id, profile);
      }
      activeProfiles.push(profile);
    }
    if (this.profiles.size > 50) {
      const sortedIds = Array.from(this.profiles.keys()).sort();
      for (let i = 0; i < sortedIds.length - 50; i++) {
        this.profiles.delete(sortedIds[i]);
      }
    }
    return activeProfiles;
  }
  _getRanges(bars, rangeMode, params) {
    switch (rangeMode) {
      case "session":
        return this._getDailyRanges(bars, params.sessionType || "24h");
      case "weekly":
        return this._getPeriodicRanges(bars, "week");
      case "monthly":
        return this._getPeriodicRanges(bars, "month");
      case "hourly":
        return this._getHourlyRanges(bars, params.hourlyBlock || 60);
      case "visible":
        return [];
      default:
        return [];
    }
  }
  _getDailyRanges(bars, sessionType) {
    const ranges = [];
    let currentDayKey = null;
    let currentRange = null;
    for (const bar of bars) {
      const date = new Date(bar.time * 1000);
      const dayKey = `${date.getFullYear()}-${date.getMonth() + 1}-${date.getDate()}`;
      if (dayKey !== currentDayKey) {
        if (currentRange) {
          currentRange.isLive = false;
        }
        currentDayKey = dayKey;
        currentRange = { start: bar.time, end: bar.time, bars: [bar], isLive: true };
        ranges.push(currentRange);
      } else {
        currentRange.end = bar.time;
        currentRange.bars.push(bar);
      }
    }
    return ranges;
  }
  _getPeriodicRanges(bars, period) {
    const ranges = [];
    let currentPeriodKey = null;
    let currentRange = null;
    for (const bar of bars) {
      const date = new Date(bar.time * 1000);
      let key;
      if (period === "week") {
        const firstDayOfYear = new Date(date.getFullYear(), 0, 1);
        const pastDaysOfYear = (date - firstDayOfYear) / 86400000;
        key = `${date.getFullYear()}-W${Math.ceil((pastDaysOfYear + firstDayOfYear.getDay() + 1) / 7)}`;
      } else {
        key = `${date.getFullYear()}-M${date.getMonth() + 1}`;
      }
      if (key !== currentPeriodKey) {
        if (currentRange) currentRange.isLive = false;
        currentPeriodKey = key;
        currentRange = { start: bar.time, end: bar.time, bars: [bar], isLive: true };
        ranges.push(currentRange);
      } else {
        currentRange.end = bar.time;
        currentRange.bars.push(bar);
      }
    }
    return ranges;
  }
  _getHourlyRanges(bars, blockMinutes) {
    const ranges = [];
    let currentBlockKey = null;
    let currentRange = null;
    const blockSeconds = blockMinutes * 60;
    for (const bar of bars) {
      const blockKey = Math.floor(bar.time / blockSeconds);
      if (blockKey !== currentBlockKey) {
        if (currentRange) currentRange.isLive = false;
        currentBlockKey = blockKey;
        currentRange = { start: bar.time, end: bar.time, bars: [bar], isLive: true };
        ranges.push(currentRange);
      } else {
        currentRange.end = bar.time;
        currentRange.bars.push(bar);
      }
    }
    return ranges;
  }
  _computeProfile(bars, id, rangeMode, params) {
    const bucketCount = params.bucketCount || 100;
    const profileMode = params.profileMode || "volume";
    const vaPercent = params.vaPercent || 70;
    let priceMin = Infinity;
    let priceMax = -Infinity;
    for (const bar of bars) {
      if (bar.low < priceMin) priceMin = bar.low;
      if (bar.high > priceMax) priceMax = bar.high;
    }
    if (priceMax === priceMin) {
      priceMax = priceMin + priceMin * 0.001 || 0.01;
    }
    // 1. Determinar un paso de precio (tick-based) estable en lugar de un bucketCount fijo del rango actual.
    // Esto evita que cuando el rango crezca, el tamaño del bucket cambie.
    const initialRange = Math.max(priceMax - priceMin, 0.00000001);
    // Buscamos un paso que sea múltiplo de 10, 5, 2 o 1 para que sea legible.
    const log = Math.floor(Math.log10(initialRange));
    let baseStep = Math.pow(10, log - 1); // Grid base
    
    // Si queremos aprox 100 buckets, el bucketSize debería ser aprox range/100
    let targetBucketSize = initialRange / bucketCount;
    // Redondear targetBucketSize al múltiplo más cercano de baseStep/10 para estabilidad
    let bucketSize = Math.max(targetBucketSize, baseStep / 20); 
    // Forzar que el bucketSize sea un número "bonito" y estable
    const roundTo = baseStep / 10;
    bucketSize = Math.ceil(bucketSize / roundTo) * roundTo;
    if (bucketSize <= 0) bucketSize = 0.01;

    // 2. Anclar priceMin y priceMax a la rejilla de bucketSize.
    // Muy importante: Esto evita que los buckets se "deslicen" verticalmente.
    priceMin = Math.floor(priceMin / bucketSize) * bucketSize;
    priceMax = Math.ceil(priceMax / bucketSize) * bucketSize;

    // 3. Recalcular el número de buckets necesario para cubrir el rango anclado.
    const actualBucketCount = Math.max(1, Math.min(1000, Math.ceil((priceMax - priceMin) / bucketSize)));
    
    const buckets = Array.from({ length: actualBucketCount }, (_, i) => ({
      priceMin: priceMin + i * bucketSize,
      priceMax: priceMin + (i + 1) * bucketSize,
      priceMid: priceMin + (i + 0.5) * bucketSize,
      volumeTotal: 0,
      volumeUp: 0,
      volumeDown: 0,
      delta: 0,
      tradeCount: 0
    }));

    let runningTotalVolume = 0;
    for (const bar of bars) {
      const barLow = bar.low;
      const barHigh = bar.high;
      const barRange = Math.max(barHigh - barLow, bucketSize * 0.01);
      const isUp = bar.close >= bar.open;
      const barVol = bar.volume || 0;
      const barDelta = bar.delta || 0;
      
      // Encontrar índices basados en la rejilla anclada
      const startIdx = Math.max(0, Math.floor((barLow - priceMin) / bucketSize));
      const endIdx = Math.min(actualBucketCount - 1, Math.floor((barHigh - priceMin) / bucketSize));
      
      for (let i = startIdx; i <= endIdx; i++) {
        const bMin = buckets[i].priceMin;
        const bMax = buckets[i].priceMax;
        const overlapLow = Math.max(barLow, bMin);
        const overlapHigh = Math.min(barHigh, bMax);
        if (overlapHigh > overlapLow) {
          const fraction = (overlapHigh - overlapLow) / barRange;
          let vol = barVol * fraction;
          if (vol < 0.00000001) continue; 
          
          const processedBars = bars.indexOf(bar);
          const avgVol = processedBars > 0 ? runningTotalVolume / processedBars : barVol;
          if (runningTotalVolume > 0 && processedBars > 5 && vol > avgVol * 25) { // Suavizamos un poco más el filtro de outliers
            vol = avgVol * 2.0;
          }

          buckets[i].volumeTotal += vol;
          runningTotalVolume += vol;
          if (isUp) buckets[i].volumeUp += vol; else
          buckets[i].volumeDown += vol;
          buckets[i].delta += barDelta * fraction;
        }
      }
      for (let i = startIdx; i <= endIdx; i++) {
        buckets[i].tradeCount += 1;
      }
    }
    let maxMetricValue = -1;
    let pocIndex = 0;
    let totalVolume = 0;
    for (let i = 0; i < actualBucketCount; i++) {
      totalVolume += buckets[i].volumeTotal;
      let metric;
      switch (profileMode) {
        case "delta": metric = Math.abs(buckets[i].delta); break;
        case "trade_count": metric = buckets[i].tradeCount; break;
        default: metric = buckets[i].volumeTotal;
      }
      if (metric > maxMetricValue) {
        maxMetricValue = metric;
        pocIndex = i;
      }
    }
    const { vahPrice, valPrice } = this._computeValueArea(buckets, pocIndex, vaPercent, totalVolume);
    return {
      id,
      buckets,
      priceMin,
      priceMax,
      bucketSize,
      pocIndex,
      pocPrice: buckets[pocIndex] ? buckets[pocIndex].priceMid : priceMin,
      totalVolume,
      vahPrice,
      valPrice
    };
  }
  _computeValueArea(buckets, pocIndex, vaPercent, totalVolume) {
    if (totalVolume === 0) return { vahPrice: buckets[pocIndex].priceMax, valPrice: buckets[pocIndex].priceMin };
    const targetVolume = totalVolume * (vaPercent / 100);
    let accumulated = buckets[pocIndex].volumeTotal;
    let upper = pocIndex;
    let lower = pocIndex;
    while (accumulated < targetVolume && (upper < buckets.length - 1 || lower > 0)) {
      const volAbove = upper < buckets.length - 1 ? buckets[upper + 1].volumeTotal : 0;
      const volBelow = lower > 0 ? buckets[lower - 1].volumeTotal : 0;
      if (volAbove >= volBelow && upper < buckets.length - 1) {
        upper++;
        accumulated += buckets[upper].volumeTotal;
      } else if (lower > 0) {
        lower--;
        accumulated += buckets[lower].volumeTotal;
      } else if (upper < buckets.length - 1) {
        upper++;
        accumulated += buckets[upper].volumeTotal;
      }
    }
    return {
      vahPrice: buckets[upper].priceMax,
      valPrice: buckets[lower].priceMin
    };
  }
}
window.VolumeProfileEngine = VolumeProfileEngine;