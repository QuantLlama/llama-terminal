const LoginModal = ({ onLogin, updateInfo }) => {
  const { useState } = React;
  const i18n = window.LoginI18n;
  const [language, setLanguage] = useState(() => i18n.getLanguage());
  const [email, setEmail] = useState(() => localStorage.getItem('ql_email') || '');
  const [password, setPassword] = useState(() => localStorage.getItem('ql_password') || '');
  const [rememberMe, setRememberMe] = useState(() => localStorage.getItem('ql_remember') === 'true');
  const [showPassword, setShowPassword] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [guideOpen, setGuideOpen] = useState(false);

  // Every visible string goes through the dictionary of the active language.
  const t = (key) => i18n.tIn(language, key);

  const changeLanguage = (next) => {
    i18n.setLanguage(next);
    setLanguage(next);
  };

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
            setError({ key: 'error.subscriptionRequired', detail: reason });
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
      setError(err.message === 'Invalid login credentials'
        ? { key: 'error.invalidCredentials' }
        : { key: 'error.unknown', detail: err.message });
    } finally {
      setLoading(false);
    }
  };

  const version = (updateInfo && updateInfo.stable_version) || '\u2014';
  const SetupGuide = window.SetupGuide;

  const fieldLabel = "block font-mono text-[11px] uppercase tracking-[0.16em] text-muted";
  const fieldInput = "mt-2 w-full rounded-none border border-border bg-panel px-3 py-2.5 text-[14px] text-text outline-none transition-colors placeholder:text-muted/60 focus-visible:border-accent focus-visible:ring-1 focus-visible:ring-accent/40";
  const linkButton = "font-mono text-[11px] uppercase tracking-[0.16em] transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-accent";
  const blockTitle = "font-mono text-[11px] uppercase tracking-[0.2em] text-text";
  const railLabel = "font-mono text-[11px] uppercase tracking-[0.22em] text-muted";

  const RailItem = ({ marker, children }) =>
    React.createElement("li", { className: "flex gap-3 text-[12.5px] leading-relaxed text-muted" },
      React.createElement("span", { className: "mt-0.5 shrink-0 font-mono text-[11px] text-muted" }, marker),
      React.createElement("span", null, children));

  return React.createElement(React.Fragment, null,
    React.createElement("div", {
      className: "fixed inset-0 z-[10000] overflow-y-auto bg-bg font-sans text-text antialiased",
      style: { animation: 'ql-fade 160ms ease-out both' } },

    React.createElement("div", { className: "mx-auto flex min-h-full w-full max-w-[1180px] flex-col" },

      // ---- Top rail: brand, version, session state, language switch ----
      React.createElement("header", {
        className: "flex h-14 shrink-0 items-center justify-between gap-4 border-b border-border px-5 sm:px-10" },

      React.createElement("div", { className: "flex min-w-0 items-center gap-3" },
        React.createElement("img", {
          src: "/images/QuantumLLama.png",
          alt: "Quantum Llama logo",
          className: "h-6 w-6 shrink-0" }),
        React.createElement("p", { className: "shrink-0 font-mono text-[11px] uppercase tracking-[0.28em] text-text" },
          "Quantum Llama"),
        React.createElement("span", { className: "hidden h-4 w-px shrink-0 bg-border sm:block", "aria-hidden": "true" }),
        React.createElement("p", { className: "hidden truncate font-mono text-[11px] uppercase tracking-[0.16em] text-muted sm:block" },
          t('brand.tagline'))
      ),

      React.createElement("div", { className: "flex shrink-0 items-center gap-3" },
        React.createElement("p", { className: "hidden font-mono text-[11px] uppercase tracking-[0.14em] text-muted sm:block" },
          t('session.state') + ' \u00B7 v' + version),
        React.createElement("span", { className: "hidden h-4 w-px bg-border sm:block", "aria-hidden": "true" }),
        React.createElement("div", {
          role: "group",
          "aria-label": t('lang.label'),
          className: "flex items-center border border-border" },
        i18n.LANGUAGES.map((code) =>
          React.createElement("button", {
            key: code,
            type: "button",
            onClick: () => changeLanguage(code),
            "aria-pressed": language === code,
            className: "w-10 py-1.5 font-mono text-[11px] uppercase tracking-[0.14em] transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-accent " +
              (language === code ? "bg-panel text-accent" : "text-muted hover:text-text") },
          code))
        )
      )
      ),

      // ---- Body: form column + help column ----
      React.createElement("main", {
        className: "grid flex-1 grid-cols-1 lg:grid-cols-[minmax(0,27rem)_minmax(0,1fr)]" },

      // ---- Form ----
      React.createElement("section", {
        role: "dialog",
        "aria-modal": "true",
        "aria-label": t('dialog.label'),
        className: "border-b border-border px-5 py-10 sm:px-10 lg:border-b-0 lg:border-r" },

      React.createElement("p", { className: railLabel }, "01 \u00B7 " + t('form.section')),
      React.createElement("h1", { className: "mt-2.5 text-[18px] font-semibold leading-tight text-text" },
        t('form.title')),
      React.createElement("p", { className: "mt-2 text-[13px] leading-relaxed text-muted" },
        t('form.subtitle')),

      updateInfo && updateInfo.update_required &&
      React.createElement("div", { className: "mt-5 border-l-2 border-accent bg-panel px-3.5 py-2.5" },
        React.createElement("p", { className: "font-mono text-[11px] uppercase tracking-[0.14em] text-accent" },
          t('update.available') + ' \u00B7 v' + version),
        React.createElement("p", { className: "mt-1.5 text-[12.5px] leading-snug text-muted" },
          t('update.restart'))
      ),

      React.createElement("form", { onSubmit: handleAuth, className: "mt-7 space-y-5" },

        React.createElement("div", null,
          React.createElement("label", { htmlFor: "login-email", className: fieldLabel }, t('label.email')),
          React.createElement("input", {
            id: "login-email",
            name: "email",
            type: "email",
            required: true,
            autoComplete: "email",
            "aria-invalid": error ? "true" : "false",
            className: fieldInput,
            placeholder: "you@fund.com",
            value: email,
            onChange: (e) => setEmail(e.target.value) })
        ),

        React.createElement("div", null,
          React.createElement("label", { htmlFor: "login-password", className: fieldLabel }, t('label.password')),
          React.createElement("div", { className: "relative" },
            React.createElement("input", {
              id: "login-password",
              name: "password",
              type: showPassword ? "text" : "password",
              required: true,
              autoComplete: "current-password",
              "aria-invalid": error ? "true" : "false",
              className: fieldInput + " pr-12",
              placeholder: "\u2022\u2022\u2022\u2022\u2022\u2022\u2022\u2022",
              value: password,
              onChange: (e) => setPassword(e.target.value) }),
            React.createElement("button", {
              type: "button",
              onClick: () => setShowPassword((visible) => !visible),
              "aria-label": t(showPassword ? 'action.hidePassword' : 'action.showPassword'),
              "aria-pressed": showPassword,
              className: "absolute right-0 top-2 flex h-[38px] w-11 items-center justify-center text-muted transition-colors hover:text-text focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-accent" },
            React.createElement("i", { className: showPassword ? "fas fa-eye-slash text-[12px]" : "fas fa-eye text-[12px]" })
            )
          )
        ),

        React.createElement("div", { className: "flex items-center gap-3" },
          React.createElement("input", {
            id: "login-remember",
            type: "checkbox",
            checked: rememberMe,
            onChange: (e) => setRememberMe(e.target.checked),
            className: "h-4 w-4 shrink-0 appearance-none border border-border bg-panel checked:border-accent checked:bg-accent focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-accent" }),
          React.createElement("label", {
            htmlFor: "login-remember",
            className: "cursor-pointer select-none font-mono text-[11px] uppercase tracking-[0.14em] text-muted transition-colors hover:text-text" },
          t('label.remember'))
        ),

        error &&
        React.createElement("div", {
          role: "alert",
          "aria-live": "assertive",
          className: "border-l-2 border-danger py-0.5 pl-3.5" },
          React.createElement("p", { className: "text-[12.5px] leading-snug text-danger" }, t(error.key)),
          error.detail &&
          React.createElement("p", { className: "mt-1 font-mono text-[11px] uppercase tracking-[0.12em] text-danger/70" },
            error.detail)
        ),

        React.createElement("button", {
          type: "submit",
          disabled: loading,
          "aria-busy": loading,
          className: "flex w-full items-center justify-center gap-2 rounded-none bg-accent px-4 py-3 font-mono text-[12px] font-semibold uppercase tracking-[0.2em] text-black transition-colors hover:bg-accent/85 disabled:cursor-not-allowed disabled:opacity-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-2 focus-visible:ring-offset-bg" },
        loading ?
        React.createElement(React.Fragment, null,
          React.createElement("i", { className: "fas fa-circle-notch animate-spin text-[11px]" }),
          t('action.signingIn')
        ) : t('action.signIn')
        )
      )
      ),

      // ---- Help ----
      React.createElement("section", { className: "px-5 py-10 sm:px-10" },

        React.createElement("p", { className: railLabel }, "02 \u00B7 " + t('help.toggle')),
        React.createElement("h2", { className: "mt-2.5 text-[15px] font-semibold leading-tight text-text" },
          t('help.title')),
        React.createElement("p", { className: "mt-2 max-w-[58ch] text-[13px] leading-relaxed text-muted" },
          t('help.intro')),

        React.createElement("div", { className: "mt-8 grid gap-8 sm:grid-cols-2" },

          React.createElement("div", null,
            React.createElement("h3", { className: blockTitle }, t('help.requirements.title')),
            React.createElement("ul", { className: "mt-3 space-y-3 border-t border-border pt-3.5" },
              React.createElement(RailItem, { marker: "01" }, t('help.requirements.1')),
              React.createElement(RailItem, { marker: "02" }, t('help.requirements.2')),
              React.createElement(RailItem, { marker: "03" }, t('help.requirements.3'))
            )
          ),

          React.createElement("div", null,
            React.createElement("h3", { className: blockTitle }, t('help.steps.title')),
            React.createElement("ol", { className: "mt-3 space-y-3 border-t border-border pt-3.5" },
              React.createElement(RailItem, { marker: "01" }, t('help.steps.1')),
              React.createElement(RailItem, { marker: "02" }, t('help.steps.2')),
              React.createElement(RailItem, { marker: "03" }, t('help.steps.3'))
            )
          )
        ),

        React.createElement("div", { className: "mt-8 border-l border-border pl-4" },
          React.createElement("h3", { className: blockTitle }, t('help.bridge.title')),
          React.createElement("p", { className: "mt-2 max-w-[66ch] text-[12.5px] leading-relaxed text-muted" },
            t('help.bridge'))
        ),

        React.createElement("div", { className: "mt-10 flex flex-wrap items-center gap-x-7 gap-y-3 border-t border-border pt-5" },
          SetupGuide &&
          React.createElement("button", {
            type: "button",
            onClick: () => setGuideOpen(true),
            className: linkButton + " inline-flex items-center gap-2 text-accent hover:text-accent/80" },
          React.createElement("i", { className: "fas fa-screwdriver-wrench text-[11px]" }),
          t('help.guide')
          ),
          React.createElement("a", {
            href: "https://llamaterminal.nbmsystemas.com/#pricing",
            target: "_blank",
            rel: "noopener noreferrer",
            className: linkButton + " text-muted hover:text-accent" },
          t('help.plans'))
        )
      )
      ),

      // ---- Bottom rail: what this login is talking to ----
      React.createElement("footer", {
        className: "mt-auto flex h-10 shrink-0 items-center border-t border-border px-5 sm:px-10" },
      React.createElement("p", { className: "font-mono text-[10.5px] uppercase tracking-[0.18em] text-muted/70" },
        "MT5 \u00B7 CCXT \u00B7 " + t('footer.stack'))
      )
    )
    ),

    guideOpen && SetupGuide &&
    React.createElement(SetupGuide, {
      onClose: () => setGuideOpen(false),
      language: language,
      onLanguageChange: changeLanguage
    })
  );
};
window.LoginModal = LoginModal;
