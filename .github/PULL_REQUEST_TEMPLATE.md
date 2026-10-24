<!--
  Keep pull requests small and reviewable. A reviewer should be able to
  understand the diff in one sitting (~400 changed lines is the practical cap).
-->

## What does this change

<!-- One paragraph. What behavior changes, and for whom. -->

## Why

<!-- Link the issue this closes. If there is no issue, explain the problem first. -->

Closes #

## Scope

- [ ] Behavior change
- [ ] Refactor without behavior change
- [ ] Tests only
- [ ] Documentation only
- [ ] Build, CI or deployment
- [ ] Dependencies

## Affected areas

<!-- Tick everything the diff touches. -->

- [ ] Market data / connectors (`src/live`, `src/services/market_data_engine`, `mt5_server.py`)
- [ ] Order execution and risk (`src/services/order_gateway`, `src/engine/core/risk_manager.py`)
- [ ] Trading engine, strategies, backtesting (`src/engine`, `src/algorithms`)
- [ ] Indicators and order flow (`src/indicators`, `src/engine/indicators`)
- [ ] ML and training (`train.py`, `src/models`, `src/features`)
- [ ] API and web surface (`src/platform`)
- [ ] Desktop shell (`electron`, `nsis`)
- [ ] Packaging, deployment (`Dockerfile`, `deploy/`, `build_dist.py`, `scripts/`)
- [ ] Documentation

## How it was verified

<!-- Commands you actually ran and their result. "Tests pass" is not evidence. -->

```text
$ python -m pytest tests -q
53 passed
```

## Risk

<!--
  State the highest-risk consequence of this diff, or "Risk: none".
  Call out explicitly any change that touches live trading, credentials,
  stored data, public interfaces or deployment.
-->

- [ ] This change can place, modify or cancel real orders
- [ ] This change touches credentials, keys or authentication
- [ ] This change writes or migrates stored data
- [ ] This change alters a public interface (HTTP, WebSocket, CLI, config format)
- [ ] Risk: none of the above

## Reviewer notes

<!-- Where should the reviewer look first? What is intentionally out of scope? -->

## Checklist

- [ ] The change is focused: one behavior, one work unit
- [ ] Tests cover the new or changed behavior
- [ ] Documentation and help text describe the change
- [ ] No credentials, tokens, keys or customer data in the diff
- [ ] Commit messages follow Conventional Commits
