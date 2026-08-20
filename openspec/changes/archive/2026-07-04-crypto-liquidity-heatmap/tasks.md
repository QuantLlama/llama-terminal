# Tasks: crypto-liquidity-heatmap

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | ~60-80 lines |
| 400-line budget risk | Low |
| Chained PRs recommended | No |
| Suggested split | Single PR |
| Delivery strategy | ask-on-risk |
| Chain strategy | pending |

Decision needed before apply: No
Chained PRs recommended: No
Chain strategy: pending
400-line budget risk: Low

### Suggested Work Units

| Unit | Goal | Likely PR | Notes |
|------|------|-----------|-------|
| 1 | Implement smart fetching & merging | PR 1 | Base branch; tests included |

## Phase 1: ChartComponent Fetching Logic

- [x] 1.1 In `src/platform/web/components/ChartComponent.js`, introduce an `isInitialHeatmapLoad` state or ref (defaulting to `true`).
- [x] 1.2 Modify `fetchLiquidityHeatmap` to dynamically set `limit=10000` for the initial fetch and `limit=200` for subsequent incremental fetches.
- [x] 1.3 Add `localLastCandleTime` to the dependency array of the heatmap fetching `useEffect` so it triggers on candle close.
- [x] 1.4 Update the state/ref `isInitialHeatmapLoad` to `false` after the first successful initial fetch.

## Phase 2: Heatmap Overlay Merging & Buffer Limit

- [x] 2.1 In `src/platform/web/components/LiquidityHeatmapOverlay.js`, rewrite the `useEffect` merge logic to use timestamp-based deduplication (convert incoming `data` to a `Map` keyed by `.time`).
- [x] 2.2 Ensure incoming data points overwrite any existing points in the internal `liveMap` with the same timestamp.
- [x] 2.3 Sort the merged data points by timestamp.
- [x] 2.4 Update the buffer capacity check to slice/truncate to `20000` instead of the previous limit (e.g., 5000).

## Phase 3: Testing & Verification

- [x] 3.1 Write unit tests for `LiquidityHeatmapOverlay.js` to ensure the timestamp deduplication merges overlapping times, prioritizes incoming data, and respects the 20,000 capacity.
- [x] 3.2 Write integration tests for `ChartComponent.js` to verify it calls the `/api/indicators/calculate` endpoint with `limit=10000` on load and `limit=200` when `localLastCandleTime` updates.
