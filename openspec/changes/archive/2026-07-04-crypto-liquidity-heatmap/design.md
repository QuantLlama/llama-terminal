<Design: crypto-liquidity-heatmap>
## Technical Approach
Implement smart incremental fetching for the crypto liquidity heatmap. Initially, `ChartComponent.js` will fetch a full history of 10,000 bars. Upon receiving updates via `localLastCandleTime` (indicating a candle close), it will trigger an incremental fetch of 200 bars. `LiquidityHeatmapOverlay.js` will merge this new data with its internal buffer using timestamp-based deduplication, with a newly increased buffer capacity of 20,000 bars.

## Architecture Decisions
### Decision: Fetching Strategy
**Choice**: Fetch 10,000 bars on initialization and 200 bars incrementally on `localLastCandleTime` updates.
**Alternatives considered**: Fetching the full history (10k bars) on every update or implementing L2 websockets.
**Rationale**: L2 websockets are out of scope. Fetching 10k bars every minute is too heavy on the backend. Fetching 200 bars on candle close provides fresh recent data seamlessly, while the initial 10k fetch ensures full historical context.

### Decision: Merging Deduplication Priority
**Choice**: Merge incrementally fetched data by timestamp, prioritizing the incoming `data` over the existing buffer for any matching timestamp.
**Alternatives considered**: Appending blindly or ignoring incoming duplicates.
**Rationale**: Overwriting existing timestamps ensures that any late-arriving or corrected ticks for a recently closed candle are updated correctly in the view, avoiding ghost/duplicate data.

## Data Flow
1. **Initial Load**: `ChartComponent.js` mounts -> Calls `/api/indicators/calculate` with `limit=10000` -> Receives initial `liquidityHeatmapData`.
2. **Candle Close**: `localLastCandleTime` state changes in `ChartComponent.js` -> Triggers `useEffect` -> Calls API with `limit=200`.
3. **Data Merge**: New data passed as `data` prop to `LiquidityHeatmapOverlay.js`.
4. **Deduplication**: `LiquidityHeatmapOverlay.js` converts `data` into a `Map` by `.time`, updates the internal `liveMap`, sorts keys, truncates to 20,000, and triggers re-render.

## File Changes
| File | Action | Description |
|------|--------|-------------|
| `src/platform/web/components/ChartComponent.js` | Modify | Update the `fetchLiquidityHeatmap` logic. Track if it's the initial load to use `limit=10000`, otherwise use `limit=200`. Add `localLastCandleTime` to the dependency array of the fetching `useEffect`. |
| `src/platform/web/components/LiquidityHeatmapOverlay.js` | Modify | Update merge logic in the `useEffect` to override existing timestamps with new data. Increase the buffer limit check from 5000 to 20000 bars. |

## Interfaces / Contracts
```javascript
// API Call for Initial Load
GET /api/indicators/calculate?symbol={symbol}&timeframe={tf}&limit=10000&platform={platform}

// API Call for Incremental Update
GET /api/indicators/calculate?symbol={symbol}&timeframe={tf}&limit=200&platform={platform}
```

## Testing Strategy
| Layer | What to Test | Approach |
|-------|-------------|----------|
| Unit | Deduplication logic | Verify `LiquidityHeatmapOverlay` correctly merges overlapping timestamps without duplicating points and caps at 20,000. |
| Integration | Incremental Fetch | Verify `ChartComponent.js` triggers a `limit=200` fetch when `localLastCandleTime` changes. |
| E2E | Rendering Performance | Ensure the chart doesn't stutter when the 200-bar incremental update occurs and merges into a 10,000-bar buffer. |

## Migration / Rollout
No data migration required. Feature is tied to the crypto mode usage of the Liquidity Heatmap.

## Open Questions
- [ ] Should we display a loading indicator specifically for the liquidity heatmap while the initial 10,000 bars are being fetched?
