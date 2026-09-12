import os
import pytest
from broker.base import Position
from broker.paper import PaperBroker
from broker.trading212 import Trading212Broker, Trading212Error
from execution.planner import build_rebalance_orders
from execution.engine import execute_orders

def test_planner_sells_before_buys():
    pos=[Position('OLD', 5, 10, 50)]
    orders=build_rebalance_orders({'NEW':0.5}, pos, 50, {'OLD':10,'NEW':10}, cash_buffer=0)
    assert orders[0].side == 'SELL'
    assert any(o.symbol=='NEW' and o.side=='BUY' for o in orders)

def test_paper_end_to_end():
    b=PaperBroker(100, {'AAPL':20,'MSFT':25})
    orders=build_rebalance_orders({'AAPL':0.5,'MSFT':0.5}, b.positions(), b.cash, b.prices, cash_buffer=0)
    r=execute_orders(b, orders, dry_run=False)
    assert all(x.status=='FILLED' for x in r)
    assert abs(b.account_summary()['total_value']-100) < 1e-8

def test_dry_run_does_not_trade():
    b=PaperBroker(100, {'AAPL':20})
    orders=build_rebalance_orders({'AAPL':1.0}, b.positions(), b.cash, b.prices, cash_buffer=0)
    execute_orders(b, orders, dry_run=True)
    assert b.positions() == []
    assert b.cash == 100

def test_live_trading_locked_by_default(monkeypatch):
    monkeypatch.delenv('GAINZ_ENABLE_LIVE', raising=False)
    with pytest.raises(Trading212Error):
        Trading212Broker('live', api_key='x', api_secret='y')
