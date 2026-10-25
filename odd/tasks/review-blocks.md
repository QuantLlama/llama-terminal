# Native review: the remaining blocks

One review of the whole day was rejected with `lens_context_budget_exceeded`: 46
files do not fit the reviewer context budget, and the provider says retrying that
same candidate can never succeed. The day is therefore reviewed block by block,
each one a separate transaction.

Base for every block: `2c42e1a` is the day's starting commit; each block's own
base is the commit before it.

| # | Block | Range (HEAD side) | Files | State |
| --- | --- | --- | --- | --- |
| 1 | Storage (SQLite + migration + untracking) | `d78c6bf..8e6b9c3` | 9 | **Reviewed.** Lineage `review-49372652ebefae16`, high, 4 lenses + refuter: two CRITICAL introduced defects found (datetime vs TEXT made the copy non-idempotent; a key covering every column produced `UPDATE ... SET  WHERE ...`). Both fixed in `4672c08`, 640 tests green, real double run shows 20 skipped. Closing the transaction is blocked by the provider, which emits a correction-plan binding and then rejects it as stale after the committed-only target changed. |
| 2 | Crypto feed and tape/DOM | `2c42e1a..ff8a588^` | `src/live/crypto_public_connector.py`, `src/services/market_data_engine/engine.py`, 2 test files | Pending. Watch the failure counter, the adaptive cadence bounds, and that the public connector is never stored where a tenant connector is expected. |
| 3 | Training pipeline | subprocess shadowing, torch, yfinance, Yahoo symbols, period caps | `main.py`, `loader.py`, `yahoo_symbols.py`, `train.py`, `Dockerfile`, requirements | Pending. |
| 4 | MT5 bridge token + futures contract resolver | `mt5_api_connector.py`, `futures_contract.py` | | Pending. |
| 5 | Ops (units, relays, tunnel) | `deploy/`, `scripts/*.sh` | | Pending. |
| 6 | Dependencies and desktop | Electron, requirements, `electron/main.js` | | Pending. |

## How to start one block

```bash
# base = the commit before the block, full 40-char id
gentle_review assess   {"baseRef": "<base>", "committedOnly": true}
gentle_review inspect
gentle_review start    {"mode": "ordinary", "baseRef": "<base>", "committedOnly": true}
gentle_review status   {"lineageId": "<lineage>"}
# then capture the lens group (forecast first, then acknowledged), the refuter, and
# if a correction is required: apply it, COMMIT it, and only then capture the plan.
```

## Rules learned the hard way

1. **Never commit while a review is open.** It moves the reviewed scope, forces a
   recovery, and the correction-plan binding goes stale.
2. **Split before starting.** If the diff is larger than roughly 10 files or a few
   thousand lines, expect `lens_context_budget_exceeded` and cut the block first.
3. **A correction in `committedOnly` mode must be committed** before the plan is
   captured, but the provider may then reject the plan it just offered because the
   target identity moved. Capture the plan first when the mode allows it; otherwise
   record the finding as fixed and close the block in the next session.
