# GainZ Alpha

GainZ Alpha is a beginner-friendly quantitative trading research platform for learning, developing, and backtesting systematic investment strategies.

GainZ Alpha V0.1 is a research and educational project. It does **not** currently trade real money.

## Overview

GainZ Alpha downloads daily historical prices, calculates simple market indicators, and displays the results in a Streamlit dashboard. It also runs a basic historical backtest so the results of a rule-based strategy can be studied without connecting to a broker or placing orders.

## Current Features - V0.1

- Historical daily market data
- AAPL research
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

## Current Strategy

The strategy compares two moving averages for AAPL:

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

Download the current AAPL and SPY data first:

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

### V0.2

- Better performance metrics
- CAGR
- Volatility
- Sharpe ratio
- Improved benchmark comparison

### V0.3

- Multiple stocks
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
