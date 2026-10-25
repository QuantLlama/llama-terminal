const LoginModal = ({ onLogin, updateInfo }) => {
  const { useState } = React;
  const [email, setEmail] = useState(() => localStorage.getItem('ql_email') || '');
  const [password, setPassword] = useState(() => localStorage.getItem('ql_password') || '');
  const [rememberMe, setRememberMe] = useState(() => localStorage.getItem('ql_remember') === 'true');
  const [showPassword, setShowPassword] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [guideOpen, setGuideOpen] = useState(false);
  const handleAuth = async (e) => {
    e.preventDefault();
    setLoading(true);
    setError(null);
    try {
      const result = await window.supabase.auth.signInWithPassword({ email, password });
      if (result.error) throw result.error;
      if (rememberMe) {
        localStorage.setItem('ql_email', email);
        localStorage.setItem('ql_password', password);
        localStorage.setItem('ql_remember', 'true');
      } else {
        localStorage.removeItem('ql_email');
        localStorage.removeItem('ql_password');
        localStorage.setItem('ql_remember', 'false');
      }
      try {
        const sRes = await fetch('/api/auth/session', {
          headers: { 'Authorization': `Bearer ${result.data.session.access_token}` }
        });
        if (sRes.ok) {
          const sData = await sRes.json();
          if (!sData.is_subscribed) {
            const reason = sData.reason || 'unknown';
            console.warn('[Login] Access denied. Reason:', reason);
            setError(`Restricted access. PREMIUM account required. (${reason})`);
            await window.supabase.auth.signOut();
            return;
          }
        } else {
          console.warn('[Login] Subscription endpoint returned', sRes.status, '- allowing login');
        }
      } catch (subErr) {
        console.warn('Subscription check network error:', subErr, '- allowing login');
      }
      onLogin(result.data.session);
    } catch (err) {
      console.error('[Login] Supabase Auth Error:', err);
      setError(err.message === 'Invalid login credentials' ? 'Invalid credentials' : err.message);
    } finally {
      setLoading(false);
    }
  };

  const CAPABILITIES = [
    {
      icon: 'fa-chart-area',
      title: 'Order flow & footprint',
      detail: 'Aggregated delta, imbalances and volume profile on every bar.'
    },
    {
      icon: 'fa-layer-group',
      title: 'DOM & liquidity heatmap',
      detail: 'Depth of market, resting liquidity and big prints in one ladder.'
    },
    {
      icon: 'fa-flask',
      title: 'Algo lab & backtests',
      detail: 'Scheduled strategies, replays and a risk-checked order path.'
    }
  ];

  const labelClass = "block text-[11px] font-mono font-semibold uppercase tracking-[0.18em] text-white/45 mb-1.5";
  const fieldClass = "w-full bg-black/40 text-white text-[13px] px-3 py-2.5 rounded-lg outline-none transition-shadow placeholder:text-white/25 focus-visible:ring-2 focus-visible:ring-amber-500/60 focus-visible:ring-offset-2 focus-visible:ring-offset-black";

  return React.createElement(React.Fragment, null,
    React.createElement("div", {
      className: "fixed inset-0 z-[10000] bg-black/80 backdrop-blur-sm grid place-items-center p-4 sm:p-6 overflow-y-auto",
      style: { animation: 'ql-fade 200ms ease-out both' } },

    React.createElement("div", {
      role: "dialog",
      "aria-modal": "true",
      "aria-label": "Sign in to Quantum Llama Professional",
      className: "w-full max-w-4xl my-auto grid grid-cols-1 lg:grid-cols-2 overflow-hidden rounded-2xl border border-white/10 bg-[#0a0a0b] shadow-[0_40px_120px_-24px_rgba(0,0,0,0.95)]",
      style: { animation: 'ql-rise 340ms cubic-bezier(0.16, 1, 0.3, 1) both' } },

    // ---- Brand panel (wide screens only) ----
    React.createElement("aside", {
      className: "relative hidden lg:flex flex-col justify-between gap-10 p-8 overflow-hidden border-r border-white/10 bg-[radial-gradient(130%_120%_at_0%_0%,rgba(245,158,11,0.16),transparent_58%)]" },

    React.createElement("div", {
      className: "pointer-events-none absolute inset-0 opacity-[0.13] bg-[linear-gradient(to_right,rgba(255,255,255,0.35)_1px,transparent_1px),linear-gradient(to_bottom,rgba(255,255,255,0.35)_1px,transparent_1px)] bg-[size:44px_44px]" }),

    React.createElement("div", { className: "relative flex items-center gap-3" },
    React.createElement("img", {
      src: "/images/QuantumLLama.png",
      alt: "Quantum Llama logo",
      className: "w-12 h-12 rounded-xl border border-amber-500/25 bg-black/50 p-1 drop-shadow-[0_0_18px_rgba(245,158,11,0.3)]" }),
    React.createElement("div", null,
      React.createElement("p", { className: "text-[11px] font-mono uppercase tracking-[0.34em] text-amber-500/80" }, "Quantum Llama"),
      React.createElement("p", { className: "text-[13px] font-semibold text-white/65" }, "Professional Terminal")
    )
    ),

    React.createElement("div", { className: "relative space-y-6" },
    React.createElement("div", { className: "h-px w-12 bg-gradient-to-r from-amber-500/70 to-transparent" }),
    React.createElement("h1", { className: "font-mono text-[26px] font-semibold leading-[1.15] text-white" },
      "Order flow, depth and execution in one screen."),
    React.createElement("p", { className: "text-[13px] leading-relaxed text-white/50" },
      "Your MetaTrader 5 terminal keeps running on your machine. The bridge you install connects it to this platform, so charts, depth and orders share one source of truth."),
    React.createElement("ul", { className: "space-y-3.5 pt-1" },
      CAPABILITIES.map((item) =>
      React.createElement("li", { key: item.title, className: "flex items-start gap-3" },
        React.createElement("span", {
          className: "mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-md border border-amber-500/20 bg-amber-500/10 text-[11px] text-amber-500/90" },
        React.createElement("i", { className: `fas ${item.icon}` })),
        React.createElement("span", { className: "text-[12.5px] leading-snug text-white/60" },
          React.createElement("strong", { className: "block font-semibold text-white/85" }, item.title),
          item.detail
        )
      )
      )
    )
    ),

    React.createElement("div", { className: "relative flex items-center justify-between gap-4 border-t border-white/5 pt-4" },
      React.createElement("p", { className: "text-[11px] font-mono uppercase tracking-[0.22em] text-white/25" }, "MT5 \u00B7 CCXT \u00B7 Private bridge"),
      React.createElement("p", { className: "text-[11px] font-mono text-white/20" }, "v" + ((updateInfo && updateInfo.stable_version) || "\u2014"))
    )
    ),

    // ---- Form panel ----
    React.createElement("section", { className: "p-6 sm:p-8" },

    React.createElement("div", { className: "mb-6 flex items-center gap-3 lg:hidden" },
      React.createElement("img", {
        src: "/images/QuantumLLama.png",
        alt: "Quantum Llama logo",
        className: "w-10 h-10 rounded-lg border border-amber-500/20 bg-black/50 p-1" }),
      React.createElement("div", null,
        React.createElement("p", { className: "text-[11px] font-mono uppercase tracking-[0.3em] text-amber-500/80" }, "Quantum Llama"),
        React.createElement("p", { className: "text-[12px] font-semibold text-white/60" }, "Professional Terminal")
      )
    ),

    React.createElement("h2", { className: "text-[18px] font-semibold text-white" }, "Sign in"),
    React.createElement("p", { className: "mt-1 text-[12.5px] text-white/45" },
      "Use the email address tied to your subscription."),

    updateInfo && updateInfo.update_required &&
    React.createElement("div", {
      className: "mt-4 flex items-center gap-2 rounded-lg border border-amber-900/40 bg-amber-950/20 px-3 py-2 text-[11.5px] text-amber-500/90" },
      React.createElement("i", { className: "fas fa-info-circle" }),
      React.createElement("p", null, "v", updateInfo.stable_version, " available")
    ),

    React.createElement("form", { onSubmit: handleAuth, className: "mt-5 space-y-4" },

      React.createElement("div", null,
        React.createElement("label", { htmlFor: "login-email", className: labelClass }, "Email"),
        React.createElement("input", {
          id: "login-email",
          name: "email",
          type: "email",
          required: true,
          autoComplete: "email",
          "aria-invalid": error ? "true" : "false",
          className: fieldClass,
          placeholder: "you@fund.com",
          value: email,
          onChange: (e) => setEmail(e.target.value) })
      ),

      React.createElement("div", null,
        React.createElement("label", { htmlFor: "login-password", className: labelClass }, "Password"),
        React.createElement("div", { className: "relative" },
          React.createElement("input", {
            id: "login-password",
            name: "password",
            type: showPassword ? "text" : "password",
            required: true,
            autoComplete: "current-password",
            "aria-invalid": error ? "true" : "false",
            className: fieldClass + " pr-12",
            placeholder: "\u2022\u2022\u2022\u2022\u2022\u2022\u2022\u2022",
            value: password,
            onChange: (e) => setPassword(e.target.value) }),
          React.createElement("button", {
            type: "button",
            onClick: () => setShowPassword((visible) => !visible),
            "aria-label": showPassword ? "Hide password" : "Show password",
            "aria-pressed": showPassword,
            className: "absolute right-2 top-1/2 -translate-y-1/2 rounded-md px-2 py-1.5 text-[12px] text-white/40 transition-colors hover:text-white/85 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-amber-500/60" },
          React.createElement("i", { className: showPassword ? "fas fa-eye-slash" : "fas fa-eye" })
          )
        )
      ),

      React.createElement("div", { className: "flex items-center gap-2.5 py-1" },
        React.createElement("input", {
          id: "login-remember",
          type: "checkbox",
          checked: rememberMe,
          onChange: (e) => setRememberMe(e.target.checked),
          className: "h-3.5 w-3.5 rounded border-white/20 bg-black/40 accent-amber-500 focus-visible:ring-2 focus-visible:ring-amber-500/60" }),
        React.createElement("label", {
          htmlFor: "login-remember",
          className: "cursor-pointer select-none text-[12px] text-white/45 transition-colors hover:text-white/70" },
        "Remember credentials")
      ),

      error &&
      React.createElement("div", {
        role: "alert",
        "aria-live": "assertive",
        className: "flex items-start gap-2 rounded-lg border border-danger/25 bg-danger/10 px-3 py-2 text-[12px] leading-snug text-danger" },
        React.createElement("i", { className: "fas fa-triangle-exclamation mt-0.5" }),
        React.createElement("span", null, error)
      ),

      React.createElement("button", {
        type: "submit",
        disabled: loading,
        "aria-busy": loading,
        className: "flex w-full items-center justify-center gap-2 rounded-lg bg-amber-500 px-4 py-2.5 text-[13px] font-bold uppercase tracking-[0.18em] text-black transition-all hover:bg-amber-400 active:scale-[0.99] disabled:cursor-not-allowed disabled:opacity-60 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-amber-300 focus-visible:ring-offset-2 focus-visible:ring-offset-black" },
      loading ?
      React.createElement(React.Fragment, null,
        React.createElement("i", { className: "fas fa-circle-notch animate-spin" }),
        "Signing in"
      ) : 'SIGN IN'
      )
    ),

    React.createElement("div", { className: "mt-6 flex flex-wrap items-center justify-between gap-3 border-t border-white/10 pt-4" },
      React.createElement("button", {
        type: "button",
        onClick: () => setGuideOpen(true),
        className: "inline-flex items-center gap-2 rounded-md text-[12px] font-semibold text-amber-500/90 underline decoration-dotted underline-offset-4 transition-colors hover:text-amber-400 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-amber-500/60" },
      React.createElement("i", { className: "fas fa-screwdriver-wrench text-[11px]" }),
      "Configurar mi sistema"
      ),
      React.createElement("a", {
        href: "https://llamaterminal.nbmsystemas.com/#pricing",
        target: "_blank",
        rel: "noopener noreferrer",
        className: "text-[11px] font-bold tracking-[0.16em] text-white/40 underline decoration-dotted underline-offset-4 transition-colors hover:text-amber-500/80 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-amber-500/60" },
      "PREMIUM PLANS"
      )
    )
    )
    )
    ),

    guideOpen && window.SetupGuide &&
    React.createElement(window.SetupGuide, { onClose: () => setGuideOpen(false) })
  );
};
window.LoginModal = LoginModal;
