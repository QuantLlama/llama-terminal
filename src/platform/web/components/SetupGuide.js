const SetupGuide = ({ onClose }) => {
  const { useEffect, useRef } = React;

  // Illustrations.
  // Inline SVG only: no binary assets, no external URLs, nothing to fetch.
  const TOPOLOGY_SVG = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 320 248" class="w-full h-auto" focusable="false">
  <g fill="none" stroke="currentColor" stroke-opacity="0.22">
    <rect x="1" y="1" width="318" height="46" rx="9" />
    <rect x="1" y="200" width="318" height="46" rx="9" />
    <rect x="1" y="134" width="318" height="46" rx="9" stroke-dasharray="5 4" />
  </g>
  <rect x="1" y="68" width="318" height="46" rx="9" fill="rgba(245,158,11,0.07)" stroke="#f59e0b" stroke-opacity="0.5" />
  <g fill="currentColor" opacity="0.9" font-family="'Inter', sans-serif" font-size="14" font-weight="600">
    <text x="16" y="22">MetaTrader 5 terminal</text>
    <text x="16" y="89">mt5_server.py bridge</text>
    <text x="16" y="155">Private network</text>
    <text x="16" y="221">Cloud container</text>
  </g>
  <g fill="currentColor" opacity="0.55" font-family="'Inter', sans-serif" font-size="12">
    <text x="16" y="38">your machine, broker account logged in</text>
    <text x="16" y="105">port 8081, X-Bridge-Token required</text>
    <text x="16" y="171">Tailscale, WireGuard, never public</text>
    <text x="16" y="237">MT5_BRIDGE_URL points here</text>
  </g>
  <g stroke="currentColor" stroke-opacity="0.5" stroke-width="1.5" marker-end="url(#ql-topology-arrow)">
    <line x1="160" y1="49" x2="160" y2="63" />
    <line x1="160" y1="116" x2="160" y2="130" />
    <line x1="160" y1="182" x2="160" y2="196" />
  </g>
  <defs>
    <marker id="ql-topology-arrow" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="7" markerHeight="7" orient="auto">
      <path d="M 0 0 L 10 5 L 0 10 z" fill="currentColor" />
    </marker>
  </defs>
</svg>`;

  const STEP_RAIL_SVG = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 320 296" class="w-full h-auto" focusable="false">
  <line x1="22" y1="18" x2="22" y2="278" stroke="currentColor" stroke-opacity="0.15" stroke-width="1" />
  <g fill="rgba(245,158,11,0.08)" stroke="#f59e0b" stroke-opacity="0.4">
    <circle cx="22" cy="24" r="11" /><circle cx="22" cy="64" r="11" /><circle cx="22" cy="104" r="11" />
    <circle cx="22" cy="144" r="11" /><circle cx="22" cy="184" r="11" /><circle cx="22" cy="224" r="11" />
    <circle cx="22" cy="264" r="11" />
  </g>
  <g fill="#f59e0b" font-family="'JetBrains Mono', monospace" font-size="11.5" text-anchor="middle">
    <text x="22" y="28">1</text><text x="22" y="68">2</text><text x="22" y="108">3</text>
    <text x="22" y="148">4</text><text x="22" y="188">5</text><text x="22" y="228">6</text>
    <text x="22" y="268">7</text>
  </g>
  <g fill="currentColor" opacity="0.7" font-family="'Inter', sans-serif" font-size="12.5">
    <text x="44" y="28">MT5 terminal ready</text>
    <text x="44" y="68">Project installed locally</text>
    <text x="44" y="108">Bridge token generated</text>
    <text x="44" y="148">Bridge running with token</text>
    <text x="44" y="188">Container pointed at bridge</text>
    <text x="44" y="228">Health check passes</text>
    <text x="44" y="268">Crypto keys (optional)</text>
  </g>
</svg>`;

  const HEALTH_SVG = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 320 136" class="w-full h-auto" focusable="false">
  <rect x="1" y="1" width="318" height="134" rx="10" fill="rgba(16,185,129,0.05)" stroke="#10b981" stroke-opacity="0.3" />
  <circle cx="17" cy="21" r="4" fill="#10b981" />
  <text x="29" y="25" fill="#10b981" opacity="0.9" font-family="'JetBrains Mono', monospace" font-size="11.5">GET /api/health \u2192 200</text>
  <g fill="currentColor" opacity="0.6" font-family="'JetBrains Mono', monospace" font-size="11.5">
    <text x="16" y="54">{ "ready_for_ui": true,</text>
    <text x="16" y="76">  "mt5_status": <tspan fill="#10b981">"connected"</tspan>,</text>
    <text x="16" y="98">  "services": { "market_data": <tspan fill="#10b981">"ONLINE"</tspan> } }</text>
    <text x="16" y="122" opacity="0.55">Both green: the container reached your bridge.</text>
  </g>
</svg>`;

  // Defaults are the ones the runtime modules actually use.
  const BRIDGE_ENV = [
    ['MT5_BRIDGE_BIND', '127.0.0.1', 'Interface the bridge listens on. Set 0.0.0.0 to expose it on the private network.'],
    ['MT5_BRIDGE_PORT', '8081', 'Port the bridge listens on. The platform URL must use the same port.'],
    ['MT5_BRIDGE_TOKEN', '(unset)', 'Shared token checked on every request. Required as soon as another machine can reach the bridge.'],
    ['MT5_BRIDGE_URL', 'http://127.0.0.1:8081', 'Where the platform looks for the bridge when the variable is unset.']
  ];

  const SETUP_STEPS = [
    { n: 1,
      title: 'Install MetaTrader 5 and log in to your broker',
      blocks: [
        { p: 'The MetaTrader5 Python package runs on Windows only, so the terminal always stays on your machine. Install it there, or run it on Linux through Wine.' },
        { list: [
          'Log in to your broker account inside the terminal. Market data and orders need an authenticated session.',
          'Leave the terminal open: the bridge drives the terminal that is already running.'
        ] }
      ] },
    { n: 2,
      title: 'Get the project running on the same machine',
      blocks: [
        { p: 'Clone the repository and let the setup script build the environment and install requirements.txt.' },
        { code: ['./setup_env.sh                 # Linux and macOS, creates venv_linux', 'setup_env.bat                  # Windows, creates venv'] },
        { note: 'Run it from the project root. It installs the same dependency list the platform ships with.' }
      ] },
    { n: 3,
      title: 'Generate the bridge token',
      blocks: [
        { code: ['python -c "import secrets; print(secrets.token_urlsafe(32))"'] },
        { p: 'Copy the printed value. The bridge can place real orders, so the token is mandatory the moment it is reachable from another machine, and anyone holding the URL and the token has the same trading access you do.' },
        { note: 'Keep the token out of git, screenshots and support tickets. Rotate it by changing it on both sides and restarting both processes.' }
      ] },
    { n: 4,
      title: 'Start the bridge with that token',
      blocks: [
        { p: 'Windows, in the environment where MetaTrader 5 runs:' },
        { code: ['set MT5_BRIDGE_BIND=0.0.0.0', 'set MT5_BRIDGE_TOKEN=<your token>', 'start_mt5_server.bat'] },
        { p: 'Linux with Wine, inside the same prefix:' },
        { code: ['export MT5_BRIDGE_BIND=0.0.0.0', 'export MT5_BRIDGE_TOKEN=<your token>', 'wine python -m uvicorn mt5_server:app --host "$MT5_BRIDGE_BIND" --port 8081'] },
        { note: 'MT5_BRIDGE_PORT defaults to 8081. The pair 127.0.0.1 with no token is the desktop-only default; never keep it once another machine needs to connect.' }
      ] },
    { n: 5,
      title: 'Connect the two sides',
      blocks: [
        { p: 'The platform process needs two values that match the bridge exactly:' },
        { list: [
          'MT5_BRIDGE_URL: the address that reaches the bridge from the machine running the platform.',
          'MT5_BRIDGE_TOKEN: the same token the bridge was started with.'
        ] },
        { p: 'When MT5_BRIDGE_URL is unset the platform falls back to http://127.0.0.1:8081, which only works when the bridge and the platform share a host.' },
        { note: 'Keep the bridge on a private network such as Tailscale, not on a public address.' }
      ] },
    { n: 6,
      title: 'Verify end to end',
      blocks: [
        { p: 'First the bridge itself, from the machine that runs it:' },
        { code: ['curl -s -H "X-Bridge-Token: <your token>" http://127.0.0.1:8081/api/balance'] },
        { p: 'Then the platform. Its /api/health response must show mt5_status connected and services.market_data ONLINE:' },
        { p: 'In the terminal, the status bar along the bottom of the screen names the platform and shows CONNECTED once the bridge answers.' }
      ] },
    { n: 7,
      title: 'Add crypto accounts (optional)',
      blocks: [
        { p: 'CCXT exchange keys are entered inside the app: open Settings from the gear button in the top bar and use the Accounts tab to add a CRYPTO account with its API key, secret and passphrase if the venue asks for one.' },
        { note: 'Some venues block the server region. When that happens the deployment also needs an egress proxy; that is an operator concern documented in the cloud runbook.' }
      ] }
  ];

  const TROUBLESHOOTING = [
    ['401 invalid bridge token', 'The token differs between the bridge and the platform. Set the same MT5_BRIDGE_TOKEN on both sides and restart both.'],
    ['Nothing answers on the port', 'The bridge is not running, or a firewall drops 8081. Bind 0.0.0.0 and allow 8081 only on the private interface.'],
    ['Reachable locally, not from the cloud', 'The private network is down. Check that both machines are signed in and can see each other.'],
    ['Could not connect to MT5', 'The terminal is closed or not logged in to the broker account. Open it, sign in, and retry.'],
    ['Wrong port', 'MT5_BRIDGE_PORT and the port inside MT5_BRIDGE_URL must agree. The default is 8081.']
  ];

  // Modal behaviour.
  const panelRef = useRef(null);

  useEffect(() => {
    const previouslyFocused = document.activeElement;
    const getFocusable = () => {
      if (!panelRef.current) return [];
      return Array.prototype.slice.call(panelRef.current.querySelectorAll(
        'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])'
      )).filter((node) => !node.disabled && node.getAttribute('aria-hidden') !== 'true');
    };
    const handleKeyDown = (event) => {
      if (event.key === 'Escape') {
        event.preventDefault();
        onClose();
        return;
      }
      if (event.key === 'Tab') {
        const focusable = getFocusable();
        if (focusable.length === 0) {
          event.preventDefault();
          return;
        }
        const first = focusable[0];
        const last = focusable[focusable.length - 1];
        if (event.shiftKey && document.activeElement === first) {
          event.preventDefault();
          last.focus();
        } else if (!event.shiftKey && document.activeElement === last) {
          event.preventDefault();
          first.focus();
        }
      }
    };
    document.addEventListener("keydown", handleKeyDown);
    const firstField = getFocusable()[0];
    if (firstField) firstField.focus();
    return () => {
      document.removeEventListener("keydown", handleKeyDown);
      if (previouslyFocused && previouslyFocused.focus) previouslyFocused.focus();
    };
  }, [onClose]);

  const codeClass = "overflow-x-auto rounded-lg border border-white/10 bg-black/60 px-3 py-2.5 font-mono text-[11.5px] leading-relaxed text-amber-100/80";

  const renderBlock = (block, index) => {
    if (block.p) {
      return React.createElement("p", { key: index, className: "text-[12.5px] leading-relaxed text-white/60" }, block.p);
    }
    if (block.list) {
      return React.createElement("ul", { key: index, className: "space-y-1.5 pl-4" },
        block.list.map((item, itemIndex) =>
          React.createElement("li", {
            key: itemIndex,
            className: "list-disc text-[12.5px] leading-relaxed text-white/60 marker:text-amber-500/60" }, item)
        )
      );
    }
    if (block.code) {
      return React.createElement("pre", { key: index, className: codeClass },
        React.createElement("code", null, block.code.join("\n")));
    }
    if (block.note) {
      return React.createElement("p", {
        key: index,
        className: "rounded-lg border border-amber-900/30 bg-amber-950/15 px-3 py-2 text-[11.5px] leading-relaxed text-amber-500/85" },
      block.note);
    }
    return null;
  };

  return React.createElement("div", {
    className: "fixed inset-0 z-[10001] flex items-end sm:items-center justify-center bg-black/85 backdrop-blur-sm p-0 sm:p-6",
    style: { animation: 'ql-fade 180ms ease-out both' },
    onMouseDown: (e) => {
      if (e.target === e.currentTarget) onClose();
    } },

  React.createElement("div", {
    ref: panelRef,
    role: "dialog",
    "aria-modal": "true",
    "aria-labelledby": "setup-guide-title",
    tabIndex: -1,
    className: "flex h-[92vh] sm:h-auto sm:max-h-[88vh] w-full sm:max-w-3xl flex-col overflow-hidden rounded-t-2xl sm:rounded-2xl border border-white/10 bg-[#0b0b0c] text-left shadow-[0_40px_120px_-24px_rgba(0,0,0,0.95)] outline-none",
    style: { animation: 'ql-rise 300ms cubic-bezier(0.16, 1, 0.3, 1) both' } },

  // Header
  React.createElement("div", { className: "flex items-start justify-between gap-4 border-b border-white/10 px-5 py-4 sm:px-6" },
    React.createElement("div", null,
      React.createElement("p", { className: "font-mono text-[11px] uppercase tracking-[0.3em] text-amber-500/80" }, "Setup guide"),
      React.createElement("h2", { id: "setup-guide-title", className: "mt-1 text-[17px] font-semibold text-white" },
        "Connect this platform to your machine"),
      React.createElement("p", { className: "mt-1 text-[12px] text-white/45" },
        "Seven steps. Your terminal keeps running locally; the platform talks to it over HTTP.")
    ),
    React.createElement("button", {
      type: "button",
      onClick: () => onClose(),
      "aria-label": "Close setup guide",
      className: "flex h-8 w-8 shrink-0 items-center justify-center rounded-lg border border-white/10 bg-white/5 text-white/60 transition-colors hover:border-white/20 hover:text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-amber-500/60" },
    React.createElement("i", { className: "fas fa-times text-[12px]" })
    )
  ),

  // Scrollable body
  React.createElement("div", { className: "flex-1 overflow-y-auto px-5 py-5 sm:px-6 space-y-6" },

    React.createElement("div", { className: "flex items-start gap-3 rounded-xl border border-white/10 bg-white/[0.03] px-4 py-3" },
      React.createElement("i", { className: "fas fa-circle-info mt-0.5 text-[12px] text-amber-500/80" }),
      React.createElement("p", { className: "text-[12.5px] leading-relaxed text-white/60" },
        "MetaTrader 5 is Windows-only, so the platform cannot reach a broker on its own. The terminal stays on your machine and a small bridge (mt5_server.py) exposes it over HTTP; the platform reaches that bridge and nothing else.")
    ),

    // Figure 1: topology
    React.createElement("figure", { className: "space-y-2" },
      React.createElement("div", {
        role: "img",
        "aria-label": "Topology: the MetaTrader 5 terminal connects to the mt5_server.py bridge on port 8081, which crosses a private Tailscale network to the cloud container",
        className: "mx-auto max-w-[440px] rounded-xl border border-white/10 bg-black/40 p-3 text-white/70",
        dangerouslySetInnerHTML: { __html: TOPOLOGY_SVG } }),
      React.createElement("figcaption", { className: "text-[11.5px] text-white/40" },
        "Terminal, then bridge, then private network, then container. Nothing else is exposed.")
    ),

    // Figure 2: step rail
    React.createElement("figure", { className: "space-y-2" },
      React.createElement("div", {
        "aria-hidden": "true",
        className: "mx-auto max-w-[440px] rounded-xl border border-white/10 bg-black/40 p-3 text-white/70",
        dangerouslySetInnerHTML: { __html: STEP_RAIL_SVG } }),
      React.createElement("figcaption", { className: "text-[11.5px] text-white/40" },
        "The same seven steps, in order. Steps 3 and 4 are the ones people skip.")
    ),

    // Environment variables
    React.createElement("section", { className: "space-y-2" },
      React.createElement("h3", { className: "font-mono text-[11px] uppercase tracking-[0.24em] text-white/45" }, "Environment variables"),
      React.createElement("div", { className: "divide-y divide-white/5 overflow-hidden rounded-xl border border-white/10 bg-white/[0.02]" },
        BRIDGE_ENV.map((row) =>
        React.createElement("div", { key: row[0], className: "flex flex-col gap-1 px-4 py-3 sm:flex-row sm:items-baseline sm:gap-4" },
          React.createElement("code", { className: "shrink-0 font-mono text-[11.5px] text-white/85 sm:w-52" }, row[0]),
          React.createElement("code", { className: "shrink-0 font-mono text-[11.5px] text-amber-500/90 sm:w-44" }, row[1]),
          React.createElement("span", { className: "text-[11.5px] leading-relaxed text-white/45" }, row[2])
        )
        )
      )
    ),

    // Steps
    React.createElement("section", { className: "space-y-5" },
      SETUP_STEPS.map((step) =>
      React.createElement("article", { key: step.n, className: "rounded-xl border border-white/10 bg-white/[0.02] p-4" },
        React.createElement("div", { className: "flex items-start gap-3" },
          React.createElement("span", {
            className: "flex h-7 w-7 shrink-0 items-center justify-center rounded-full border border-amber-500/40 bg-amber-500/10 font-mono text-[11.5px] text-amber-500" },
          step.n),
          React.createElement("h3", { className: "pt-1 text-[13.5px] font-semibold leading-snug text-white/90" }, step.title)
        ),
        React.createElement("div", { className: "mt-3 space-y-2.5 pl-10" },
          step.blocks.map(renderBlock)
        )
      )
      )
    ),

    // Figure 3: what success looks like
    React.createElement("figure", { className: "space-y-2" },
      React.createElement("div", {
        role: "img",
        "aria-label": "The platform health payload reports mt5_status connected and services market_data ONLINE",
        className: "mx-auto max-w-[440px] rounded-xl border border-white/10 bg-black/40 p-3 text-white/70",
        dangerouslySetInnerHTML: { __html: HEALTH_SVG } }),
      React.createElement("figcaption", { className: "text-[11.5px] leading-relaxed text-white/40" },
        "This is the platform's own health payload. Nothing else you do matters until both fields are green, and the terminal's bottom status bar shows the platform as CONNECTED.")
    ),

    // Troubleshooting
    React.createElement("section", { className: "space-y-2" },
      React.createElement("h3", { className: "font-mono text-[11px] uppercase tracking-[0.24em] text-white/45" }, "Troubleshooting"),
      React.createElement("div", { className: "divide-y divide-white/5 overflow-hidden rounded-xl border border-white/10 bg-white/[0.02]" },
        TROUBLESHOOTING.map((row) =>
        React.createElement("div", { key: row[0], className: "px-4 py-3" },
          React.createElement("p", { className: "font-mono text-[11.5px] text-danger/80" }, row[0]),
          React.createElement("p", { className: "mt-1 text-[11.5px] leading-relaxed text-white/50" }, row[1])
        )
        )
      )
    ),

    React.createElement("p", { className: "pb-2 text-[11px] leading-relaxed text-white/30" },
      "The operator runbook in the repository (deploy/MT5_BRIDGE.md) and the cloud document (docs/CLOUD.md) hold the same procedure for support.")
  ),

  // Footer
  React.createElement("div", { className: "flex flex-wrap items-center justify-between gap-3 border-t border-white/10 px-5 py-3 sm:px-6" },
    React.createElement("p", { className: "text-[11px] text-white/35" },
      "Anyone holding the bridge URL and token can trade on the signed-in terminal."),
    React.createElement("button", {
      type: "button",
      onClick: () => onClose(),
      className: "rounded-lg border border-white/10 bg-white/5 px-3 py-1.5 text-[12px] font-semibold text-white/70 transition-colors hover:border-amber-500/30 hover:text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-amber-500/60" },
    "Close"
    )
  )
  )
  );
};
window.SetupGuide = SetupGuide;
