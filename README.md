# GainZ Alpha

GainZ Alpha is a beginner-friendly quantitative trading research platform for learning, developing, and backtesting systematic investment strategies.

GainZ Alpha V0.3 is a research and educational project. It does **not** currently trade real money.

## Overview

GainZ Alpha downloads daily historical prices, calculates simple market indicators, and displays the results in a Streamlit dashboard. It also runs a basic historical backtest so the results of a rule-based strategy can be studied without connecting to a broker or placing orders.

## Current Features - V0.1

- Historical daily market data
- Multi-stock research universe: AAPL, MSFT, GOOGL, AMZN, NVDA, META, JPM, V, WMT, COST, XOM, JNJ, PG, HD, KO
- SPY benchmark data
- Streamlit dashboard
- Interactive Plotly charts
- Daily return calculations
- Cumulative return analysis
- AAPL vs SPY comparison
- 50-day moving average
- 200-day moving average
- Trend classification
- Long-only moving-average strategy
- Historical backtesting
- $10,000 simulated portfolio
- Buy-and-hold comparison
- Maximum drawdown
- Basic protection against look-ahead bias by shifting signals by one trading day

V0.2 evaluates the GainZ Alpha strategy, AAPL buy-and-hold, and SPY buy-and-hold using CAGR, annualized volatility, Sharpe ratio, maximum drawdown, percentage of trading days invested, and position changes. V0.3 applies the unchanged strategy independently to the research universe, compares each result with buy-and-hold, and reports excess CAGR. The initial Sharpe ratio uses a 0% risk-free rate. Each comparison uses the shared date window available across successfully downloaded research files.

## Current Strategy

The strategy compares two moving averages for each selected stock:

```text
50-day MA > 200-day MA -> Invested in AAPL
50-day MA < 200-day MA -> Cash
```

The signal is shifted by one trading day so a closing price is not used to pretend that the portfolio could have traded earlier on that same day. This is intentionally a very simple educational strategy and is not an investment recommendation.

## Project Structure

```text
GainZ/
|-- main.py                    # Small command-line entry point
|-- requirements.txt           # Python packages needed by the project
|-- pyproject.toml             # Pytest configuration
|-- config/                    # Human-readable research settings
|-- data/                      # Data download code and local market data
|   |-- raw/                   # Reserved for original downloaded data
|   `-- processed/             # Reserved for cleaned research data
|-- strategies/                # Reserved for strategy definitions
|-- backtesting/               # Historical simulation and metrics
|-- portfolio_management/      # Reserved for future portfolio logic
|-- risk_management/           # Reserved for future risk checks
|-- dashboard/                 # Streamlit dashboard and charts
`-- tests/                     # Automated checks
```

The downloaded CSV files are local research data and are intentionally ignored by Git. The folders remain available through `.gitkeep` files.

## Installation

In Windows PowerShell:

```powershell
git clone <private-repository-url>
cd GainZ
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

## Running GainZ Alpha

Download or update the current research universe and SPY benchmark first:

```powershell
python data\download_prices.py
```

Then start the dashboard from the project folder:

```powershell
streamlit run dashboard\app.py
```

Open the local URL shown by Streamlit. Run the tests with:

```powershell
pytest
```

## Current Limitations

- Research only
- Historical backtesting only
- No broker integration
- No live trading
- No real-money execution
- No leverage
- No short selling
- No options
- No machine learning
- Historical results are not guaranteed to continue in the future
- Transaction costs may not yet be fully modeled

## Planned Development

Future work will remain incremental and research-focused:

### V0.3

- Multi-stock research comparison
- Portfolio-level backtesting
- Position sizing
- Stronger risk management

### Later research

- Additional strategies
- Out-of-sample testing
- Transaction costs and slippage
- Paper trading

Much later, and only after extensive testing, broker API integration and automated execution may be considered. Neither is currently implemented.

## Disclaimer

GainZ Alpha is for educational and research purposes only. It is not financial advice, an offer to buy or sell securities, or a guarantee of investment performance. Do not use it to trade real money without appropriate independent research and professional advice.

## Paper trading and Trading 212 integration

The repository now includes an end-to-end execution layer.

- `python run_paper_trading.py` runs the strategy against a local £100 simulated account.
- `python run_trading212.py` connects to Trading 212 **DEMO** and creates a dry-run order plan.
- `python run_trading212.py --execute-demo` submits orders to the Trading 212 **DEMO** environment.
- Real-money mode is deliberately locked in `broker/trading212.py` and is not exposed as a CLI flag.

Set `TRADING212_API_KEY` and `TRADING212_API_SECRET` as environment variables. Never paste credentials into Python files or commit them. The adapter resolves symbols against Trading 212 instrument metadata and uses market orders with signed fractional quantities.

### Safety gates

The default path is paper/demo only. Orders are generated from target weights, sells are submitted before buys, a cash buffer is retained, zero/tiny orders are skipped, and real-money access requires a deliberate source/config change plus `GAINZ_ENABLE_LIVE=YES`.

### Research limitation

The historical stock universe is based on current constituents, so survivorship bias remains. Walk-forward testing reduces temporal overfitting but does not remove that limitation. Do not interpret historical returns as guaranteed future returns.
