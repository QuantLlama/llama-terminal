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
- **S4** — User: *"lo de la guia completa no me gusta ese modal que abre tiene que ser algoo mas
  porfesional no asi"*. The setup guide the login links to must be a full-surface documentation
  view: its own screen with a step index and a reading column, in the same visual language as the
  login, in both languages, and without the generated-looking illustration set.
- **S5** — User: *"y le falta un poco mas de tamaño a todo quedo muy pequeño tampoco muy grande pero
  mejor propocion por favor"*. The login scale must be comfortable but not oversized: body copy,
  labels, controls and headings sized for reading at arm's length, with proportions that hold at
  both wide and narrow widths.

## Decisions taken

| Question | Answer |
| --- | --- |
| i18n scope | Login and its help only, with a language switch. The rest of the app stays as it is |
| Initial language | Detected from the browser, remembered in `localStorage` |
| Setup guide shape | Full-surface documentation view, chosen over a flat modal and over removing the guide |
| Setup guide figures | The inline SVG illustrations are replaced by flat HTML structure: their text cannot be translated and they are the most template-like part |

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

| ID | Spec | Task | Route | Commit |
| --- | --- | --- | --- | --- |
| T1 | S2 | Minimal i18n: a `login.*` dictionary for `es` and `en`, browser detection, `localStorage` memory, and a compact `ES / EN` switch that does not shift layout | inline + TDD | `4e01603` |
| T2 | S1, S3, S5 | Redesign `LoginModal.js` and the login surface in `index.html` following the direction above, at a readable scale, keeping the existing auth flow untouched | inline | `8c808f9` |
| T3 | S2 | Help text (what the platform is, requirements, first steps, bridge note) in both languages | inline | with T2 |
| T4 | S1, S5 | Verify both languages, keyboard navigation and focus states, and that the layout does not break at narrow widths | inline | evidence below |
| T5 | S2, S4 | Rebuild `SetupGuide.js` as a full-surface bilingual documentation view with the login's visual language | inline + TDD on the content | `846a2b5` |

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
- Every component script in `index.html` carries a `?v=` query. Bump it for the file you change,
  otherwise Electron serves the previous build and the redesign never shows up.

## Log

- **L1** — User: *"lo que me gustaria es que en el login sea mas profesinal no tan creado con IA el
  diseño, y sobre todo que la ayuda y todo tambien este en español e ingles me gustara que
  mejoremos eso a un estilo super profesional como las landig y plataforma profesionales como ATAS
  y esas otras"*.
- **L2** — User: *"lo de la guia completa no me gusta ese modal que abre tiene que ser algoo mas
  porfesional no asi"*. Decision: replace the modal with a full-surface documentation view.
- **L3** — User: *"y le falta un poco mas de tamaño a todo quedo muy pequeño tampoco muy grande pero
  mejor propocion por favor"*. Decision: raise the login scale one step across labels, copy,
  controls and headings.
- **L4** — Evidence: `build/obf_src/src/platform/web/components/LoginModal.js` is a May build, so a
  packaged or cached copy can serve the old login. Every script tag carries `?v=`; bumping it is
  part of the change.
- **L5** — Evidence: `npx jest --roots ./src` → 7 suites, 55 tests, all green. Per suite: loginI18n
  14, setupGuideContent 6, LoginModal 18, SetupGuide 12, plus the three pre-existing overlay suites.
- **L6** — Evidence: rendered in headless Chrome through a scratch harness outside the repository.
  Login at 1440x900 in `es` and `en`, login at 390x844, guide at 1440x900 in `es` and `en` and at
  390x844: no horizontal overflow, one column below `lg`, the switch keeps both labels on screen,
  and both languages read the same scale. Two defects were found this way and fixed: sections that
  collided in the guide, and a guide title collapsing to nothing at 390px.
- **L8** — Evidence, and a process miss: CI failed on the first push. `tests/test_login_and_guide.py`
  asserts the *source shape* of both components (literal copy, `lg:grid-cols-2`, inline SVG, the
  modal's backdrop). Moving the copy into the dictionaries and turning the modal into a full screen
  broke 18 of them. The JS suite could not see this: it tests behaviour, not source shape. The rules
  are now asserted against the file that owns them (component renders the key, every language
  defines it). Never ship a change to these two components without running
  `python -m pytest tests/test_login_and_guide.py`.
- **L9** — Evidence, second review (candidate: the six commits after `414399e`). Reached `approved`
  through readability + reliability reviewers, one refuter and one targeted validator. The refuter
  caught a CRITICAL finding I introduced: to satisfy the retargeted Python contract I had replaced
  `(sin definir)` with the English `(unset)` in the Spanish dictionary and then written the test to
  demand the English literal in every language, which hid the translation regression behind the very
  test meant to protect it. Fixed in `17c89d0`; each language is now held to its own placeholder.
  Lesson: a test written to satisfy CI can encode the defect it should catch.
- **L7** — Delivery slices on `feat/login-redesign`: `4e01603` dictionaries (i18n only), `8c808f9`
  login surface, `846a2b5` setup guide, `53669b0` review findings, `63b908d` contract tests, `17c89d0` review correction. Each
  slice carries its tests and its `?v=` bump, so every commit is loadable on its own.
