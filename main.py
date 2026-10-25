#!/usr/bin/env python3
"""MOEX Paper Lab: interactive console for educational paper trading."""
from __future__ import annotations

import argparse
from copy import deepcopy
from datetime import date
from pathlib import Path
import shutil

from moex_paper_lab.models import Trade, clean_ticker, money, parse_iso_date
from moex_paper_lab.portfolio import Portfolio
from moex_paper_lab.risk import assess_risk
from moex_paper_lab.storage import append_trade, export_report, load_prices, load_trades, update_price

ROOT = Path(__file__).resolve().parent
DEFAULT_TRADES = ROOT / "data" / "trades.csv"
DEFAULT_PRICES = ROOT / "data" / "prices.csv"


def initialize_data(trades: Path, prices: Path) -> None:
    """Copy synthetic examples into editable files only for first-time default users."""
    for target, sample, default in (
        (trades, ROOT / "data" / "sample_trades.csv", DEFAULT_TRADES),
        (prices, ROOT / "data" / "sample_prices.csv", DEFAULT_PRICES),
    ):
        if target == default and not target.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(sample, target)
            print(f"Created local working data: {target.relative_to(ROOT)}")


def load_portfolio(trades_file: Path) -> Portfolio:
    portfolio = Portfolio()
    for trade in load_trades(trades_file):
        portfolio.apply_trade(trade)
    return portfolio


def display_snapshot(portfolio: Portfolio, prices_file: Path) -> None:
    snap = portfolio.snapshot(load_prices(prices_file))
    print("\nPAPER PORTFOLIO (synthetic or manually entered prices)")
    print(f"{'Ticker':<9}{'Shares':>7}{'Avg cost':>13}{'Price':>12}{'Value':>14}{'U/P&L':>14}")
    print("-" * 69)
    for pos in snap.positions:
        print(f"{pos.ticker:<9}{pos.quantity:>7}{pos.average_cost:>13.2f}"
              f"{pos.market_price:>12.2f}{pos.market_value:>14.2f}{pos.unrealized_pnl:>14.2f}")
    if not snap.positions:
        print("No open positions.")
    print(f"Market value: {snap.market_value:.2f} RUB")
    print(f"Realized P&L: {snap.realized_pnl:+.2f} RUB | "
          f"Unrealized P&L: {snap.unrealized_pnl:+.2f} RUB | "
          f"Total P&L: {snap.total_pnl:+.2f} RUB")


def record_trade(portfolio: Portfolio, trades_file: Path) -> None:
    raw_date = input(f"Trade date [YYYY-MM-DD, Enter={date.today()}]: ").strip()
    trade = Trade(
        trade_date=parse_iso_date(raw_date) if raw_date else date.today(),
        ticker=input("Ticker (e.g. SBER): "),
        side=input("Side [BUY/SELL]: "),
        quantity=int(input("Quantity (whole shares): ").strip()),
        price=money(input("Price per share (RUB): "), "price"),
        commission=money(input("Commission (RUB, 0 allowed): "), "commission"),
    )
    # Validate the entire transaction against a copy before writing to disk.
    preview = deepcopy(portfolio)
    preview.apply_trade(trade)
    append_trade(trades_file, trade)
    portfolio.apply_trade(trade)
    print(f"Recorded simulated {trade.side} of {trade.quantity} {trade.ticker}.")


def change_price(prices_file: Path) -> None:
    ticker = clean_ticker(input("Ticker: "))
    price = money(input("New simulated/manual market price (RUB): "), "price")
    update_price(prices_file, ticker, price)
    print(f"Updated {ticker} to {price:.2f} RUB (manual price).")


def display_risk(portfolio: Portfolio, prices_file: Path) -> None:
    snap = portfolio.snapshot(load_prices(prices_file))
    flags = assess_risk(snap)
    print("\nRISK MONITOR | Demo thresholds: >40% allocation, >10% price drop")
    if not snap.positions:
        print("No positions to check.")
    elif not flags:
        print("No warning thresholds exceeded.")
    for flag in flags:
        print(f"WARNING [{flag.ticker}] {flag.rule}: {flag.message}")
    print("Educational warnings only; not investment advice.")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Offline simulated Moscow Exchange paper-portfolio CLI; no live trading."
    )
    parser.add_argument("--trades", type=Path, default=DEFAULT_TRADES,
                        help="Path to local paper trades CSV")
    parser.add_argument("--prices", type=Path, default=DEFAULT_PRICES,
                        help="Path to local manual/synthetic prices CSV")
    args = parser.parse_args()
    trades_file = args.trades.expanduser().resolve()
    prices_file = args.prices.expanduser().resolve()
    try:
        initialize_data(trades_file, prices_file)
        portfolio = load_portfolio(trades_file)
        load_prices(prices_file)
    except (ValueError, OSError) as exc:
        parser.exit(1, f"Unable to initialize: {exc}\n")
    while True:
        print("\n" + "=" * 45)
        print("      MOEX PAPER LAB | PAPER TRADES ONLY")
        print("=" * 45)
        print("1. View portfolio and P&L")
        print("2. Record a simulated trade")
        print("3. Update a manual market price")
        print("4. Check portfolio risk")
        print("5. Export CSV portfolio report")
        print("6. Exit")
        try:
            choice = input("Select 1–6: ").strip()
            if choice == "1":
                display_snapshot(portfolio, prices_file)
            elif choice == "2":
                record_trade(portfolio, trades_file)
            elif choice == "3":
                change_price(prices_file)
            elif choice == "4":
                display_risk(portfolio, prices_file)
            elif choice == "5":
                path = ROOT / "reports" / "portfolio_report.csv"
                export_report(path, portfolio.snapshot(load_prices(prices_file)))
                print(f"Saved report: {path}")
            elif choice == "6":
                print("Goodbye! No real orders were placed.")
                break
            else:
                print("Please enter a number between 1 and 6.")
        except (ValueError, OSError) as exc:
            print(f"Please check your input: {exc}")
        except (EOFError, KeyboardInterrupt):
            print("\nGoodbye!")
            break


if __name__ == "__main__":
    main()
