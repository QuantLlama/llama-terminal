function _nthWeekday(year, month, dayOfWeek, n) {
  const d = new Date(Date.UTC(year, month, 1));
  let count = 0;
  while (d.getUTCMonth() === month) {
    if (d.getUTCDay() === dayOfWeek) {
      count++;
      if (count === n) return d.getTime();
    }
    d.setUTCDate(d.getUTCDate() + 1);
  }
  return d.getTime();
}
function _lastWeekday(year, month, dayOfWeek) {
  const d = new Date(Date.UTC(year, month + 1, 0));
  while (d.getUTCDay() !== dayOfWeek) {
    d.setUTCDate(d.getUTCDate() - 1);
  }
  return d.getTime();
}
function _isUsDst(now = new Date()) {
  const y = now.getUTCFullYear();
  const start = _nthWeekday(y, 2, 0, 2) + 7 * 3600 * 1000;
  const end = _nthWeekday(y, 10, 0, 1) + 6 * 3600 * 1000;
  return now.getTime() >= start && now.getTime() < end;
}
function _isEuDst(now = new Date()) {
  const y = now.getUTCFullYear();
  const start = _lastWeekday(y, 2, 0) + 1 * 3600 * 1000;
  const end = _lastWeekday(y, 9, 0) + 1 * 3600 * 1000;
  return now.getTime() >= start && now.getTime() < end;
}
const _US_INDEX_RE = /\b(sp[x5]|us[_\s]?500|s&p|nas|ndx|nq|ust[e]?c|nasdaq|us30|dj[ia]?|dow|ymf?|rty|russell|us2000)\b/i;
const _EU_INDEX_RE = /\b(dax|fdax|ger[_\s]?30|ger[_\s]?40|ftse|uk[_\s]?10[05]|cac|fra[_\s]?40|ibex|esp[_\s]?35|euro[_\s]?50|stoxx|fts|mib|smi|aex|bel[_\s]?20|sttd)\b/i;
const _AU_INDEX_RE = /\b(asx|as[x]?[_\s]?200|aord)\b/i;
const _JP_INDEX_RE = /\b(nikkei|n225|topix|jpy[_\s]?ind)\b/i;
const _WTI_RE = /\b(wti|us[_\s]?oil|usoil|oil|cl[a-z]?[\d]?|crudeoil|cru|luz)\b/i;
const _BRENT_RE = /\b(brent|ukoil|uk[_\s]?oil|bo[a-z]?[\d]?|lco|brt)\b/i;
const _METALS_RE = /\b(xau|xag|gold|silver|gc[a-z]?[\d]?|si[a-z]?[\d]?|gld|ags)\b/i;
const _NATGAS_RE = /\b(ng[a-z]?[\d]?|ngas|natural[_\s]?gas|hen)\b/i;
const _CRYPTO_RE = /\b(btc|eth|sol|ada|xrp|dot|doge|shib|ltc|link|matic|avax|bnb|usdt|usdc)\b/i;
function _classifySymbol(symbol) {
  if (!symbol) return 'DEFAULT';
  try {
    if (typeof window !== 'undefined' && window.localStorage && window.localStorage.getItem('platform') === 'crypto') {
      return 'CRYPTO';
    }
  } catch (e) {}
  const s = symbol.toUpperCase().replace(/[_.\-/]/g, ' ');
  if (_CRYPTO_RE.test(s) || s.includes('USDT')) return 'CRYPTO';
  if (_US_INDEX_RE.test(s)) return 'US_INDEX';
  if (_EU_INDEX_RE.test(s)) return 'EU_INDEX';
  if (_AU_INDEX_RE.test(s)) return 'AU_INDEX';
  if (_JP_INDEX_RE.test(s)) return 'JP_INDEX';
  if (_WTI_RE.test(s)) return 'US_CRUDE';
  if (_BRENT_RE.test(s)) return 'EU_CRUDE';
  if (_METALS_RE.test(s)) return 'METALS';
  if (_NATGAS_RE.test(s)) return 'NATURAL_GAS';
  return 'FOREX';
}
function _getSessionWindows(instrClass, now) {
  const usDst = _isUsDst(now);
  const euDst = _isEuDst(now);
  switch (instrClass) {
    case 'US_INDEX':{
        const usOff = usDst ? 4 : 5;
        const preOpen = 4;
        const regOpen = 9.5;
        const regClose = 16;
        const aftClose = 20;
        return [
        { id: 'PRE', label: 'Pre-Market', color: 'bg-gray-400', open: preOpen - usOff, close: regOpen - usOff, isOpen: true },
        { id: 'NY', label: 'New York', color: 'bg-green-500', open: regOpen - usOff, close: regClose - usOff, isOpen: true },
        { id: 'POST', label: 'After Hours', color: 'bg-gray-500', open: regClose - usOff, close: aftClose - usOff, isOpen: true }];
      }
    case 'EU_INDEX':{
        const cetOff = euDst ? 2 : 1;
        return [
        { id: 'EU', label: 'European', color: 'bg-blue-500', open: 9 - cetOff, close: 17.5 - cetOff, isOpen: true }];
      }
    case 'AU_INDEX':{
        const auOff = 10;
        return [
        { id: 'AU', label: 'ASX', color: 'bg-yellow-400', open: 10 - auOff + 24, close: 16 - auOff + 24, isOpen: true }];
      }
    case 'JP_INDEX':{
        return [
        { id: 'JP', label: 'Tokyo', color: 'bg-orange-400', open: 0, close: 6.5, isOpen: true },
        { id: 'BREAK', label: 'Lunch', color: 'bg-gray-600', open: 2.5, close: 3.5, isOpen: false }];
      }
    case 'US_CRUDE':
    case 'NATURAL_GAS':{
        const ctOff = usDst ? 5 : 6;
        return [
        { id: 'NYMEX', label: 'NYMEX', color: 'bg-orange-500', open: 18 - ctOff, close: 17 - ctOff + 24, isOpen: true },
        { id: 'BREAK', label: 'Break', color: 'bg-gray-600', open: 17 - ctOff, close: 18 - ctOff, isOpen: false }];
      }
    case 'EU_CRUDE':{
        return [
        { id: 'ICE', label: 'ICE Brent', color: 'bg-amber-500', open: 1, close: 23, isOpen: true }];
      }
    case 'METALS':{
        const etOff = usDst ? 4 : 5;
        return [
        { id: 'COMEX', label: 'COMEX', color: 'bg-yellow-500', open: 18 - etOff, close: 17 - etOff + 24, isOpen: true },
        { id: 'BREAK', label: 'Break', color: 'bg-gray-600', open: 17 - etOff, close: 18 - etOff, isOpen: false }];
      }
    case 'CRYPTO':{
        return [
        { id: 'CRYPTO', label: 'Crypto 24/7', color: 'bg-purple-500', open: 0, close: 24, isOpen: true }];
      }
    default:{
        const lonOpen = euDst ? 7 : 8;
        const lonClose = euDst ? 16 : 17;
        const nyAbsOff = usDst ? 4 : 5;
        const nyOpenUTC = 9.5 + nyAbsOff;
        const nyCloseUTC = 17 + nyAbsOff;
        const overlapStart = Math.max(lonOpen, nyOpenUTC);
        const overlapEnd = Math.min(lonClose, nyCloseUTC);
        return [
        { id: 'ASIA', label: 'Asia (Tokyo)', color: 'bg-yellow-500', open: 0, close: 9, isOpen: true },
        { id: 'LONDON', label: 'London', color: 'bg-blue-500', open: lonOpen, close: lonClose, isOpen: true },
        { id: 'LON_NY', label: 'London × NY', color: 'bg-purple-500 animate-pulse', open: overlapStart, close: overlapEnd, isOpen: true },
        { id: 'NY', label: 'New York', color: 'bg-green-500', open: nyOpenUTC, close: nyCloseUTC, isOpen: true }];
      }
  }
}
function _isWeekend(now, instrClass) {
  const dow = now.getUTCDay();
  const utcH = now.getUTCHours() + now.getUTCMinutes() / 60;
  if (instrClass === 'CRYPTO') return false;
  const is24h = ['FOREX', 'METALS', 'US_CRUDE', 'EU_CRUDE', 'NATURAL_GAS'].includes(instrClass);
  if (is24h) {
    if (dow === 6) return true;
    if (dow === 0 && utcH < 22) return true;
    if (dow === 5 && utcH >= 22) return true;
    return false;
  }
  return dow === 0 || dow === 6;
}
export const getMarketSession = (symbol = '') => {
  const now = new Date();
  const instrClass = _classifySymbol(symbol);
  const usDst = _isUsDst(now);
  const euDst = _isEuDst(now);
  if (_isWeekend(now, instrClass)) {
    return {
      session: 'WEEKEND',
      label: 'Weekend',
      color: 'bg-red-500',
      isOpen: false,
      description: 'Market Closed — Weekend',
      instrClass,
      isDst: { us: usDst, eu: euDst }
    };
  }
  const utcH = now.getUTCHours() + now.getUTCMinutes() / 60;
  const windows = _getSessionWindows(instrClass, now);
  let matched = null;
  const active = windows.filter((w) => {
    let { open, close } = w;
    if (close > 24) {
      return utcH >= open || utcH < close - 24;
    }
    return utcH >= open && utcH < close;
  });
  if (active.length > 0) {
    const priority = ['LON_NY', 'NY', 'LONDON', 'ASIA', 'NYMEX', 'COMEX', 'ICE', 'EU', 'JP', 'AU', 'PRE', 'POST', 'CRYPTO'];
    active.sort((a, b) => {
      const ia = priority.indexOf(a.id);
      const ib = priority.indexOf(b.id);
      return (ia === -1 ? 99 : ia) - (ib === -1 ? 99 : ib);
    });
    matched = active[0];
  }
  if (matched) {
    if (!matched.isOpen) {
      return {
        session: 'BREAK',
        label: 'Daily Break',
        color: 'bg-gray-500',
        isOpen: false,
        description: `${instrClass} — Daily Settlement Break`,
        instrClass,
        isDst: { us: usDst, eu: euDst }
      };
    }
    let sessionId = matched.id;
    if (active.length > 1 && active.some((w) => w.id === 'LONDON') && active.some((w) => w.id === 'NY')) {
      sessionId = 'LON+NY';
    }
    return {
      session: sessionId,
      label: matched.label,
      color: matched.color,
      isOpen: true,
      description: matched.label,
      instrClass,
      isDst: { us: usDst, eu: euDst }
    };
  }
  return {
    session: 'CLOSED',
    label: 'Closed',
    color: 'bg-red-500',
    isOpen: false,
    description: `${instrClass} — Outside Trading Hours`,
    instrClass,
    isDst: { us: usDst, eu: euDst }
  };
};
export const getNextSessionOpen = (symbol = '') => {
  const now = new Date();
  const instrClass = _classifySymbol(symbol);
  const windows = _getSessionWindows(instrClass, now);
  const openWindows = windows.filter((w) => w.isOpen);
  if (!openWindows.length) return null;
  const utcH = now.getUTCHours() + now.getUTCMinutes() / 60;
  let nearest = null;
  for (const w of openWindows) {
    if (w.open > utcH && (!nearest || w.open < nearest)) {
      nearest = w.open;
    }
  }
  if (nearest === null) return null;
  const next = new Date(now);
  next.setUTCHours(Math.floor(nearest), Math.round(nearest % 1 * 60), 0, 0);
  return next.toISOString();
};
export const getSessionTimes = (symbol = '') => {
  const now = new Date();
  const usDst = _isUsDst(now);
  const euDst = _isEuDst(now);
  const nyOff = usDst ? 4 : 5;
  const euOff = euDst ? 1 : 2;
  return {
    ASIA: { start: '00:00 UTC', end: '09:00 UTC', note: 'Tokyo/Sydney' },
    LONDON: { start: `${8 - euOff + 1}:00 UTC`, end: `${17 - euOff + 1}:00 UTC`, note: `EU DST: ${euDst ? 'active (CEST/BST)' : 'inactive (CET/GMT)'}` },
    NY: { start: `${9 + (5 - nyOff)}:30 UTC`, end: `${21 + (5 - nyOff)}:00 UTC`, note: `US DST: ${usDst ? 'active (EDT)' : 'inactive (EST)'}` },
    OVERLAP: { start: `${13 + (5 - nyOff)}:30 UTC`, end: `${16 + (5 - nyOff)}:30 UTC`, description: 'London + NY' }
  };
};