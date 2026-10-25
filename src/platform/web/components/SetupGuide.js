/**
 * Setup guide as its own screen: an index rail on the left, a reading column on
 * the right, flat surfaces and hairlines only. It reads the same dictionaries
 * the login uses, so switching language inside the guide also switches the form
 * behind it.
 */
const GuideSection = ({ id, title, children }) =>
  React.createElement("section", { id: id, className: "scroll-mt-6" },
    React.createElement("h2", {
      className: "border-b border-border pb-2 font-mono text-[11px] uppercase tracking-[0.22em] text-muted" },
    title),
    React.createElement("div", { className: "mt-5 space-y-5" }, children)
  );

const GuideCode = ({ lines }) =>
  React.createElement("pre", {
    className: "overflow-x-auto border border-border bg-panel px-3.5 py-3 font-mono text-[12px] leading-relaxed text-text/85" },
  React.createElement("code", null, lines.join("\n")));

const GuideBlock = ({ block }) => {
  if (block.p) {
    return React.createElement("p", { className: "max-w-[74ch] text-[13px] leading-relaxed text-muted" }, block.p);
  }
  if (block.list) {
    return React.createElement("ul", { className: "space-y-2" },
      block.list.map((item, index) =>
        React.createElement("li", { key: index, className: "flex gap-3 text-[13px] leading-relaxed text-muted" },
          React.createElement("span", { className: "mt-0.5 shrink-0 font-mono text-[11px] text-muted" }, "\u2014"),
          React.createElement("span", null, item)
        )
      )
    );
  }
  if (block.code) return React.createElement(GuideCode, { lines: block.code });
  if (block.note) {
    return React.createElement("p", {
      className: "max-w-[74ch] border-l-2 border-accent/40 pl-3.5 text-[12.5px] leading-relaxed text-muted" },
    block.note);
  }
  return null;
};

