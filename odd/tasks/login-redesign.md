# Login redesign and bilingual login/help

The login is the first thing a user sees and it reads as generic. It is also
Spanish-only. Branch: `feat/login-redesign`.

## Specs

- **S1** — User: *"lo que me gustaria es que en el login sea mas profesinal no tan creado con IA el
  diseño"*. The login must look like a professional trading platform, not a generated template.
- **S2** — User: *"sobre todo que la ayuda y todo tambien este en español e ingles"*. The login and
  its help text exist in both languages.
- **S3** — User: *"me gustara que mejoremos eso a un estilo super profesional como las landig y
  plataforma profesionales como ATAS y esas otras"*. Visual reference: ATAS and similar
  professional trading terminals.

## Decisions taken

| Question | Answer |
| --- | --- |
| i18n scope | Login and its help only, with a language switch. The rest of the app stays as it is |
| Initial language | Detected from the browser, remembered in `localStorage` |

## Direction

ATAS and comparable terminals look dense and technical, not decorative:

- Dark, low-contrast surfaces; one accent colour used sparingly for the action.
- Tight, consistent typography with small uppercase labels and letter spacing, like the
  existing header (`text-[10px]`, `tracking-wider`).
- No gradients, no floating illustration, no oversized rounded cards, no emoji.
- Information hierarchy over ornament: brand and version, the form, the session state, the
  help, and the language switch, each with a clear weight.
- Space used deliberately: a narrow column on a large surface, not a centred card floating in
  emptiness.

## Tasks

| ID | Spec | Task | Route |
| --- | --- | --- | --- |
| T1 | S2 | Minimal i18n: a `login.*` dictionary for `es` and `en`, browser detection, `localStorage` memory, and a compact `ES / EN` switch that does not shift layout | inline + TDD |
| T2 | S1, S3 | Redesign `LoginModal.js` and the login surface in `index.html` following the direction above, keeping the existing auth flow untouched | inline |
| T3 | S2 | Help text (what the platform is, requirements, first steps, bridge note) in both languages | inline |
| T4 | S1 | Verify both languages, keyboard navigation and focus states, and that the layout does not break at narrow widths | inline |

## Technical notes for the next session

- The login component is `src/platform/web/components/LoginModal.js` (258 lines) and it is
  mounted from `index.html` around line 4888: `React.createElement(window.LoginModal, {...})`
  when there is no session. `src/platform/web/components/Header.js` is dead code.
- The design tokens already exist: `text-muted`, `border`, `bg-black/50`, `text-accent`,
  `bg-success`, `bg-danger`. Use them instead of new colours.
- The auth flow to respect: `supabase.auth.signInWithPassword`, `window.authFetch` for
  per-user routes, and the four places startup restores a session from (see
  `odd/tasks/review-blocks.md` and the sign-out commit `7c483ea`).
- No new dependency. The page loads React and Babel in the browser; a plain dictionary object
  is enough for two languages.
