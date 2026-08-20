<Proposal: crypto-liquidity-heatmap>
## Intent
The liquidity heatmap in crypto mode currently does not auto-update due to a lack of L2 websockets and reliance on backend OHLCV that is only fetched on load. This change will implement smart incremental fetching to auto-update the heatmap without relying on websockets.

## Scope
### In Scope
- Fetching 10,000 bars initially for full history.
- Incrementally fetching 200 bars exactly on `localLastCandleTime` (candle close).
- Merging new data in `LiquidityHeatmapOverlay.js`.
- Increasing the internal buffer limit to 20,000.

### Out of Scope
- Implementing L2 websockets.
- Pixel-perfect mathematical rendering over performance.
- Fetching the entire history on every update.

## Capabilities
### New Capabilities
- `crypto-liquidity-heatmap`: Auto-updating liquidity heatmap relying on smart incremental fetching of backend OHLCV on candle close.

### Modified Capabilities
- None

## Approach
Implement a Smart Incremental Fetching strategy:
1. On initial load, fetch 10,000 bars to populate the full history, accepting a 1-2 second delay.
2. Monitor `localLastCandleTime` and trigger an incremental fetch of 200 bars on candle close.
3. Update `LiquidityHeatmapOverlay.js` to correctly merge the new incrementally fetched bars with the existing data.
4. Increase the internal chart data buffer size to 20,000 to accommodate the expanded historical context and new incoming data.

## Affected Areas
| Area | Impact | Description |
|------|--------|-------------|
| `LiquidityHeatmapOverlay.js` | Modified | Implement merge logic and increase buffer limit to 20,000. |
| Chart Data Fetching / Component | Modified | Add initial 10k bar fetch and incremental 200 bar fetch on candle close. |

## Risks
| Risk | Likelihood | Mitigation |
|------|------------|------------|
| Initial load delay impacts UX | Low/Med | Display a loading state or skeleton while fetching the initial 10,000 bars. |
| Duplicated data points on merge | Low | Ensure merge logic strictly uses timestamp deduplication. |

## Rollback Plan
Revert changes to `LiquidityHeatmapOverlay.js` and the chart fetching logic back to the previous static "fetch on load" implementation and restore original buffer limits.

## Dependencies
- Backend OHLCV data endpoint must support limit query parameters (e.g., 10,000 and 200).

## Success Criteria
- [ ] Heatmap auto-updates at each candle close automatically.
- [ ] Initial history displays 10,000 bars.
- [ ] No noticeable performance degradation occurs upon incremental updates (chart remains fluid).
