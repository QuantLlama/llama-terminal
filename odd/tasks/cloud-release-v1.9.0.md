# Cloud mode documentation and v1.9.0 release

Document the cloud runtime end to end, publish v1.9.0, and make the MT5/cloud
integration story legible to users and to a reviewer. Branch: `chore/repo-professionalization`
(continues the open PR).

## Specs

- **S1** — User: *"no se si seria una release de todo lo ultimo que hicimos ahora que ahora el
  sistema se peude utilziar desde la nube"*. Publish a real release: version bump, release notes,
  changelog, annotated tag, GitHub Release.
- **S2** — User: *"como se usa tendriamos que tener un grafico o todo bien detallado de como
  funciona ahora la plataforma en modo cloud"*. A dedicated cloud-mode document with a diagram,
  operating instructions and the limits of the deployment.
- **S3** — User: *"para que los usarios se enteren de estas nuevas futres o releases"*. Release
  notes reachable from the repository front page and from the Releases page.
- **S4** — User: *"si un reculetere lo ve seapa com ose implemeto soluciono problemas para poder
  conectarlo con mt5 y demas que sea algo profesional para que quede registrado en nuestro repo"*.
  A problem → cause → solution record of the integration work, kept in the repository (document +
  ADR + issue links), not in chat.

## Tasks

| ID | Spec | Task | Route | Commit |
| --- | --- | --- | --- | --- |
| T1 | S2, S4 | `docs/CLOUD.md` + `docs/images/cloud-topology.svg`: components, request paths, environment matrix, persistence, security model, operations, and the six integration problems with cause and fix | inline | `docs: document the cloud runtime end to end` |
| T2 | S1, S3 | `docs/RELEASES/v1.9.0.md`, `CHANGELOG.md` 1.9.0 section, `package.json` version | inline | `docs(release): prepare v1.9.0` |
| T3 | S3 | README: cloud mode in the feature list, cloud doc in the index, "what's new" pointer | inline | folded into T2 |
| T4 | S2, S4 | Fix the stale statement in `deploy/COOLIFY.md` (bridge has no auth) and cross-link the new document | inline | folded into T1 |
| T5 | S1, S3 | CI green, merge PR #13, tag `v1.9.0`, publish the GitHub Release with the notes | inline (`gh`) | tag + release |

## Log

### L1 — original request (verbatim)

> otra cosa que tenemos que hacer no se si seria una release de todo lo ultimo que hicimos ahora que
> ahora el sistema se peude utilziar desde la nube y como se usa tendriamos que tener un grafico o
> todo bien detallado de como funciona ahora la plataforma en modo cloud.- para que los usuarios se
> enteren de estas nuevas futres o releases, y aparte si un reculetere lo ve seapa com ose implemeto
> soluciono problemas para poder conectarlo con mt5 y demas que sea algo profesional para que quede
> registrado en nuestro repo

### L2 — evidence gathered before writing

- Live deployment answers: `https://llama.nbmsystemas.com/health` → `200 application/json`,
  `/` → `200 text/html`.
- Coolify app `quantum-llama-web` on branch `feature/coolify-deploy`, domain
  `https://llama.nbmsystemas.com`, Dockerfile build, port `8050`, health `GET /health`.
- `deploy/COOLIFY.md` still says *"The current `mt5_server.py` has no auth layer"* — stale since
  `feat(mt5): authenticate and configure the remote bridge` (commit `13ff331`) and the auth tests.
- `mt5_server.py` now has `GZipMiddleware` plus `require_bridge_token` middleware;
  `src/live/mt5_bridge_auth.py` resolves bind address and token.
- VPS relays exist as scripts (`deploy/vps/setup-mt5-relay.sh`,
  `setup-crypto-proxy-relay.sh`), not as committed compose files.

### L3 — release decision

- Version: **1.9.0** (minor). The cloud capability is additive; nothing was removed and no
  configuration format changed.
- The API's `VERSION`/`STABLE_VERSION` constants stay at `2.4.0` in this release: changing a value
  old clients compare against is a contract decision, and it is already tracked as issue #8.
- Merge of PR #13 is part of publishing: a release must point at a tagged commit on `main`.
