const { useState, useEffect, useRef, useCallback, useMemo } = React;
const DEFAULT_DOM_CONFIG = {
  levels: 40,
  updateInterval: 100,
  scaleMode: 'linear',
  cumulative: false,
  minVolumeFilter: 0,
  compact: false,
  showVolumes: true,
  bidColor: '#0ea371',
  askColor: '#e03535',
  bgColor: '#0c0c0c',
  spoofColor: '#f59e0b',
  midpointColor: '#f59e0b',
  textColor: '#d4dde8',
  rowBgEven: '#111111',
  volumeHeatmap: true,
  highlightLargeOrders: true,
  rowHeight: 20,
  spoofingEnabled: true,
  spoofingSensitivity: 0.5,
  showGhosts: true,
  showRowHighlight: true,
  showActivityFlash: true
};
const STORAGE_KEY = 'dom_panel_config_v2';
function loadStoredConfig() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    return raw ? { ...DEFAULT_DOM_CONFIG, ...JSON.parse(raw) } : { ...DEFAULT_DOM_CONFIG };
  } catch {
    return { ...DEFAULT_DOM_CONFIG };
  }
}
const S = {
  panel: {
    display: 'flex',
    flexDirection: 'column',
    height: '100%',
    background: '#0c0c0c',
    borderLeft: '1px solid #1c1c1c',
    position: 'relative',
    overflow: 'hidden',
    fontFamily: "'Inter', sans-serif"
  },
  toolbar: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    padding: '0 8px',
    height: 28,
    minHeight: 28,
    background: '#111111',
    borderBottom: '1px solid #1c1c1c',
    fontSize: 11,
    flexShrink: 0
  },
  toolbarLeft: { display: 'flex', alignItems: 'center', gap: 6 },
  toolbarRight: { display: 'flex', gap: 2 },
  iconBtn: {
    background: 'none',
    border: 'none',
    cursor: 'pointer',
    fontSize: 12,
    padding: '0 4px',
    lineHeight: '28px'
  },
  canvas: { flex: 1, position: 'relative', overflow: 'hidden', minHeight: 0 },
  popover: {
    position: 'absolute',
    top: 30,
    right: 4,
    zIndex: 200,
    background: '#131313',
    border: '1px solid #2a2a2a',
    borderRadius: 6,
    padding: '10px 12px',
    width: 224,
    maxHeight: 'calc(100% - 40px)',
    overflowY: 'auto',
    boxShadow: '0 12px 40px rgba(0,0,0,0.7)',
    fontSize: 11,
    color: '#d4dde8'
  },
  label: { color: '#4a5568', fontSize: 10, textTransform: 'uppercase', letterSpacing: '0.06em', display: 'block', marginBottom: 2 },
  section: { color: '#f59e0b', fontSize: 9, fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.08em', marginBottom: 4 },
  range: { width: '100%', accentColor: '#f59e0b', marginTop: 2, display: 'block' },
  select: {
    width: '100%',
    background: '#0c0c0c',
    border: '1px solid #2a2a2a',
    color: '#d4dde8',
    borderRadius: 3,
    padding: '3px 6px',
    fontSize: 11,
    marginTop: 2
  },
  checkRow: { display: 'flex', alignItems: 'center', gap: 6, cursor: 'pointer', fontSize: 11, userSelect: 'none' },
  divider: { borderTop: '1px solid #1e1e1e', paddingTop: 8, marginTop: 8 },
  colorRow: { display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 6 },
  colorSwatch: { width: 28, height: 18, padding: 0, border: '1px solid #333', background: 'none', cursor: 'pointer', borderRadius: 2 },
  resetBtn: {
    marginTop: 6,
    padding: '3px 8px',
    fontSize: 10,
    background: '#1a1a1a',
    border: '1px solid #333',
    color: '#6b7280',
    borderRadius: 3,
    cursor: 'pointer',
    width: '100%'
  },
  fieldWrap: { marginBottom: 8 }
};
const SettingsPanel = React.memo(({ config, onChange }) => {
  const chk = (key) => (e) => onChange(key, e.target.checked);
  const num = (key, parse = parseInt) => (e) => onChange(key, parse(e.target.value));
  const color = (key) => (e) => onChange(key, e.target.value);
  const scaleBtn = (mode) => ({
    onClick: () => onChange('scaleMode', mode),
    style: {
      flex: 1,
      padding: '3px 0',
      fontSize: 10,
      border: '1px solid #2a2a2a',
      borderRadius: 3,
      cursor: 'pointer',
      background: config.scaleMode === mode ? '#f59e0b' : '#0c0c0c',
      color: config.scaleMode === mode ? '#000' : '#d4dde8'
    }
  });
  const CheckBox = ({ k, label }) =>
  React.createElement('label', { style: S.checkRow },
  React.createElement('input', {
    type: 'checkbox',
    checked: !!config[k],
    onChange: chk(k),
    style: { accentColor: '#f59e0b' }
  }),
  label
  );
  const ColorRow = ({ k, label, fallback }) =>
  React.createElement('div', { style: S.colorRow },
  React.createElement('span', { style: S.label }, label),
  React.createElement('input', {
    type: 'color',
    value: config[k] && config[k].startsWith('#') ? config[k] : fallback || '#ffffff',
    onChange: color(k),
    style: S.colorSwatch
  })
  );
  return React.createElement('div', { style: S.popover },
  React.createElement('div', { style: S.fieldWrap },
  React.createElement('span', { style: S.label }, `Levels  ${config.levels}`),
  React.createElement('input', {
    type: 'range', min: 5, max: 200, step: 5,
    value: config.levels,
    onChange: num('levels'),
    style: S.range
  })
  ),
  React.createElement('div', { style: S.fieldWrap },
  React.createElement('span', { style: S.label }, 'Refresh'),
  React.createElement('select', {
    value: config.updateInterval,
    onChange: num('updateInterval'),
    style: S.select
  },
  React.createElement('option', { value: 50 }, '50ms — Extreme'),
  React.createElement('option', { value: 100 }, '100ms — Fluid'),
  React.createElement('option', { value: 250 }, '250ms — Balanced'),
  React.createElement('option', { value: 500 }, '500ms — Default'),
  React.createElement('option', { value: 1000 }, '1000ms — Slow')
  )
  ),
  React.createElement('div', { style: S.fieldWrap },
  React.createElement('span', { style: S.label }, 'Scale'),
  React.createElement('div', { style: { display: 'flex', gap: 4, marginTop: 2 } },
  React.createElement('button', scaleBtn('linear'), 'Linear'),
  React.createElement('button', scaleBtn('logarithmic'), 'Log')
  )
  ),
  React.createElement('div', { style: S.divider },
  React.createElement('span', { style: S.section }, 'Detection'),
  React.createElement('div', { style: { display: 'flex', flexDirection: 'column', gap: 6 } },
  React.createElement(CheckBox, { k: 'spoofingEnabled', label: 'Detect Spoofing' }),
  React.createElement(CheckBox, { k: 'showGhosts', label: 'Show Order Ghosts' }),
  React.createElement(CheckBox, { k: 'volumeHeatmap', label: 'Volume Heatmap' }),
  React.createElement(CheckBox, { k: 'highlightLargeOrders', label: 'Large Order Alerts' })
  )
  ),
  config.spoofingEnabled && React.createElement('div', { style: { marginTop: 8 } },
  React.createElement('span', { style: S.label }, `Sensitivity  ${config.spoofingSensitivity}`),
  React.createElement('input', {
    type: 'range', min: 0.1, max: 1.0, step: 0.05,
    value: config.spoofingSensitivity,
    onChange: num('spoofingSensitivity', parseFloat),
    style: S.range
  })
  ),
  React.createElement('div', { style: S.divider },
  React.createElement('span', { style: S.section }, 'Display'),
  React.createElement('div', { style: { display: 'flex', flexDirection: 'column', gap: 6 } },
  React.createElement(CheckBox, { k: 'cumulative', label: 'Cumulative Mode' }),
  React.createElement(CheckBox, { k: 'compact', label: 'Compact Rows' }),
  React.createElement(CheckBox, { k: 'showVolumes', label: 'Show Volumes' }),
  React.createElement(CheckBox, { k: 'showRowHighlight', label: 'Row Highlight' }),
  React.createElement(CheckBox, { k: 'showActivityFlash', label: 'Activity Flash' })
  )
  ),
  React.createElement('div', { style: S.divider },
  React.createElement('span', { style: S.section }, 'Colours'),
  React.createElement(ColorRow, { k: 'bidColor', label: 'Bid', fallback: '#0ea371' }),
  React.createElement(ColorRow, { k: 'askColor', label: 'Ask', fallback: '#e03535' }),
  React.createElement(ColorRow, { k: 'bgColor', label: 'Background', fallback: '#0c0c0c' }),
  React.createElement(ColorRow, { k: 'midpointColor', label: 'Spread', fallback: '#f59e0b' }),
  React.createElement(ColorRow, { k: 'spoofColor', label: 'Spoof Ghost', fallback: '#f59e0b' }),
  React.createElement(ColorRow, { k: 'textColor', label: 'Text', fallback: '#d4dde8' }),
  React.createElement('button', {
    onClick: () => {
      const keys = ['bidColor', 'askColor', 'bgColor', 'midpointColor', 'spoofColor', 'textColor', 'rowBgEven'];
      keys.forEach((k) => onChange(k, DEFAULT_DOM_CONFIG[k]));
    },
    style: S.resetBtn
  }, 'Reset Colours')
  )
  );
});
const DOMPanel = ({ symbol, onClose, width, externalConfig }) => {
  const [domData, setDomData] = useState(null);
  const [error, setError] = useState(null);
  const [statusInfo, setStatusInfo] = useState(null);
  const [isLoading, setIsLoading] = useState(true);
  const [showSettings, setShowSettings] = useState(false);
  const [config, setConfig] = useState(loadStoredConfig);
  const canvasRef = useRef(null);
  const engineRef = useRef(null);
  const rendererRef = useRef(null);
  const prevSymbolRef = useRef(symbol);
  const lastRenderTsRef = useRef(0);
  useEffect(() => {
    try {localStorage.setItem(STORAGE_KEY, JSON.stringify(config));} catch {}
  }, [config]);
  useEffect(() => {
    if (!externalConfig || typeof externalConfig !== 'object') return;
    setConfig((prev) => {
      const next = { ...prev };
      const take = (src, dst) => {if (externalConfig[src] != null) next[dst ?? src] = externalConfig[src];};
      take('levels');
      take('scaleMode');
      take('bidColor');
      take('askColor');
      take('bgColor');
      take('rowBgEven');
      take('spoofColor');
      take('midpointColor');
      take('textColor');
      take('showRowHighlight');
      take('showLabels', 'showVolumes');
      return next;
    });
  }, [externalConfig]);
  useEffect(() => {
    if (!canvasRef.current) return;
    if (!engineRef.current && window.DOMEngine) {
      engineRef.current = new window.DOMEngine();
    }
    if (!rendererRef.current && window.DOMRenderer) {
      rendererRef.current = new window.DOMRenderer(canvasRef.current);
    }
    return () => {
      rendererRef.current?.destroy();
      rendererRef.current = null;
      engineRef.current = null;
    };
  }, []);
  useEffect(() => {
    engineRef.current?.setScaleMode(config.scaleMode);
    engineRef.current?.setCumulative(config.cumulative);
    engineRef.current?.setMinVolumeFilter(config.minVolumeFilter);
    engineRef.current?.setSpoofConfig({
      enabled: config.spoofingEnabled,
      sensitivity: config.spoofingSensitivity
    });
    rendererRef.current?.setConfig({
      compact: config.compact,
      showVolumes: config.showVolumes,
      bidColor: config.bidColor,
      askColor: config.askColor,
      bgColor: config.bgColor,
      volumeHeatmap: config.volumeHeatmap,
      highlightLargeOrders: config.highlightLargeOrders,
      rowHeight: config.compact ? 16 : config.rowHeight || 20,
      showSpoofingAlerts: config.spoofingEnabled,
      showGhosts: config.showGhosts,
      spoofColor: config.spoofColor,
      showRowHighlight: config.showRowHighlight,
      showActivityFlash: config.showActivityFlash,
      midpointColor: config.midpointColor,
      textColor: config.textColor,
      rowBgEven: config.rowBgEven
    });
  }, [config]);
  useEffect(() => {
    if (!symbol) return;

    // Force an initial render to avoid blank canvas on mount
    rendererRef.current?.render({ bids: [], asks: [], symbol });

    if (prevSymbolRef.current !== symbol) {
      setDomData(null);
      setIsLoading(true);
      setError(null);
      setStatusInfo(null);
      lastRenderTsRef.current = 0;
      rendererRef.current?.render({ bids: [], asks: [], symbol });
      prevSymbolRef.current = symbol;
    }
    const handleUpdate = (e) => {
      const data = e.detail;
      if (!data) return;
      const norm = (s) => window.getUniversalSymbol ? window.getUniversalSymbol(s) : s;
      const dataSym = norm(data.symbol);
      const targetSym = norm(symbol);
      
      // console.log(`[DOM_PANEL] Event for ${data.symbol} (norm: ${dataSym}) vs Target ${symbol} (norm: ${targetSym})`);
      
      if (dataSym !== targetSym && data.symbol !== symbol) return;
      
      const now = Date.now();
      if (now - lastRenderTsRef.current < config.updateInterval) return;
      lastRenderTsRef.current = now;
      setError(null);
      setStatusInfo(null);
      setIsLoading(false);
      if (!engineRef.current) return;
      const processed = engineRef.current.processSnapshot(data);
      if (!processed) {
        // console.warn("[DOM_PANEL] Engine returned null for snapshot");
        return;
      }
      // console.log("[DOM_PANEL] Snapshot processed, rendering...", {
      //   bids: processed.bids?.length,
      //   asks: processed.asks?.length
      // });
      rendererRef.current?.render(processed);
      setDomData(processed);
    };
    window.addEventListener('market_dom', handleUpdate);
    const ctrl = new AbortController();
    (async () => {
      try {
        const res = await fetch(
          `/api/v2/feed/dom/${encodeURIComponent(symbol)}?levels=${config.levels}`,
          { signal: ctrl.signal }
        );
        if (!res.ok) {
           setError(`HTTP ${res.status}: Failed to load DOM`);
           setIsLoading(false);
           return;
        }
        const data = await res.json();
        if (!engineRef.current) return;
        const processed = engineRef.current.processSnapshot(data);
        if (!processed) {
           setError('No DOM data received');
           setIsLoading(false);
           return;
        }
        rendererRef.current?.render(processed);
        setDomData(processed);
        setIsLoading(false);
        lastRenderTsRef.current = Date.now();
      } catch (err) {
        if (err.name !== 'AbortError') {
          console.error('[DOM] Fetch error:', err);
          setError(err.message || 'Failed to connect to feed');
          setIsLoading(false);
        }
      }
    })();
    return () => {
      window.removeEventListener('market_dom', handleUpdate);
      ctrl.abort();
    };
  }, [symbol, config.levels, config.updateInterval]);
  const handleCfg = useCallback((key, value) => {
    setConfig((prev) => ({ ...prev, [key]: value }));
  }, []);
  const dotColor = useMemo(() => {
    if (error) return '#e03535';
    if (isLoading || statusInfo) return '#f59e0b';
    return '#0ea371';
  }, [error, isLoading, statusInfo]);
  return React.createElement('div', { style: { ...S.panel, width: width || '100%' } },
  React.createElement('div', { style: S.toolbar },
  React.createElement('div', { style: S.toolbarLeft },
  React.createElement('i', { className: 'fas fa-layer-group', style: { color: '#f59e0b', fontSize: 10 } }),
  React.createElement('span', {
    style: { color: '#d4dde8', fontWeight: 600, fontSize: 11, letterSpacing: '0.04em' }
  }, 'DOM'),
  React.createElement('div', {
    style: {
      width: 6, height: 6, borderRadius: '50%',
      background: dotColor,
      boxShadow: `0 0 5px ${dotColor}88`,
      flexShrink: 0
    }
  })
  ),
  React.createElement('div', { style: S.toolbarRight },
  React.createElement('button', {
    onClick: () => setShowSettings((s) => !s),
    title: 'DOM Settings',
    style: { ...S.iconBtn, color: showSettings ? '#f59e0b' : '#3d4f5f' }
  }, React.createElement('i', { className: 'fas fa-cog' })),
  onClose && React.createElement('button', {
    onClick: onClose,
    title: 'Close DOM',
    style: { ...S.iconBtn, color: '#3d4f5f' }
  }, React.createElement('i', { className: 'fas fa-times' }))
  )
  ),
  showSettings && React.createElement(SettingsPanel, {
    config: config,
    onChange: handleCfg
  }),
  React.createElement('div', { ref: canvasRef, style: S.canvas }),
  (error || statusInfo) && React.createElement('div', {
    style: {
      position: 'absolute',
      bottom: 32,
      left: 0,
      right: 0,
      textAlign: 'center',
      padding: '4px 8px',
      background: error ? 'rgba(224,53,53,0.12)' : 'rgba(245,158,11,0.12)',
      color: error ? '#e03535' : '#f59e0b',
      fontSize: 10,
      fontFamily: "'JetBrains Mono', monospace",
      pointerEvents: 'none'
    }
  }, error || statusInfo)
  );
};
window.DOMPanel = DOMPanel;
