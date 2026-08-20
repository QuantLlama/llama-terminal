## Exploration: crypto-liquidity-heatmap

### Current State
Currently, the Liquidity Heatmap indicator (`LiquidityHeatmapOverlay.js`) only automatically updates in real-time when it receives `market_dom` (L2 order book) websocket events. In crypto mode, users often lack a continuous L2 data stream, so the frontend relies on the backend's OHLCV-based approximation (`liquidity_heatmap.py`). However, `ChartComponent.js` only fetches this data on initial load or when settings change, forcing the user to manually refresh to see new areas. Furthermore, the history limit is capped at 2000-3000 bars, and the frontend buffer is strictly capped at 5000 bars, which prevents the heatmap from drawing across the entire width of the chart when zoomed out ("todo largo del grafico").

### Affected Areas
- `src/platform/web/components/ChartComponent.js` — Missing trigger to fetch incremental heatmap data on `localLastCandleTime` (candle close), and hardcoded low fetch limits.
- `src/platform/web/components/LiquidityHeatmapOverlay.js` — Hardcoded buffer limit of 5000 bars. The data merging logic (`if (!liveMap.has(time))`) prevents updating the latest candle with new backend data.

### Approaches

1. **Full History Polling on Candle Close** — Modify `ChartComponent.js` to fetch `limit=10000` every time a candle closes.
   - Pros: Simple to implement.
   - Cons: Will severely lag the platform and overload the network/backend ("lenta y pesada") since it downloads ~15MB of JSON data every minute/second.
   - Effort: Low

2. **Smart Incremental Fetching (Recommended)** — Modify `ChartComponent.js` to fetch a large history (`limit=10000`) on initial load, but only fetch `limit=200` on subsequent `localLastCandleTime` updates. Modify `LiquidityHeatmapOverlay.js` to correctly merge and overwrite the latest bars, and increase its internal buffer to `20000`.
   - Pros: Extremely efficient; network payload for updates is tiny. Gives massive history without causing UI lag. Ensures the heatmap automatically advances.
   - Cons: The last 200 bars approximation might have a tiny decay discrepancy vs computing 10000 bars at once, but mathematically negligible.
   - Effort: Medium

### Recommendation
Proceed with **Approach 2 (Smart Incremental Fetching)**. This directly solves the manual refresh issue by tracking `localLastCandleTime` to auto-fetch updates. By splitting the logic into an initial heavy fetch (`limit=10000`) and lightweight incremental updates (`limit=200`), the platform will remain fast and responsive. Increasing the frontend buffer to `20000` will solve the issue of the heatmap not drawing across the entire chart.

### Risks
- Large initial fetch (`limit=10000`) may cause a brief 1-2 second loading delay when the chart first opens, though rendering is already optimized via frustum culling.
- Overwriting existing candles in the frontend buffer could cause visual flickering if not handled cleanly in the overlay loop.

### Ready for Proposal
Yes — The root causes are identified and the solution balances performance with the requested large historical scale.
