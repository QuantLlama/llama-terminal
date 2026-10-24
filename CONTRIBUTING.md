# Contributing to llama-terminal

Thanks for taking the time to contribute. This document describes how work reaches
`main`. It is intentionally short: issues first, small pull requests, tests with the
behavior, English artifacts.

## Before you start

- **Bug?** Open a bug report issue. Include the version, the surface (desktop, browser
  mode, trainer, API) and the data source.
- **Feature?** Open a feature request and describe the problem before the solution. A
  feature is agreed before it is implemented; a surprise pull request for a large
  feature may be closed.
- **Security defect?** Do not open a public issue. Follow [SECURITY.md](SECURITY.md).
- **Question?** Read [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md) first.

## Development environment

The full setup — Python virtual environments, Node, native dependencies, the MT5 bridge
and how to run each mode — lives in [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md).

The short version:

```bash
./setup_env.sh          # Linux/macOS · use setup_env.bat on Windows
npm install
source venv_linux/bin/activate
python run.py           # Terminal app · Browser mode · Trainer CLI
python -m pytest tests -q
```

## Workflow

1. **Issue.** Every behavior change starts from an issue. Link it from the pull request.
2. **Branch.** Branch from `main` with a type prefix:
   `feat/`, `fix/`, `docs/`, `perf/`, `refactor/`, `test/`, `ci/`, `chore/`.
   Example: `fix/mt5-bridge-reconnect`.
3. **Commit.** [Conventional Commits](https://www.conventionalcommits.org/):
   `type(scope): imperative summary`.
   Types: `feat`, `fix`, `docs`, `test`, `refactor`, `perf`, `build`, `ci`, `chore`.
   Scopes used in this repository: `mt5`, `crypto`, `api`, `engine`, `algo`, `ml`,
   `web`, `electron`, `deploy`, `docs`, `repo`.
4. **Pull request.** Use the pull request template. One behavior per pull request.
   Keep the diff reviewable — around 400 changed lines is the practical ceiling; split
   larger work into chained pull requests.
5. **Review.** `CODEOWNERS` is requested automatically. CI must be green and the
   conversation resolved before merge.
6. **Merge.** Squash merge into `main`. The pull request title becomes the commit
   subject, so it must follow Conventional Commits too.

## Tests

Behavior changes ship with tests. This is not optional for anything that can move money,
read a broker account, persist state or serve an HTTP/WebSocket route.

```bash
python -m pytest tests -q                 # full suite
python -m pytest tests/test_mt5_bridge_auth.py -q   # one module
```

Guidelines:

- Assert the observable effect, not the implementation detail: exit codes, HTTP
  responses, emitted values, persisted state.
- Cover the boundaries and error paths the change introduces.
- A test that would pass with the change reverted does not test the change.
- Never write a test that depends on live market data, a live broker session or a real
  credential. Use fixtures and fakes.

## Documentation

When you change a command, an option, an endpoint, a configuration key or an error
message, update the documentation that describes it:

- `README.md` — what the product is and how to run it
- `docs/ARCHITECTURE.md` — components and data flow
- `docs/DEVELOPMENT.md` — setup, running modes, troubleshooting
- `docs/TESTING.md` — test strategy and how to run each suite
- `docs/ML-PIPELINE.md` — features, models, training
- `docs/ROADMAP.md` — what is planned
- `CHANGELOG.md` — user-visible changes

## Language and style

- **Repository artifacts are written in English**: code, comments, docstrings, commit
  messages, issues, pull requests, documentation and UI copy.
- Python targets 3.11+. Use type hints on public functions, `logging` over `print`, and
  keep functions small enough to test.
- Do not commit credentials, tokens, account numbers or logs containing them. `.env`,
  `*.key`, `.crypto_key`, `.mt5_key`, `*.db` and `*.log` are ignored for a reason.

## Trading-specific rules

This platform can place real orders. Any change touching execution, sizing, risk limits
or order state must state that explicitly in the pull request and must not be merged
without a test that fails when the guard is removed.

## License

By contributing you agree that your contribution is licensed under the [MIT
License](LICENSE).