const SetupGuide = ({ onClose, language: languageProp, onLanguageChange }) => {
  const { useEffect, useRef } = React;
  const i18n = window.LoginI18n;
  const language = languageProp || i18n.getLanguage();
  const changeLanguage = onLanguageChange || ((next) => i18n.setLanguage(next));
  const doc = window.SetupGuideContent[language];

  const panelRef = useRef(null);

  // Escape closes; Tab stays inside the panel; focus returns where it came from.
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
    document.addEventListener('keydown', handleKeyDown);
    const firstField = getFocusable()[0];
    if (firstField) firstField.focus();
    return () => {
      document.removeEventListener('keydown', handleKeyDown);
      if (previouslyFocused && previouslyFocused.focus) previouslyFocused.focus();
    };
  }, [onClose]);

  const goTo = (event, id) => {
    event.preventDefault();
    const target = document.getElementById(id);
    if (target) target.scrollIntoView({ block: 'start', behavior: 'smooth' });
  };

  const railLabel = "font-mono text-[11px] uppercase tracking-[0.22em] text-muted";
  const indexItem = "flex items-baseline gap-3 border-l border-border py-2 pl-3 text-left transition-colors hover:border-accent hover:text-text focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-accent";

  const INDEX = [
    { id: 'guide-overview', label: doc.sections.overview },
    { id: 'guide-env', label: doc.sections.env },
    { id: 'guide-steps', label: doc.sections.steps },
    { id: 'guide-troubleshooting', label: doc.sections.troubleshooting }
  ];

  return React.createElement("div", {
    ref: panelRef,
    role: "dialog",
    "aria-modal": "true",
    "aria-labelledby": "setup-guide-title",
    className: "fixed inset-0 z-[10001] overflow-y-auto bg-bg font-sans text-text antialiased",
    style: { animation: 'ql-fade 160ms ease-out both' } },

  React.createElement("div", { className: "mx-auto flex min-h-full w-full max-w-[1180px] flex-col" },

    // ---- Top rail ----
    React.createElement("header", {
      className: "flex h-14 shrink-0 items-center justify-between gap-4 border-b border-border px-5 sm:px-10" },

    React.createElement("div", { className: "flex min-w-0 items-center gap-3" },
      React.createElement("p", { className: "hidden shrink-0 font-mono text-[11px] uppercase tracking-[0.22em] text-muted sm:block" },
        doc.eyebrow),
      React.createElement("span", { className: "hidden h-4 w-px shrink-0 bg-border sm:block", "aria-hidden": "true" }),
      React.createElement("h1", { id: "setup-guide-title", className: "line-clamp-2 text-[15px] font-semibold leading-tight text-text" },
        doc.title)
    ),

    React.createElement("div", { className: "flex shrink-0 items-center gap-3" },
      React.createElement("div", {
        role: "group",
        "aria-label": doc.languageLabel,
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
      ),
      React.createElement("button", {
        type: "button",
        onClick: () => onClose(),
        className: "border border-border bg-panel px-3.5 py-1.5 font-mono text-[11px] uppercase tracking-[0.16em] text-text transition-colors hover:border-accent hover:text-accent focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-accent" },
      doc.closeLabel)
    )
    ),

    // ---- Body: index rail + reading column ----
    React.createElement("main", {
      className: "grid flex-1 grid-cols-1 lg:grid-cols-[minmax(0,16rem)_minmax(0,1fr)]" },

    React.createElement("aside", { className: "border-b border-border px-5 py-8 sm:px-10 lg:border-b-0 lg:border-r" },
      React.createElement("div", { className: "lg:sticky lg:top-8" },
        React.createElement("p", { className: railLabel }, doc.indexTitle),
        React.createElement("nav", { className: "mt-4", "aria-label": doc.indexTitle },
          React.createElement("ul", { className: "space-y-0.5" },
            INDEX.map((item, index) =>
              React.createElement("li", { key: item.id },
                React.createElement("a", {
                  href: '#' + item.id,
                  onClick: (event) => goTo(event, item.id),
                  className: indexItem + " text-[11px] uppercase tracking-[0.16em] text-muted" },
                React.createElement("span", { className: "font-mono text-[10px] text-muted/70" },
                  '0' + (index + 1)),
                item.label)
              )
            )
          )
        )
      )
    ),

    React.createElement("div", { className: "space-y-9 px-5 py-8 sm:px-10" },

      React.createElement("p", { className: "max-w-[74ch] text-[13px] leading-relaxed text-muted" }, doc.intro),

      // ---- Overview: data path ----
      React.createElement("div", { id: "guide-overview", className: "scroll-mt-6" },
        React.createElement("h2", { className: "border-b border-border pb-2 font-mono text-[11px] uppercase tracking-[0.22em] text-muted" },
          doc.topology.title),
        React.createElement("div", { className: "mt-5 max-w-[38rem]" },
          doc.topology.nodes.map((node, index) =>
            React.createElement(React.Fragment, { key: node.label },
              React.createElement("div", {
                className: "border px-3.5 py-2.5 " +
                  (index === 1 ? "border-accent/50 bg-panel" : "border-border bg-panel/50") },
              React.createElement("p", { className: "font-mono text-[12px] text-text" }, node.label),
              React.createElement("p", { className: "mt-0.5 text-[11.5px] text-muted" }, node.detail)
              ),
              index < doc.topology.nodes.length - 1 &&
              React.createElement("p", { className: "py-1 text-center font-mono text-[11px] text-muted/60", "aria-hidden": "true" }, "\u2193")
            )
          ),
          React.createElement("p", { className: "mt-3 text-[11.5px] leading-relaxed text-muted/80" },
            doc.topology.caption)
        )
      ),

      // ---- Environment variables ----
      React.createElement(GuideSection, { id: "guide-env", title: doc.envTitle },
        React.createElement("div", { className: "border border-border" },
          React.createElement("div", {
            className: "hidden border-b border-border bg-panel/50 px-3.5 py-2 sm:grid sm:grid-cols-[13rem_11rem_minmax(0,1fr)] sm:gap-4" },
            React.createElement("p", { className: railLabel + " text-[10px]" }, doc.envHeader.name),
            React.createElement("p", { className: railLabel + " text-[10px]" }, doc.envHeader.value),
            React.createElement("p", { className: railLabel + " text-[10px]" }, doc.envHeader.description)
          ),
          doc.env.map((row, index) =>
            React.createElement("div", {
              key: row[0],
              className: "flex flex-col gap-1 px-3.5 py-3 sm:grid sm:grid-cols-[13rem_11rem_minmax(0,1fr)] sm:items-baseline sm:gap-4 " +
                (index > 0 ? "border-t border-border" : "") },
            React.createElement("code", { className: "font-mono text-[12px] text-text" }, row[0]),
            React.createElement("code", { className: "font-mono text-[12px] text-muted" }, row[1]),
            React.createElement("span", { className: "text-[12.5px] leading-relaxed text-muted" }, row[2])
            )
          )
        )
      ),

      // ---- Steps ----
      React.createElement(GuideSection, { id: "guide-steps", title: doc.stepsTitle },
        doc.steps.map((step) =>
          React.createElement("article", { key: step.n, className: "border-t border-border pt-6 first:border-t-0 first:pt-0" },
            React.createElement("div", { className: "grid gap-2 sm:grid-cols-[3rem_minmax(0,1fr)] sm:gap-4" },
              React.createElement("p", { className: "font-mono text-[11px] uppercase tracking-[0.16em] text-muted" },
                '0' + step.n),
              React.createElement("h3", { className: "text-[14px] font-semibold leading-snug text-text" },
                step.title)
            ),
            React.createElement("div", { className: "mt-4 space-y-3.5 sm:pl-[4rem]" },
              step.blocks.map((block, index) =>
                React.createElement(GuideBlock, { key: index, block: block })
              )
            )
          )
        )
      ),

      // ---- Troubleshooting ----
      React.createElement(GuideSection, { id: "guide-troubleshooting", title: doc.troubleshootingTitle },
        React.createElement("div", { className: "border border-border" },
          doc.troubleshooting.map((row, index) =>
            React.createElement("div", {
              key: row[0],
              className: "px-3.5 py-3 " + (index > 0 ? "border-t border-border" : "") },
            React.createElement("p", { className: "font-mono text-[12px] text-danger/80" }, row[0]),
            React.createElement("p", { className: "mt-1 max-w-[74ch] text-[12.5px] leading-relaxed text-muted" }, row[1])
            )
          )
        ),
        React.createElement("p", { className: "text-[11.5px] leading-relaxed text-muted/80" },
          doc.sourcesNote + ' ',
          doc.sources.map((source, index) =>
            React.createElement("span", { key: source },
              React.createElement("code", { className: "font-mono text-[11.5px] text-muted" }, source),
              index < doc.sources.length - 1 ? ' \u00B7 ' : ''
            )
          )
        )
      )
    )
    ),

    // ---- Bottom rail ----
    React.createElement("footer", {
      className: "mt-auto flex h-10 shrink-0 items-center border-t border-border px-5 sm:px-10" },
    React.createElement("p", { className: "font-mono text-[10.5px] uppercase tracking-[0.16em] text-muted/70" },
      doc.securityNote)
    )
  )
  );
};
window.SetupGuide = SetupGuide;
