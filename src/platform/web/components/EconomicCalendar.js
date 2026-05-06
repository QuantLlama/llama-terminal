const EconomicCalendar = ({ isOpen, onClose }) => {
  const [events, setEvents] = React.useState([]);
  const [loading, setLoading] = React.useState(true);
  const [filters, setFilters] = React.useState(() => {
    const stored = localStorage.getItem('calendar_filters');
    const defaults = {
      High: true, Medium: true, Low: false,
      markets: { cfd: true, futures: true, crypto: true }
    };
    if (!stored) return defaults;
    try {
      const parsed = JSON.parse(stored);
      return {
        ...defaults,
        ...parsed,
        markets: { ...defaults.markets, ...(parsed.markets || {}) }
      };
    } catch (e) {
      return defaults;
    }
  });
  const [selectedCountries, setSelectedCountries] = React.useState(() => {
    const stored = localStorage.getItem('calendar_countries');
    return stored ? JSON.parse(stored) : ['USD'];
  });
  const [isSquawkEnabled, setIsSquawkEnabled] = React.useState(() => localStorage.getItem('squawk_enabled') === 'true');
  const [refreshing, setRefreshing] = React.useState(false);
  const [activeTab, setActiveTab] = React.useState('upcoming');
  const [timeFilter, setTimeFilter] = React.useState('week');
  const [showSettings, setShowSettings] = React.useState(false);
  const [squawkSettings, setSquawkSettings] = React.useState(() => {
    const stored = localStorage.getItem('squawk_settings');
    return stored ? JSON.parse(stored) : { voice: '', rate: 1.0, lang: 'es-ES' };
  });
  const [mainTab, setMainTab] = React.useState('calendar');
  const [news, setNews] = React.useState([]);
  const [newsLoading, setNewsLoading] = React.useState(false);
  const [newsToken, setNewsToken] = React.useState(() => localStorage.getItem('news_api_token') || 'KGhpJvRn6fmBsY51HkDkiYNrVhXkpriXAJUSHvzg');
  const [translatedNews, setTranslatedNews] = React.useState(new Set());
  const [newsFilters, setNewsFilters] = React.useState(() => {
    const stored = localStorage.getItem('news_filters');
    return stored ? JSON.parse(stored) : { minSentiment: -1.0, symbols: '', language: 'en' };
  });
  const announcedStages = React.useRef(new Map());

  // --- Dragging Logic ---
  const width = 820;
  const height = 580;
  const clampPos = (p) => {
    if (typeof window === 'undefined') return p;
    const maxX = Math.max(0, window.innerWidth - width);
    const maxY = Math.max(0, window.innerHeight - 50);
    return { x: Math.min(Math.max(0, p.x), maxX), y: Math.min(Math.max(0, p.y), maxY) };
  };
  const [pos, setPos] = React.useState(() => {
    if (typeof window === 'undefined') return { x: 100, y: 100 };
    const defaultPos = {
      x: Math.max(24, (window.innerWidth - width) / 2),
      y: Math.max(24, (window.innerHeight - height) / 2)
    };
    try {
      const saved = localStorage.getItem('calendar_modal_pos');
      if (saved) return clampPos(JSON.parse(saved));
    } catch (e) { }
    return clampPos(defaultPos);
  });
  const [dragging, setDragging] = React.useState(false);
  const dragRef = React.useRef(null);
  const offsetRef = React.useRef({ x: 0, y: 0 });
  const initializedRef = React.useRef(false);

  React.useLayoutEffect(() => {
    if (!isOpen) return;
    if (initializedRef.current) return;
    try {
      const saved = localStorage.getItem('calendar_modal_pos');
      if (saved) {
        setPos(clampPos(JSON.parse(saved)));
        initializedRef.current = true;
        return;
      }
    } catch (e) { }
    setPos(clampPos({
      x: Math.max(24, (window.innerWidth - width) / 2),
      y: Math.max(24, (window.innerHeight - height) / 2)
    }));
    initializedRef.current = true;
  }, [isOpen]);

  const handleMouseDown = (e) => {
    if (!e.target.closest('.drag-handle')) return;
    const targetTag = e.target.tagName.toLowerCase();
    if (targetTag !== 'button' && targetTag !== 'input' && targetTag !== 'textarea') {
      e.preventDefault();
    }
    setDragging(true);
    const rect = dragRef.current.getBoundingClientRect();
    offsetRef.current = { x: e.clientX - rect.left, y: e.clientY - rect.top };
  };

  React.useEffect(() => {
    if (!dragging) return;
    const move = (e) => {
      setPos(clampPos({
        x: e.clientX - offsetRef.current.x,
        y: e.clientY - offsetRef.current.y
      }));
    };
    const stop = () => setDragging(false);
    window.addEventListener('mousemove', move, true);
    window.addEventListener('mouseup', stop, true);
    return () => {
      window.removeEventListener('mousemove', move, true);
      window.removeEventListener('mouseup', stop, true);
    };
  }, [dragging]);

  React.useEffect(() => {
    if (!dragging && initializedRef.current) {
      try { localStorage.setItem('calendar_modal_pos', JSON.stringify(pos)); } catch (e) { }
    }
  }, [dragging, pos]);
  // -----------------------
  const fetchCalendar = async () => {
    try {
      const countriesParam = selectedCountries.join(',');
      const res = await fetch(`/api/calendar?countries=${countriesParam}`);
      const data = await res.json();
      if (data.status === 'success') {
        setEvents(data.events);
      }
    } catch (e) {
      console.error("Failed to fetch calendar", e);
    } finally {
      setLoading(false);
    }
  };
  React.useEffect(() => {
    if (isOpen || isSquawkEnabled) {
      fetchCalendar();
      const interval = setInterval(fetchCalendar, 120000); // 2 min
      return () => clearInterval(interval);
    }
  }, [isOpen, isSquawkEnabled, selectedCountries]);
  const fetchNews = async () => {
    if (!newsToken) return;
    setNewsLoading(true);
    try {
      const baseUrl = 'https://api.marketaux.com/v1/news/all';
      const params = new URLSearchParams({
        api_token: newsToken,
        language: newsFilters.language,
        filter_entities: 'true',
        limit: '10'
      });
      if (newsFilters.symbols) params.append('symbols', newsFilters.symbols);
      if (newsFilters.minSentiment > -1) params.append('min_sentiment', newsFilters.minSentiment);
      const res = await fetch(`${baseUrl}?${params.toString()}`);
      const data = await res.json();
      if (data.data) {
        setNews(data.data);
      }
    } catch (e) {
      console.error("Failed to fetch news", e);
    } finally {
      setNewsLoading(false);
    }
  };

  const handleManualRefresh = async () => {
    setRefreshing(true);
    await Promise.all([fetchCalendar(), fetchNews()]);
    setTimeout(() => setRefreshing(false), 800);
  };
  React.useEffect(() => {
    if (isOpen && mainTab === 'news') {
      fetchNews();
    }
  }, [isOpen, mainTab, newsFilters, newsToken]);
  React.useEffect(() => {
    if (!isSquawkEnabled || events.length === 0) return;
    const checkAndSpeak = () => {
      const now = new Date();
      events.forEach((event) => {
        const eventTime = new Date(event.date);
        const diffSeconds = Math.floor((eventTime - now) / 1000);
        if (!filters[event.impact]) return;
        const isImportant = ['fomc', 'fed ', 'min', 'oil', 'crude', 'natural gas', 'opec', 'inventory'].
          some((k) => event.title.toLowerCase().includes(k));
        const isCrypto = event.country === 'BTC' || event.country === 'ETH';
        const isFutures = ['USD', 'EUR', 'GBP', 'JPY'].includes(event.country) && event.title.toLowerCase().includes('futures') || isImportant;
        const isCFD = !isCrypto && !isFutures;
        if (isCrypto && !filters.markets?.crypto) return;
        if (isFutures && !filters.markets?.futures) return;
        if (isCFD && !filters.markets?.cfd) return;
        
        if (diffSeconds > 0 && diffSeconds <= 240) {
          // console.log(`[SQUAWK] ⏰ Near event: "${event.title}" in ${Math.floor(diffSeconds/60)}m ${diffSeconds%60}s`);
        }
        
        if (!announcedStages.current.has(event.id)) {
          announcedStages.current.set(event.id, new Set());
        }
        const stagesDone = announcedStages.current.get(event.id);
        
        [3, 2, 1].forEach((stage) => {
          const targetSeconds = stage * 60;
          // Robust check: trigger if within a small window and not already done for this stage
          if (diffSeconds > 0 && diffSeconds <= targetSeconds && diffSeconds >= targetSeconds - 10 && !stagesDone.has(stage)) {
            speak(event, stage);
            stagesDone.add(stage);
          }
        });
      });
    };
    const speak = (event, minutesRemaining) => {
      const msg = new SpeechSynthesisUtterance();
      let text = '';
      const impactText = {
        'es-ES': {
          'High': 'impacto alto',
          'Medium': 'impacto medio',
          'Low': 'impacto bajo'
        },
        'en-US': {
          'High': 'high impact',
          'Medium': 'medium impact',
          'Low': 'low impact'
        }
      };
      const impact = impactText[squawkSettings.lang]?.[event.impact] || event.impact;
      if (squawkSettings.lang === 'es-ES') {
        text = `Atención: ${minutesRemaining} ${minutesRemaining === 1 ? 'minuto' : 'minutos'} para ${event.title}, ${impact}`;
      } else {
        text = `Attention: ${minutesRemaining} ${minutesRemaining === 1 ? 'minute' : 'minutes'} for ${event.title}, ${impact}`;
      }
      msg.text = text;
      msg.lang = squawkSettings.lang;
      msg.rate = squawkSettings.rate;
      const voices = window.speechSynthesis.getVoices();
      let selectedVoice = voices.find((v) => v.name === squawkSettings.voice);
      if (!selectedVoice && voices.length > 0) {
        const langPrefix = squawkSettings.lang.slice(0, 2);
        selectedVoice = voices.find((v) => v.lang.startsWith(langPrefix)) || voices[0];
      }
      if (selectedVoice) msg.voice = selectedVoice;
      window.speechSynthesis.speak(msg);
    };
    checkAndSpeak();
    const interval = setInterval(checkAndSpeak, 2000);
    return () => clearInterval(interval);
  }, [events, isSquawkEnabled, filters, squawkSettings]);
  React.useEffect(() => {
    localStorage.setItem('calendar_filters', JSON.stringify(filters));
    localStorage.setItem('squawk_enabled', isSquawkEnabled);
    localStorage.setItem('squawk_settings', JSON.stringify(squawkSettings));
    localStorage.setItem('calendar_countries', JSON.stringify(selectedCountries));
    localStorage.setItem('news_api_token', newsToken);
    localStorage.setItem('news_filters', JSON.stringify(newsFilters));
  }, [filters, isSquawkEnabled, squawkSettings, selectedCountries, newsToken, newsFilters]);
  if (!isOpen) return null;
  const isImportantEvent = (title) => {
    const t = title.toLowerCase();
    const keywords = ['fomc', 'fed ', 'min', 'oil', 'crude', 'natural gas', 'opec', 'inventory'];
    return keywords.some((k) => t.includes(k));
  };
  const filteredEvents = events.filter((e) => {
    if (!filters[e.impact]) return false;
    const isCrypto = e.country === 'BTC' || e.country === 'ETH';
    const isImportant = isImportantEvent(e.title);
    const isFutures = ['USD', 'EUR', 'GBP', 'JPY'].includes(e.country) && e.title.toLowerCase().includes('futures') || isImportant;
    const isCFD = !isCrypto && !isFutures;
    if (isCrypto && !filters.markets?.crypto) return false;
    if (isFutures && !filters.markets?.futures) return false;
    if (isCFD && !filters.markets?.cfd) return false;
    return true;
  });
  return (
    React.createElement("div", { className: "fixed inset-0 z-[9999] pointer-events-none overflow-hidden font-sans" },
      React.createElement("div", {
        ref: dragRef,
        onMouseDown: handleMouseDown,
        style: { position: 'absolute', left: `${pos.x}px`, top: `${pos.y}px`, width: '820px', height: '580px' },
        className: "pointer-events-auto bg-panel border border-border rounded-xl shadow-2xl flex flex-col overflow-hidden animate-in fade-in zoom-in duration-200"
      },
        React.createElement("div", { className: "drag-handle cursor-move h-12 border-b border-border bg-black/20 flex items-center justify-between px-6 flex-shrink-0" },
          React.createElement("div", { className: "flex items-center gap-3" },
            React.createElement("div", { className: "flex bg-white/5 rounded-lg p-1 border border-white/5" },
              React.createElement("button", {
                onClick: () => setMainTab('calendar'),
                className: `px-3 py-1 text-[10px] font-bold rounded-md transition-all ${mainTab === 'calendar' ? 'bg-accent text-black' : 'text-muted hover:text-white'}`
              },
                React.createElement("i", { className: "fas fa-calendar-alt mr-2" }), " CALENDAR"
              ),
              React.createElement("button", {
                onClick: () => setMainTab('news'),
                className: `px-3 py-1 text-[10px] font-bold rounded-md transition-all ${mainTab === 'news' ? 'bg-accent text-black' : 'text-muted hover:text-white'}`
              },
                React.createElement("i", { className: "fas fa-newspaper mr-2" }), " NEWS"
              )
            ),
            React.createElement("div", { className: "w-[1px] h-4 bg-white/10 mx-2" }),
            React.createElement("button", {
              onClick: handleManualRefresh,
              className: `p-2 text-muted hover:text-accent transition-all ${refreshing ? 'pointer-events-none' : ''}`,
              title: "Refrescar datos"
            },
              React.createElement("i", { className: `fas fa-sync-alt ${refreshing ? 'fa-spin' : ''} text-[12px]` })
            ),
            React.createElement("div", { className: "w-[1px] h-4 bg-white/10 mx-2" }),
            mainTab === 'calendar' ?
              React.createElement("div", { className: "flex bg-white/5 rounded p-0.5 border border-white/5" },
                React.createElement("button", {
                  onClick: () => setTimeFilter('day'),
                  className: `px-2 py-0.5 text-[8px] font-bold rounded transition-colors ${timeFilter === 'day' ? 'bg-accent/20 text-accent' : 'text-muted hover:text-white'}`
                },
                  "TODAY"
                ),
                React.createElement("button", {
                  onClick: () => setTimeFilter('week'),
                  className: `px-2 py-0.5 text-[8px] font-bold rounded transition-colors ${timeFilter === 'week' ? 'bg-accent/20 text-accent' : 'text-muted hover:text-white'}`
                },
                  "WEEK"
                )
              ) :
              React.createElement("button", {
                onClick: fetchNews,
                className: "p-1 px-3 bg-white/5 rounded border border-white/5 text-[8px] font-bold text-muted hover:text-white hover:bg-white/10 transition-all"
              },
                React.createElement("i", { className: `fas fa-sync-alt mr-1 ${newsLoading ? 'animate-spin' : ''}` }), " REFRESH NEWS"
              )
          ),
          React.createElement("div", { className: "flex items-center gap-2" },
            React.createElement("button", {
              onClick: () => setIsSquawkEnabled(!isSquawkEnabled),
              className: `p-1.5 rounded transition-colors ${isSquawkEnabled ? 'text-accent' : 'text-muted hover:text-white'}`,
              title: isSquawkEnabled ? "Squawk Active" : "Squawk Muted"
            },
              React.createElement("i", { className: `fas ${isSquawkEnabled ? 'fa-volume-up' : 'fa-volume-mute'} text-xs` })
            ),
            React.createElement("button", {
              onClick: () => setShowSettings(!showSettings),
              className: `p-1.5 rounded transition-colors ${showSettings ? 'text-accent' : 'text-muted hover:text-white'}`
            },
              React.createElement("i", { className: "fas fa-cog text-xs" })
            ),
            React.createElement("div", { className: "w-[1px] h-4 bg-white/10 mx-1" }),
            React.createElement("button", { onClick: onClose, className: "p-1.5 text-muted hover:text-white transition-colors" },
              React.createElement("i", { className: "fas fa-times text-xs" })
            )
          )
        ),
        !showSettings && mainTab === 'calendar' &&
        React.createElement("div", { className: "flex border-b border-white/10 bg-white/5 text-[10px] font-bold uppercase tracking-widest flex-shrink-0" },
          React.createElement("button", {
            onClick: () => setActiveTab('upcoming'),
            className: `flex-1 py-3 transition-colors ${activeTab === 'upcoming' ? 'text-accent border-b-2 border-accent bg-white/5' : 'text-gray-400 hover:text-white hover:bg-white/5'}`
          },
            "Upcoming"
          ),
          React.createElement("button", {
            onClick: () => setActiveTab('completed'),
            className: `flex-1 py-3 transition-colors ${activeTab === 'completed' ? 'text-accent border-b-2 border-accent bg-white/5' : 'text-gray-400 hover:text-white hover:bg-white/5'}`
          },
            "Completed"
          )
        ),
        React.createElement("div", { className: "flex-1 overflow-hidden p-0 flex flex-col" },
          showSettings ?
            React.createElement("div", { className: "flex-1 flex flex-col p-6 animate-in slide-in-from-top-2 duration-300" },
              React.createElement("div", { className: "flex-1 grid grid-cols-2 gap-x-8 gap-y-6 overflow-hidden" },
                React.createElement("div", { className: "space-y-6" },
                  React.createElement("section", null,
                    React.createElement("h3", { className: "text-[9px] font-bold text-muted uppercase tracking-[0.2em] mb-3" }, "Market Focus"),
                    React.createElement("div", { className: "grid grid-cols-3 gap-2" },
                      [
                        { id: 'cfd', label: 'CFD/FX', icon: 'fa-exchange-alt' },
                        { id: 'futures', label: 'FUTURES', icon: 'fa-chart-bar' },
                        { id: 'crypto', label: 'CRYPTO', icon: 'fab fa-bitcoin' }].
                        map((market) =>
                          React.createElement("button", {
                            key: market.id,
                            onClick: () => setFilters({
                              ...filters,
                              markets: { ...filters.markets, [market.id]: !filters.markets[market.id] }
                            }),
                            className: `py-2 px-1 rounded border text-[8px] font-bold flex flex-col items-center gap-1 transition-all ${filters.markets?.[market.id] ?
                              'bg-accent/10 border-accent/20 text-accent' :
                              'bg-white/5 border-white/5 text-muted grayscale opacity-60'}`
                          },
                            React.createElement("i", { className: `fas ${market.icon} text-[10px]` }),
                            market.label
                          )
                        )
                    )
                  ),
                  React.createElement("section", null,
                    React.createElement("h3", { className: "text-[9px] font-bold text-muted uppercase tracking-[0.2em] mb-3" }, "Priority / Impact"),
                    React.createElement("div", { className: "grid grid-cols-3 gap-2" },
                      ['High', 'Medium', 'Low'].map((imp) =>
                        React.createElement("button", {
                          key: imp,
                          onClick: () => setFilters({ ...filters, [imp]: !filters[imp] }),
                          className: `py-2 px-1 rounded border text-[8px] font-bold flex flex-col items-center gap-1 transition-all ${filters[imp] ?
                            'bg-accent/10 border-accent/20 text-accent' :
                            'bg-white/5 border-white/5 text-muted grayscale opacity-60'}`
                        },
                          React.createElement("div", { className: `w-1.5 h-1.5 rounded-full ${imp === 'High' ? 'bg-red-500 shadow-[0_0_5px_rgba(239,68,68,0.5)]' : imp === 'Medium' ? 'bg-orange-500' : 'bg-yellow-500'}` }),
                          imp
                        )
                      )
                    )
                  ),
                  React.createElement("section", null,
                    React.createElement("h3", { className: "text-[9px] font-bold text-muted uppercase tracking-[0.2em] mb-3" }, "Audio (Squawk)"),
                    React.createElement("div", { className: "grid grid-cols-1 gap-4 bg-white/5 p-3 rounded-lg border border-white/5" },
                      React.createElement("div", { className: "flex items-center justify-between" },
                        React.createElement("label", { className: "text-[9px] text-muted font-bold" }, "LANGUAGE"),
                        React.createElement("select", {
                          value: squawkSettings.lang,
                          onChange: (e) => setSquawkSettings({ ...squawkSettings, lang: e.target.value }),
                          className: "bg-black border border-white/10 rounded px-2 py-1 text-[9px] text-white outline-none focus:border-accent/40"
                        },
                          React.createElement("option", { value: "es-ES" }, "Spanish (ES)"),
                          React.createElement("option", { value: "en-US" }, "English (US)")
                        )
                      ),
                      React.createElement("div", { className: "flex items-center justify-between gap-4" },
                        React.createElement("label", { className: "text-[9px] text-muted font-bold shrink-0" }, "SPEED"),
                        React.createElement("input", {
                          type: "range", min: "0.5", max: "2", step: "0.1",
                          value: squawkSettings.rate,
                          onChange: (e) => setSquawkSettings({ ...squawkSettings, rate: parseFloat(e.target.value) }),
                          className: "w-full h-1 bg-white/10 rounded-lg appearance-none cursor-pointer accent-accent"
                        }
                        )
                      )
                    )
                  )
                ),
                React.createElement("div", { className: "space-y-6 overflow-y-auto custom-scrollbar pr-2" },
                  React.createElement("section", null,
                    React.createElement("h3", { className: "text-[9px] font-bold text-muted uppercase tracking-[0.2em] mb-3" }, "Regions / Countries"),
                    React.createElement("div", { className: "grid grid-cols-4 gap-2" },
                      [
                        { code: 'USD', label: 'USA', flag: '🇺🇸' },
                        { code: 'EUR', label: 'EU', flag: '🇪🇺' },
                        { code: 'GBP', label: 'UK', flag: '🇬🇧' },
                        { code: 'JPY', label: 'JP', flag: '🇯🇵' },
                        { code: 'CAD', label: 'CA', flag: '🇨🇦' },
                        { code: 'AUD', label: 'AU', flag: '🇦🇺' },
                        { code: 'CHF', label: 'CH', flag: '🇨🇭' },
                        { code: 'NZD', label: 'NZ', flag: '🇳🇿' }].
                        map((country) =>
                          React.createElement("button", {
                            key: country.code,
                            onClick: () => {
                              if (selectedCountries.includes(country.code)) {
                                setSelectedCountries(selectedCountries.filter((c) => c !== country.code));
                              } else {
                                setSelectedCountries([...selectedCountries, country.code]);
                              }
                            },
                            className: `p-1.5 rounded-lg border text-[8px] font-bold flex flex-col items-center gap-1 transition-all ${selectedCountries.includes(country.code) ?
                              'bg-accent/10 border-accent/20 text-accent' :
                              'bg-white/5 border-white/5 text-muted grayscale opacity-60'}`
                          },
                            React.createElement("span", { className: "text-sm" }, country.flag),
                            country.label
                          )
                        )
                    )
                  ),
                  React.createElement("section", { className: "bg-white/5 p-4 rounded-xl border border-white/10 space-y-4" },
                    React.createElement("h3", { className: "text-[9px] font-bold text-accent uppercase tracking-[0.2em] flex items-center gap-2" },
                      React.createElement("i", { className: "fas fa-key text-[10px]" }), " MarketAux API Config"
                    ),
                    React.createElement("div", { className: "space-y-1.5" },
                      React.createElement("label", { className: "text-[8px] text-muted font-bold uppercase" }, "News API Token"),
                      React.createElement("input", {
                        type: "password",
                        value: newsToken,
                        onChange: (e) => setNewsToken(e.target.value),
                        placeholder: "Enter API Token...",
                        className: "w-full bg-black/40 border border-white/10 rounded px-3 py-2 text-[10px] text-white outline-none focus:border-accent/40 font-mono transition-all"
                      }
                      )
                    ),
                    React.createElement("div", { className: "grid grid-cols-2 gap-4" },
                      React.createElement("div", { className: "space-y-1.5" },
                        React.createElement("label", { className: "text-[8px] text-muted font-bold uppercase" }, "Min Sentiment"),
                        React.createElement("select", {
                          value: newsFilters.minSentiment,
                          onChange: (e) => setNewsFilters({ ...newsFilters, minSentiment: parseFloat(e.target.value) }),
                          className: "w-full bg-black/40 border border-white/10 rounded px-2 py-1.5 text-[10px] text-white outline-none focus:border-accent/40"
                        },
                          React.createElement("option", { value: "-1.0" }, "All News"),
                          React.createElement("option", { value: "0.1" }, "Bullish Only"),
                          React.createElement("option", { value: "-0.1" }, "Bearish Only"),
                          React.createElement("option", { value: "0.5" }, "Strongly Bullish")
                        )
                      ),
                      React.createElement("div", { className: "space-y-1.5" },
                        React.createElement("label", { className: "text-[8px] text-muted font-bold uppercase" }, "Sync Symbols"),
                        React.createElement("input", {
                          type: "text",
                          value: newsFilters.symbols,
                          onChange: (e) => setNewsFilters({ ...newsFilters, symbols: e.target.value }),
                          placeholder: "e.g. AAPL,TSLA",
                          className: "w-full bg-black/40 border border-white/10 rounded px-2 py-1.5 text-[10px] text-white outline-none focus:border-accent/40"
                        }
                        )
                      )
                    )
                  )
                )
              ),
              React.createElement("button", {
                onClick: () => setShowSettings(false),
                className: "w-full mt-6 py-2 bg-accent/10 border border-accent/20 text-accent text-[10px] font-bold rounded hover:bg-accent/20 transition-all active:scale-[0.98]"
              },
                "SAVE CONFIGURATION"
              )
            ) :
            React.createElement("div", { className: "flex-1 overflow-y-auto custom-scrollbar divide-y divide-white/5" },
              mainTab === 'calendar' ?
                loading ?
                  React.createElement("div", { className: "flex flex-col items-center justify-center h-full gap-4" },
                    React.createElement("div", { className: "w-6 h-6 border border-accent/30 border-t-accent rounded-full animate-spin" }),
                    React.createElement("span", { className: "text-[8px] text-muted font-bold tracking-[0.2em] animate-pulse" }, "SYNCING DATA...")
                  ) :
                  (() => {
                    const now = new Date();
                    const displayEvents = filteredEvents.filter((e) => {
                      const eventTime = new Date(e.date);
                      
                      // Utilize backend is_today calculation to bypass Wine JS UTC timezone bug
                      const isSameDay = e.is_today === true;

                      if (timeFilter === 'day' && !isSameDay) {
                        return false;
                      }

                      if (activeTab === 'upcoming') {
                        return eventTime > now;
                      } else {
                        return eventTime <= now;
                      }
                    }).sort((a, b) => {
                      const timeA = new Date(a.date);
                      const timeB = new Date(b.date);
                      if (activeTab === 'upcoming') {
                        return timeA - timeB;
                      }
                      return timeB - timeA;
                    });
                    if (displayEvents.length === 0) {
                      return (
                        React.createElement("div", { className: "flex flex-col items-center justify-center h-full gap-2 text-center p-20" },
                          React.createElement("i", { className: "fas fa-search text-white/5 text-4xl mb-2" }),
                          React.createElement("span", { className: "text-[10px] text-muted font-bold uppercase tracking-wider" }, "No events found")
                        ));
                    }
                    return displayEvents.map((event) => {
                      const showAsCompleted = activeTab === 'completed';
                      
                      const actualColor = event.actual 
                        ? (parseFloat(event.actual) >= parseFloat(event.forecast || 0) ? 'text-green-500/90' : 'text-red-500/90') 
                        : 'text-gray-500';

                      return React.createElement("div", { key: event.id, className: `flex items-center gap-4 px-6 py-3 transition-all group ${showAsCompleted ? 'opacity-40 grayscale hover:opacity-70' : 'hover:bg-white/[0.02]'}` },
                        React.createElement("div", { className: "flex flex-col items-center w-12 shrink-0" },
                          React.createElement("span", { className: "text-[10px] font-mono text-white/90 font-bold" }, new Date(event.date).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })),
                          (() => {
                            const nowSync = new Date();
                            const diff = Math.floor((new Date(event.date) - nowSync) / 60000);
                            return activeTab === 'upcoming' && diff > 0 && diff <= 60 ? React.createElement("span", { className: "text-[8px] font-bold text-accent animate-pulse mt-0.5" }, diff, "m") : null;
                          })()
                        ),
                        React.createElement("div", { className: "flex items-center gap-3 shrink-0" },
                          React.createElement("div", { className: `w-[2px] h-6 rounded-full ${event.impact === 'High' ? 'bg-red-500 shadow-[0_0_8px_rgba(239,68,68,0.4)]' : event.impact === 'Medium' ? 'bg-orange-500' : 'bg-yellow-500'}` }),
                          React.createElement("span", { className: "text-[9px] font-bold text-gray-400 bg-white/5 px-2 py-0.5 rounded border border-white/5 w-10 text-center" }, event.country)
                        ),
                        React.createElement("div", { className: "flex-1 min-w-0" },
                          React.createElement("div", { className: `text-[11px] font-bold text-gray-200 truncate ${showAsCompleted ? 'line-through decoration-red-500/30' : ''}` }, event.title),
                          React.createElement("span", { className: "text-[8px] font-bold text-gray-600 uppercase tracking-widest mt-0.5 block" }, new Date(event.date).toLocaleDateString('en-US', { weekday: 'short', day: 'numeric', month: 'numeric' }))
                        ),
                        React.createElement("div", { className: "flex items-center gap-8 shrink-0 font-mono text-right" },
                          React.createElement("div", { className: "flex flex-col w-12" },
                            React.createElement("span", { className: "text-[8px] text-muted font-bold" }, "ACTUAL"),
                            React.createElement("span", { className: `text-[10px] font-bold ${actualColor}` }, event.actual ? `${event.actual}${event.unit || ''}` : '-')
                          ),
                          React.createElement("div", { className: "flex flex-col w-12 border-l border-white/5 pl-4" },
                            React.createElement("span", { className: "text-[8px] text-muted font-bold" }, "FORECAST"),
                            React.createElement("span", { className: "text-[10px] text-gray-500 font-bold" }, event.forecast ? `${event.forecast}${event.unit || ''}` : '-')
                          )
                        )
                      );
                    });
                  })() :
                newsLoading ?
                  React.createElement("div", { className: "flex flex-col items-center justify-center h-full gap-4" },
                    React.createElement("div", { className: "w-6 h-6 border border-accent/30 border-t-accent rounded-full animate-spin" }),
                    React.createElement("span", { className: "text-[8px] text-muted font-bold tracking-[0.2em] animate-pulse" }, "LOADING NEWS...")
                  ) :
                  React.createElement("div", { className: "flex flex-col divide-y divide-white/[0.03]" },
                    news.length > 0 ? news.map((item) => {
                      const isTranslated = translatedNews.has(item.uuid);
                      const sentiment = item.entities?.[0]?.sentiment_score || 0;
                      const displayTitle = isTranslated ? `[ES] ${item.title}` : item.title;
                      const displayDesc = isTranslated ? `Contenido traducido: ${item.description}` : item.description;
                      return (
                        React.createElement("div", { key: item.uuid, className: "p-5 hover:bg-white/[0.03] transition-all group relative overflow-hidden" },
                          React.createElement("div", { className: `absolute top-0 right-0 w-32 h-32 blur-[60px] opacity-10 transition-all ${sentiment > 0 ? 'bg-green-500' : sentiment < 0 ? 'bg-red-500' : 'bg-blue-500'}` }),
                          React.createElement("div", { className: "flex gap-5 relative z-10" },
                            item.image_url &&
                            React.createElement("div", { className: "w-28 h-20 rounded-lg overflow-hidden flex-shrink-0 bg-black/40 border border-white/5 shadow-inner" },
                              React.createElement("img", {
                                src: item.image_url,
                                alt: "",
                                className: "w-full h-full object-cover grayscale group-hover:grayscale-0 transition-all duration-500 scale-105 group-hover:scale-100"
                              }
                              )
                            ),
                            React.createElement("div", { className: "flex-1 min-w-0" },
                              React.createElement("div", { className: "flex items-center justify-between mb-2" },
                                React.createElement("div", { className: "flex items-center gap-2" },
                                  React.createElement("span", { className: "px-2 py-0.5 bg-accent/10 border border-accent/20 rounded text-[7px] font-bold text-accent uppercase tracking-wider" },
                                    item.source
                                  ),
                                  React.createElement("span", { className: "text-[8px] text-gray-500 font-medium" },
                                    new Date(item.published_at).toLocaleString([], { hour: '2-digit', minute: '2-digit', day: 'numeric', month: 'short' })
                                  )
                                ),
                                React.createElement("div", { className: "flex gap-1.5 items-center" },
                                  item.entities?.slice(0, 2).map((e) =>
                                    React.createElement("span", { key: e.symbol, className: "px-1.5 py-0.5 bg-white/5 border border-white/10 rounded text-[7px] text-gray-400 font-mono" }, "$",
                                      e.symbol
                                    )
                                  )
                                )
                              ),
                              React.createElement("h3", { className: "text-[11px] font-bold text-white mb-1.5 group-hover:text-accent transition-colors leading-snug" },
                                displayTitle
                              ),
                              React.createElement("p", { className: "text-[10px] text-gray-400 line-clamp-2 leading-relaxed mb-3" },
                                displayDesc
                              ),
                              React.createElement("div", { className: "flex items-center justify-between" },
                                React.createElement("div", { className: "flex gap-4 items-center" },
                                  React.createElement("a", {
                                    href: item.url,
                                    target: "_blank",
                                    className: "text-[8px] font-bold text-muted hover:text-white flex items-center gap-1.5 transition-colors"
                                  },
                                    React.createElement("i", { className: "fas fa-external-link-alt text-[7px]" }), " FUENTE ORIGINAL"
                                  ),
                                  React.createElement("button", {
                                    onClick: () => {
                                      if (isTranslated) {
                                        setTranslatedNews((prev) => {
                                          const next = new Set(prev);
                                          next.delete(item.uuid);
                                          return next;
                                        });
                                      } else {
                                        setTranslatedNews((prev) => new Set([...prev, item.uuid]));
                                      }
                                    },
                                    className: `text-[8px] font-bold flex items-center gap-1.5 transition-all ${isTranslated ? 'text-accent' : 'text-accent/60 hover:text-accent'}`
                                  },
                                    React.createElement("i", { className: `fas ${isTranslated ? 'fa-check-circle' : 'fa-language'} text-[9px]` }),
                                    isTranslated ? 'TRADUCIDO' : 'TRADUCIR A ES'
                                  )
                                ),
                                React.createElement("div", {
                                  className: `flex items-center gap-2 px-2.5 py-1 rounded-full text-[7px] font-black tracking-tighter shadow-sm border ${sentiment > 0.1 ? 'bg-green-500/10 text-green-400 border-green-500/20' :
                                    sentiment < -0.1 ? 'bg-red-500/10 text-red-400 border-red-500/20' :
                                      'bg-gray-500/10 text-gray-400 border-gray-500/20'}`
                                },
                                  React.createElement("div", { className: `w-1 h-1 rounded-full ${sentiment > 0.1 ? 'bg-green-400 animate-pulse' : sentiment < -0.1 ? 'bg-red-400 animate-pulse' : 'bg-gray-400'}` }),
                                  sentiment > 0.1 ? 'STRONG BULLISH' : sentiment < -0.1 ? 'STRONG BEARISH' : 'NEUTRAL SENTIMENT'
                                )
                              )
                            )
                          )
                        ));
                    }) :
                      React.createElement("div", { className: "flex flex-col items-center justify-center p-24 gap-5" },
                        React.createElement("div", { className: "w-16 h-16 rounded-full bg-white/5 flex items-center justify-center border border-white/5" },
                          React.createElement("i", { className: "fas fa-newspaper text-white/10 text-2xl" })
                        ),
                        React.createElement("div", { className: "text-center" },
                          React.createElement("span", { className: "text-[10px] text-muted font-black uppercase tracking-[0.3em] block mb-1" }, "No news available"),
                          React.createElement("span", { className: "text-[8px] text-gray-600 font-medium" }, "Check your API Token or sentiment filters")
                        ),
                        React.createElement("button", {
                          onClick: fetchNews,
                          className: "px-4 py-2 bg-accent/5 border border-accent/20 rounded text-[9px] font-bold text-accent hover:bg-accent/10 transition-all"
                        },
                          "RETRY CONNECTION"
                        )
                      )
                  )
            )
        ),
        !showSettings &&
        React.createElement("div", { className: "h-10 bg-black/40 border-t border-white/5 flex items-center justify-center px-6 flex-shrink-0" },
          React.createElement("span", { className: "text-[9px] text-muted font-bold tracking-[0.2em] animate-pulse flex items-center gap-2" },
            React.createElement("div", { className: "w-1 h-1 bg-accent rounded-full" }), " REAL-TIME FEED ACTIVE"
          )
        )
      )
    ));
};
window.EconomicCalendar = EconomicCalendar;