const TpoRenderer = ({ chart, series, data, settings, visible = true }) => {
  const { useEffect, useRef, useMemo } = React;
  const canvasRef = useRef(null);
  const dataRef = useRef(data);
  const settingsRef = useRef(settings);
  const visibleRef = useRef(visible);

  useEffect(() => {
    dataRef.current = data;
    settingsRef.current = settings;
    visibleRef.current = visible;
  }, [data, settings, visible]);

  const profiles = useMemo(() => {
    if (!data || data.length === 0) return [];
    
    let currentSessionId = null;
    let currentProfile = null;
    const parsedProfiles = [];
    const tpoSettings = settings?.indicators?.tpo || {};
    const sp = tpoSettings.sessionPeriod || '1d';
    const bp = tpoSettings.blockPeriod || 30;
    
    let tickSize = tpoSettings.rowSize;
    if (!tickSize || tickSize <= 0) {
      let sumBody = 0;
      let valid = 0;
      const count = Math.min(1000, data.length);
      for(let i=data.length - count; i<data.length; i++) {
         sumBody += (data[i].high - data[i].low);
         valid++;
      }
      const avg = valid > 0 ? sumBody / valid : 1;
      tickSize = avg > 0 ? Number((avg / 25).toPrecision(1)) : 1;
      if (tickSize === 0) tickSize = 1;
    }

    const getSessionId = (time) => {
      const d = new Date(time * 1000);
      if (sp === '1w') {
        const d2 = new Date(d);
        d2.setUTCDate(d2.getUTCDate() - d2.getUTCDay()); 
        return d2.toLocaleDateString();
      }
      if (sp === '1M') {
        return `${d.getUTCFullYear()}-${d.getUTCMonth()}`;
      }
      // '1d' or default
      return d.toLocaleDateString();
    };

    data.forEach(candle => {
      const sid = getSessionId(candle.time);
      if (sid !== currentSessionId) {
        if (currentProfile) parsedProfiles.push(currentProfile);
        currentSessionId = sid;
        currentProfile = {
          id: sid,
          startTime: candle.time,
          endTime: candle.time,
          high: candle.high,
          low: candle.low,
          tpoMap: {} // mapping of priceLevel -> array of blocks (letters)
        };
      }
      
      const msSinceStart = (candle.time - currentProfile.startTime) * 1000;
      const minsSinceStart = msSinceStart / 60000;
      const blockIndex = Math.floor(minsSinceStart / bp);
      // Letras de A a Z, luego a a z
      const blockLetter = String.fromCharCode(blockIndex < 26 ? 65 + blockIndex : (blockIndex < 52 ? 97 + (blockIndex - 26) : 63));

      // Expand low to high using tickSize
      const minLevel = Math.floor(candle.low / tickSize) * tickSize;
      const maxLevel = Math.floor(candle.high / tickSize) * tickSize;
      
      for (let p = minLevel; p <= maxLevel + 1e-9; p += tickSize) {
        const pl = Number(p.toFixed(8)); // fix floating point quirks
        if (!currentProfile.tpoMap[pl]) currentProfile.tpoMap[pl] = new Set();
        currentProfile.tpoMap[pl].add(blockLetter);
      }
      
      currentProfile.high = Math.max(currentProfile.high, candle.high);
      currentProfile.low = Math.min(currentProfile.low, candle.low);
      currentProfile.endTime = candle.time;
    });
    
    if (currentProfile) parsedProfiles.push(currentProfile);

    // Calcular POC y VA
    parsedProfiles.forEach(prof => {
      let totalTpos = 0;
      let maxTpoCount = 0;
      let pocLevel = null;
      
      const levels = Object.keys(prof.tpoMap).map(Number).sort((a,b)=>a-b);
      
      levels.forEach(lvl => {
        const count = prof.tpoMap[lvl].size;
        totalTpos += count;
        if (count > maxTpoCount) {
          maxTpoCount = count;
          pocLevel = lvl;
        }
      });
      
      // VA (70% rule)
      const targetVA = totalTpos * 0.7;
      let currentVA = maxTpoCount;
      let upIdx = levels.indexOf(pocLevel) + 1;
      let downIdx = levels.indexOf(pocLevel) - 1;
      
      while (currentVA < targetVA && (upIdx < levels.length || downIdx >= 0)) {
        let upVol = 0;
        let downVol = 0;
        
        if (upIdx < levels.length) upVol = prof.tpoMap[levels[upIdx]].size;
        if (downIdx >= 0) downVol = prof.tpoMap[levels[downIdx]].size;
        
        if (upVol >= downVol && upVol > 0) {
          currentVA += upVol;
          upIdx++;
        } else if (downVol > 0) {
          currentVA += downVol;
          downIdx--;
        } else {
          break;
        }
      }
      
      prof.poc = pocLevel;
      prof.vah = upIdx > 0 && upIdx <= levels.length ? levels[upIdx - 1] : levels[levels.length - 1];
      prof.val = downIdx >= -1 && downIdx < levels.length - 1 ? levels[downIdx + 1] : levels[0];
      prof.levels = levels;
      prof.tickSize = tickSize;
    });

    return parsedProfiles;
  }, [data, settings?.indicators?.tpo?.sessionPeriod, settings?.indicators?.tpo?.blockPeriod, settings?.indicators?.tpo?.rowSize]);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas || !chart || !series) return;
    const ctx = canvas.getContext('2d');
    let animationFrameId;

    const render = () => {
      if (!visibleRef.current || profiles.length === 0) {
        ctx.clearRect(0, 0, canvas.width, canvas.height);
        animationFrameId = requestAnimationFrame(render);
        return;
      }

      const dpr = window.devicePixelRatio || 1;
      const rect = canvas.getBoundingClientRect();
      const canvasWidth = rect.width * dpr;
      const canvasHeight = rect.height * dpr;

      if (canvas.width !== canvasWidth || canvas.height !== canvasHeight) {
        canvas.width = canvasWidth;
        canvas.height = canvasHeight;
      }

      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.clearRect(0, 0, rect.width, rect.height);

      const timeScale = chart.timeScale();
      const visibleRange = timeScale.getVisibleLogicalRange();
      if (!visibleRange) {
        animationFrameId = requestAnimationFrame(render);
        return;
      }

      const tpoSettings = settingsRef.current?.indicators?.tpo || {};
      const colorVA = tpoSettings.colorVA || "rgba(59, 130, 246, 0.5)";
      const colorTPO = tpoSettings.colorTPO || "rgba(107, 114, 128, 0.3)";
      const colorPOC = tpoSettings.colorPOC || "#ef4444";
      const colorIB = tpoSettings.colorIB || "rgba(234, 179, 8, 0.8)";
      
      ctx.textBaseline = 'middle';
      ctx.textAlign = 'left';

      // Dibujamos solo los perfiles que podrían estar en pantalla (simplificado)
      profiles.forEach(prof => {
        const startX = timeScale.timeToCoordinate(prof.startTime);
        const endX = timeScale.timeToCoordinate(prof.endTime);
        
        // Si el perfil entero está fuera de la pantalla (muy a la izq o muy a la der)
        if (startX === null && endX === null) return;
        if (startX !== null && startX > rect.width) return;
        if (endX !== null && endX < 0) return;

        const drawX = startX !== null ? startX : 0; 
        
        // Determinar altura de fila (cuanto espacio hay para cada TPO y)
        const yTop = series.priceToCoordinate(prof.high);
        const yBot = series.priceToCoordinate(prof.low);
        if (yTop === null || yBot === null) return;
        
        const tickDistPx = Math.abs(series.priceToCoordinate(prof.levels[0]) - series.priceToCoordinate(prof.levels[0] + prof.tickSize));
        const rowH = Math.max(1, tickDistPx);
        
        const drawText = rowH >= 6;
        const letterW = drawText ? rowH * 0.7 : Math.max(2, Math.min(rowH, 6));
        
        if (drawText) {
          ctx.font = `bold ${Math.floor(rowH * 0.8)}px "Inter", sans-serif`;
        }

        // Draw POC Line background
        if (tpoSettings.showPOC !== false && prof.poc !== null) {
          const pocY = series.priceToCoordinate(prof.poc);
          if (pocY !== null) {
            ctx.fillStyle = colorPOC;
            ctx.globalAlpha = 0.2;
            const maxLetters = prof.tpoMap[prof.poc].size;
            ctx.fillRect(drawX, pocY - rowH/2, maxLetters * letterW, rowH);
            ctx.globalAlpha = 1.0;
            // Linea extendida
            ctx.strokeStyle = colorPOC;
            ctx.lineWidth = 1;
            ctx.beginPath();
            ctx.moveTo(drawX + maxLetters * letterW, pocY);
            ctx.lineTo(rect.width, pocY);
            ctx.stroke();
          }
        }

        prof.levels.forEach(lvl => {
          const y = series.priceToCoordinate(lvl);
          if (y === null || y < -rowH || y > rect.height + rowH) return;
          
          const tpoSet = prof.tpoMap[lvl];
          const isVA = lvl >= prof.val && lvl <= prof.vah;
          const isPOC = lvl === prof.poc;
          
          let curX = drawX;
          
          ctx.fillStyle = isPOC ? colorPOC : (isVA ? colorVA : colorTPO);
          
          if (!drawText) {
            // Draw blocks instead of letters
            ctx.fillRect(curX, y - rowH/2, tpoSet.size * letterW, Math.max(1, rowH - 0.5));
          } else {
            // Draw letters
            let idx = 0;
            for (let letter of tpoSet) {
              // Highlight initial balance (usually A and B)
              const isIB = letter === 'A' || letter === 'B';
              if (isIB && tpoSettings.showIB !== false) {
                 ctx.fillStyle = colorIB;
              } else {
                 ctx.fillStyle = isPOC ? colorPOC : (isVA ? colorVA : colorTPO);
              }
              ctx.fillText(letter, curX + idx * letterW, y);
              idx++;
            }
          }
        });
      });

      animationFrameId = requestAnimationFrame(render);
    };

    animationFrameId = requestAnimationFrame(render);
    return () => {
      cancelAnimationFrame(animationFrameId);
    };
  }, [chart, series, profiles, visible]);

  return (
    React.createElement("canvas", {
      ref: canvasRef,
      className: "absolute inset-0 w-full h-full pointer-events-none",
      style: { zIndex: 11, display: visible ? 'block' : 'none' } 
    })
  );
};

window.TpoRenderer = TpoRenderer;
