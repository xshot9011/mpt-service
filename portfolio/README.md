# Portfolio Management

## Main Page
- List of available portfolios
- Each portfolio entry displays:
  - PnL
  - Balance

## Portfolio

### Detail Page

- Asset Type (contain multiple symbols)
  - Symbol (can switch to another asset type)
    - Unit
    - NAV
      - Have another app call "NAVManagers" it will update the current price to database time series postgresl and add to redis (with retention remove old data)
        - Algorithem to cache, 1H go first, then 1D, 1W, 1M, 1Y, all (The service NAVManager will calculate it)
        - When user open the portfolio detail page, it will get the latest price from redis (if not found) then go to postgresql to get the latest price
          - it will trigger the "NAVManager" to go and get the price from the source (some wherer not sure, but i want API that able to select time frame like get BTC dd/mm/yyyy at 01.00.00)
      - Also allow user to manually put the price (will go like this first) because m poor...
    - ValueNow
    - PnL
- Portfolio Level
  - Graph of invest cost and current value at the end of each day (can do later, now focus on monthly)
  - Pnl calculate from current_portfolio_value - total_invest_cost
- Symbol level
  - PnL calculate from current_symbol_value - total_invest_cost (or MovingAveragePrice not sure will it get the same result)

### Transaction Detail Page
- Transaction details
- Ledger entries
- Realized PnL
- Unrealized PnL

## Incremental Feature Roadmap

### Milestone 1: Core Ledger Foundation
- **Data Models**: Setup `Asset`, `Broker`, `Position`, `Transaction`, `LedgerEntry`.
- **Core Logic**: Implement moving-average cost calculation for Positions.
- **Double-Entry**: Automate balancing transaction records (Debit/Credit).
- **Admin Setup**: Provide basic Django admin interfaces for testing.

### Milestone 2: Point-in-Time Valuation (Manual)
- **App Restructuring**: Extract `Asset` and `DailyPrice` into a dedicated `symbol` app.
- **Portfolio Linking**: Introduce a `Portfolio` model to group `Position` and `Transaction` records.
- **Valuation Logic**: Implement `value_at(target_date)` to calculate historical portfolio value using past transactions and the latest available manual `DailyPrice`.
- **Testing**: Comprehensive unit tests for point-in-time calculation.

### Milestone 3: Data Automation (NAVManager & Cron)
- **External Integration**: Build the `NAVManager` service to fetch realtime and historical prices from APIs (e.g., Yahoo Finance, CoinGecko).
  - First phase of this may be only at 1 hour interval. (we have 1H we can build 1D 1W 1M 1Y later on)
- **Automation**: Setup background tasks/cron jobs to automatically update `symbol.DailyPrice` at specific intervals.
- **Redis Caching**: Cache the latest prices and aggregated data (1H/1D/1W) when NAVManager fetches them, ensuring the web dashboard remains snappy without hitting the DB.
  - Redis will store the data with retention policy, so it will automatically remove old data.

### Milestone 4: Performance Optimization (Snapshots)
- **Portfolio Snapshot (`PortfolioSnapshot`)**: Create a model to persist heavy point-in-time calculations (Total Value, Invested Cost, PnL).
  - Snapshot will be calculated at the end of each day, and never cared about time change after the 00.00 . To allow cronjob which can run with delay.

### Milestone 5: Graphing & Dashboard UI- **Basic UI**: Simple Django views to review portfolios, positions, and input manual fallback prices.
- **Advanced Graphing**: Plot the `PortfolioSnapshot` data alongside individual asset performance over time (1D, 1W, 1M, 1Y).
- **Flexible Timeframes**: Ensure graphs can be generated from any arbitrary start date using the transaction history and snapshots.
