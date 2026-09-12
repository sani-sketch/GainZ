from pathlib import Path
import pandas as pd

from backtesting.moving_average_backtest import calculate_portfolio_metrics
from backtesting.regime_multifactor_research import Variant, run_variant
from config.settings import load_settings
from risk_management.dynamic_risk import apply_dynamic_risk_overlay, standard_risk_configs

ROOT = Path(__file__).resolve().parent
SETTINGS = load_settings()
INITIAL = 10_000.0
VALIDATION_START = pd.Timestamp("2025-01-01")


def load_prices(ticker: str) -> pd.DataFrame:
    path = ROOT / "data" / f"{ticker}_daily.csv"
    return pd.read_csv(
        path,
        skiprows=[1, 2],
        names=["Date", "Adj Close", "Close", "High", "Low", "Open", "Volume"],
        header=0,
        parse_dates=["Date"],
    )[["Date", "Close", "Volume"]].dropna().sort_values("Date")


def metrics(r: pd.Series) -> dict[str, float]:
    values = INITIAL * (1 + r).cumprod()
    m = calculate_portfolio_metrics(
        pd.Series(r.index), values.reset_index(drop=True), r.reset_index(drop=True), INITIAL
    )
    return {
        "cagr": float(m["cagr"]),
        "sharpe": float(m["sharpe_ratio"]),
        "max_drawdown": float(m["maximum_drawdown"]),
        "total_return": float(m["total_return"]),
        "final_value": float(values.iloc[-1]),
    }


def main():
    tickers = SETTINGS["universe"].get("broad_symbols", SETTINGS["universe"]["symbols"])
    benchmark = SETTINGS["universe"]["benchmark"]
    price_data = {ticker: load_prices(ticker) for ticker in tickers}
    spy = load_prices(benchmark)

    # Frozen leading candidate from the prior diagnostic pass.
    candidate = Variant(
        name="N10_momentum_trend_3m6m_none",
        top_n=10,
        momentum_fast=63,
        momentum_slow=126,
        momentum_slow_weight=0.60,
        weight_momentum=0.60,
        weight_trend=0.30,
        weight_low_vol=0.10,
        weight_volume=0.00,
        regime="none",
    )
    raw, bench, _ = run_variant(price_data, spy, candidate, initial_capital=INITIAL)

    rows = []
    histories = []
    for cfg in standard_risk_configs():
        overlay = apply_dynamic_risk_overlay(raw, cfg)
        overlay["config"] = cfg.name
        histories.append(overlay.reset_index(names="Date"))
        for period_name, mask in [
            ("full", pd.Series(True, index=raw.index)),
            ("validation", raw.index >= VALIDATION_START),
        ]:
            rr = overlay.loc[mask, "protected_return"]
            mm = metrics(rr)
            rows.append({
                "config": cfg.name,
                "period": period_name,
                **mm,
                "average_exposure": float(overlay.loc[mask, "exposure"].mean()),
                "minimum_exposure": float(overlay.loc[mask, "exposure"].min()),
            })

    # Baselines for easy comparison.
    for name, series in [("RAW_GAINZ", raw), ("SPY", bench)]:
        for period_name, mask in [
            ("full", pd.Series(True, index=series.index)),
            ("validation", series.index >= VALIDATION_START),
        ]:
            mm = metrics(series.loc[mask])
            rows.append({
                "config": name, "period": period_name, **mm,
                "average_exposure": 1.0, "minimum_exposure": 1.0,
            })

    results = pd.DataFrame(rows)
    results.to_csv(ROOT / "outputs" / "risk_diagnostics.csv", index=False)
    pd.concat(histories, ignore_index=True).to_csv(ROOT / "outputs" / "risk_overlay_history.csv", index=False)

    val = results[results["period"] == "validation"].copy()
    print(val[["config", "cagr", "sharpe", "max_drawdown", "average_exposure", "final_value"]]
          .sort_values("sharpe", ascending=False).to_string(index=False))

    with open(ROOT / "outputs" / "risk_diagnostics_summary.md", "w", encoding="utf-8") as f:
        f.write("# GainZ Risk Overlay Diagnostics\n\n")
        f.write("Validation period starts 2025-01-01. Candidate is frozen from prior diagnostics.\n\n")
        f.write(val[["config", "cagr", "sharpe", "max_drawdown", "average_exposure", "final_value"]]
                .sort_values("sharpe", ascending=False).to_markdown(index=False))
        f.write("\n")


if __name__ == "__main__":
    main()
