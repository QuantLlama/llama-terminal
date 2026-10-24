# Repository professionalization — llama-terminal

Turn `QuantLlama/Plataforma_LamaTerminal_V0.1.7b` into a release-ready, English-language,
recruiter-facing open-source project, and ship a custom GitHub profile README for the
`QuantLlama` account. Branch: `chore/repo-professionalization`.

## Specs

- **S1** — User: *"nesecit que este repositorio este al altura de un repo profesinal"*. The repo
  must meet the baseline of a professional OSS repository: README, docs, license, contributing,
  code of conduct, security policy, changelog, issue/PR templates, CI, CODEOWNERS.
- **S2** — User: *"que nos aseguremos que todo este en ingles. documantado"*. Decision (L2-Q4):
  English scope is **README + docs/ only** — `README.md`, everything under `docs/`, and
  `deploy/*.md` as a consistency follow-up. Code comments, identifiers, and UI strings are out of
  scope for this feature.
- **S3** — User: *"que siemrle se hagan issus, pr, accition todo lo que realmente un repo tiene que
  tener"*. Issue templates, PR template, CI workflow(s), conventional commits, labels, milestones,
  and a real PR that carries this work. "accition" = CI/CD automation (interpreted as GitHub
  Actions + Dependabot).
- **S4** — User: *"porque la idea es liberar el proyecto"*. The repo must be *release-ready*.
  Decision (L2-Q1): **do not flip visibility now**; prepare everything and let the owner publish.
  No push-to-public, no release publication, no tag creation in this feature.
- **S5** — User: *"presentarlo a mis reculetr como un proyecto de grtan escala demostrando mis
  conocimientos como ingeniero en sistema desarrollador full stck y data sciencia"*. The
  documentation must make the scale visible: system architecture, data flow, ML pipeline,
  risk/execution engine, deployment topology, testing strategy, ADRs.
- **S6** — User: *"quiero que mejores al 100% mi perfil de github que sea uno de los mejores que
  tenga diesño propio"*. A profile README on the `QuantLlama` account (L2-Q3) with custom
  design (own SVG banner/badges, not an off-the-shelf template dump).
- **S7** — User: *"te dejo mi web para que veas a que me dedico
  https://pabloezmoscardo.nbmsystemas.com/"*. Positioning source of truth: Information Systems
  Engineer & Full Stack Developer, 20+ years, Rafaela Argentina, remote; stack includes
  full stack, DevOps, AI/LLM, security, algorithms, algorithmic trading.
- **S8** — User: *"tambien quiero que pongas mi segundo githubel de nbmsystemas"*. Cross-link the
  `nbmsystemas` account (https://github.com/nbmsystemas, https://nbmsystemas.com) from the
  `QuantLlama` profile README and from the repository.
- **S9** — Decision (L2-Q2): rename the repository to **`llama-terminal`**.

## Tasks

| ID | Spec | Task | Route | Commit |
| --- | --- | --- | --- | --- |
| T1 | S1, S3 | `.github/` governance: issue templates (bug/feature/config), PR template, CODEOWNERS, `.editorconfig`, `.gitattributes` | inline | `chore(repo): add issue, PR and editor conventions` |
| T2 | S1, S2, S5, S7, S8 | Rewrite `README.md` in English: positioning, badges, architecture diagram, features, screenshots, stack, quickstart, testing, deployment, roadmap, contributing | inline | `docs(readme): rewrite the project README in English` |
| T3 | S1, S2, S5 | `docs/`: `ARCHITECTURE.md`, `DEVELOPMENT.md`, `TESTING.md`, `ML-PIPELINE.md`, `ROADMAP.md`, `adr/`; translate `docs/RELEASES/v1.8.1.md` to English | inline (architecture map from explore subagent) | `docs: document architecture, development, testing and ML pipeline` |
| T4 | S1, S2 | `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`, `SECURITY.md`, `CHANGELOG.md`, `.github/FUNDING` if applicable | inline | `docs(governance): add contributing, conduct, security and changelog` |
| T5 | S3 | `requirements.ci.txt`, `.github/workflows/ci.yml` (pytest + syntax/lint gates), `.github/dependabot.yml` | inline | `ci: run the test suite on every pull request` |
| T6 | S4, S8, S9 | Repo metadata: description in English, homepage, topics; rename to `llama-terminal`; create labels, milestones and roadmap issues | inline (`gh`) | no commit (GitHub metadata) |
| T7 | S3 | Open the PR carrying T1–T5 against `main`, linked to the roadmap issues | inline (`gh`) | PR only |
| T8 | S6, S7, S8 | `QuantLlama/QuantLlama` profile repo: custom SVG banner + README in English, featured work, stack, cross-link to `nbmsystemas` | inline | commit in `QuantLlama/QuantLlama` |

## Log

### L1 — original request (verbatim)

> nesecit que este repositorio este al altura de un repo profesinal, que nos aseguremos que todo
> este en ingles. documantado, que siemrle se hagan issus, pr, accition todo lo que realmente un
> repo tiene que tener, porque la idea es liberar el proyecto,.y aparte presentarlo a mis reculetr
> como un proyecto de grtan escala demostrando mis concimientos como ingeniero en sistema
> desarrollador full stck y data sciencia,. este sera mi caballito de guerra no puedo quedar mal en
> este tambien quiero que mejores al 100% mi perfil de github que sea uno de los mejores que tenga
> diesñio propio y te dejo mi web para que veas a que me dedico
> https://pabloezmoscardo.nbmsystemas.com/ y tambien quiero que pongas mi segundo githubel de
> nbmsystemas.-

### L2 — decisions answered by the owner (verbatim)

- Q1 visibility → *"Preparar todo y dejarlo privado"*
- Q2 repository name → *"llama-terminal"*
- Q3 profile account → *"QuantLlama (perfil principal)"*
- Q4 English scope → *"Solo README y docs/"*

### L3 — evidence (baseline before this feature)

- `venv_linux/bin/python -m pytest tests -q` → `53 passed, 1 warning in 33.88s`.
- Repo has no `.github/`, no issues, no pull requests, private visibility, Spanish description, no
  homepage URL.
- `deploy/COOLIFY.md` and `deploy/MT5_BRIDGE.md` were already written in English; `docs/RELEASES/v1.8.1.md`
  is Spanish.

### L4 — delivery strategy and slice boundaries

Delivery strategy: **single PR** (solo maintainer, private repo, no release in this feature).
Review budget: the PR exceeds the ~400-line guideline because repository scaffolding is mostly
prose (templates, ADRs, governance). Slices, each a commit:

1. `chore(repo)` — governance templates, 461 lines.
2. `docs(governance)` — contributing, conduct, security, changelog, 377 lines.
3. `docs(readme)` — README rewrite + screenshot asset move.
4. `docs` — architecture, development, testing, ML, roadmap, ADRs, release-note translation.
5. `ci` — workflow, minimal CI requirements, dependabot, link checker, pytest.ini.

### L5 — scope deviations (owner should know)

- The previous README claimed `Transformers` and `XGBoost` as active ML components. Neither is
  imported anywhere (`git grep`), so the English README states the pipeline that actually runs
  (LSTM + random forest + ARIMA/Gaussian-process diagnostics + DEAP search). Accuracy over
  marketing: an interviewer will ask.
- `.env.example` could not be created (harness blocked writes to that path); the environment
  variables are documented as a table in `docs/DEVELOPMENT.md` instead.
- English scope stayed at README + `docs/` as decided (L2-Q4). Non-English code comments remain;
  `docs/ROADMAP.md` lists the follow-ups.
