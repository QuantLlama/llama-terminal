</Delta for crypto-liquidity-heatmap>
<crypto-liquidity-heatmap Specification>
## Purpose
This specification details the behavior of the auto-updating crypto liquidity heatmap, which relies on smart incremental fetching of backend OHLCV data on candle close rather than L2 websockets.

## Requirements

### Requirement: Initial Historical Data Fetch
The system MUST fetch 10,000 bars of historical OHLCV data upon initial load to populate the full liquidity heatmap history.
#### Scenario: Initializing the heatmap on first load
- GIVEN the user opens the crypto liquidity heatmap view
- WHEN the view initializes
- THEN the system fetches 10,000 historical bars from the backend
- AND the heatmap is populated with the full historical context

### Requirement: Incremental Data Fetch on Candle Close
The system MUST incrementally fetch 200 recent bars from the backend exactly on the candle close event.
#### Scenario: Auto-updating on candle close
- GIVEN the heatmap has completed its initial load
- WHEN a new candle close event occurs
- THEN the system fetches the most recent 200 bars
- AND the newly fetched data is merged with the existing data on the heatmap

### Requirement: Data Merging with Deduplication
The system MUST merge incrementally fetched bars with existing historical data using strictly timestamp-based deduplication to prevent overlapping or duplicate data points.
#### Scenario: Merging new bars without duplicates
- GIVEN the system has received 200 incrementally fetched bars
- WHEN the system merges the new bars into the existing dataset
- THEN it uses timestamps to deduplicate any overlapping bars
- AND the chart updates fluidly without duplicate entries

### Requirement: Chart Data Buffer Capacity
The internal chart data buffer MUST support a capacity of up to 20,000 bars to accommodate the extensive historical context and subsequent incremental updates.
#### Scenario: Storing extensive history and updates
- GIVEN the user is viewing the liquidity heatmap for an extended period
- WHEN incremental updates are continuously merged
- THEN the internal buffer retains up to 20,000 bars to provide extensive historical context
