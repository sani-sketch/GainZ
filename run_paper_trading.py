"""End-to-end GainZ paper runner. No real-money orders are possible here."""
from pathlib import Path
import json
import pandas as pd
from config.settings import load_settings
from live.signal import adaptive_target
from broker.paper import PaperBroker
from execution.planner import build_rebalance_orders
from execution.engine import execute_orders

ROOT = Path(__file__).resolve().parent
SETTINGS = load_settings()

def load_prices(ticker):
    return pd.read_csv(ROOT/'data'/f'{ticker}_daily.csv', skiprows=[1,2], names=['Date','Adj Close','Close','High','Low','Open','Volume'], header=0, parse_dates=['Date'])[['Date','Close','Volume']].dropna().sort_values('Date')

def main():
    tickers = SETTINGS['universe'].get('broad_symbols', SETTINGS['universe']['symbols'])
    benchmark = SETTINGS['universe']['benchmark']
    data = {t: load_prices(t) for t in tickers}
    spy = load_prices(benchmark)
    weights, decision = adaptive_target(data, spy)
    prices = {t: float(df['Close'].iloc[-1]) for t, df in data.items()}
    prices[benchmark] = float(spy['Close'].iloc[-1])
    broker = PaperBroker(cash=100.0, prices=prices)
    orders = build_rebalance_orders(weights, broker.positions(), broker.cash, prices, min_order_value=1.0)
    results = execute_orders(broker, orders, dry_run=False)
    report = {'decision': decision, 'target_weights': weights, 'orders': [r.__dict__ for r in results], 'account': broker.account_summary(), 'positions': [p.__dict__ for p in broker.positions()]}
    (ROOT/'outputs'/'paper_trade_report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps(report, indent=2))

if __name__ == '__main__': main()
