"""Validated CSV input and atomic CSV output."""
from __future__ import annotations

import csv
from datetime import date
from decimal import Decimal
import os
from pathlib import Path
import tempfile
from typing import Iterable

from .models import PortfolioRow, Snapshot, Trade, clean_ticker, money

TRADE_COLUMNS = ["date", "ticker", "side", "quantity", "price", "commission"]
PRICE_COLUMNS = ["ticker", "price", "as_of"]
REPORT_COLUMNS = ["ticker", "quantity", "average_cost", "market_price", "market_value", "unrealized_pnl", "realized_pnl"]


def _read_rows(path: Path, columns: list[str]) -> list[dict[str, str]]:
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as file:
            reader = csv.DictReader(file)
            if reader.fieldnames != columns:
                raise ValueError(f"{path.name}: expected columns: {', '.join(columns)}")
            rows = list(reader)
            if any(None in row or any(v is None for v in row.values()) for row in rows):
                raise ValueError(f"{path.name}: malformed CSV row")
            return rows
    except FileNotFoundError as exc:
        raise ValueError(f"file not found: {path}") from exc
    except UnicodeError as exc:
        raise ValueError(f"{path.name}: CSV file is not valid UTF-8") from exc


def load_trades(path: Path) -> list[Trade]:
    trades = []
    for line, row in enumerate(_read_rows(path, TRADE_COLUMNS), start=2):
        try:
            trades.append(Trade(
                trade_date=date.fromisoformat(row["date"]),
                ticker=row["ticker"],
                side=row["side"],
                quantity=int(row["quantity"]),
                price=money(row["price"], "price"),
                commission=money(row["commission"], "commission"),
            ))
        except (ValueError, TypeError, OverflowError) as exc:
            raise ValueError(f"{path.name}, row {line}: {exc}") from exc
    return trades


def load_prices(path: Path) -> dict[str, Decimal]:
    prices: dict[str, Decimal] = {}
    for line, row in enumerate(_read_rows(path, PRICE_COLUMNS), start=2):
        try:
            ticker = clean_ticker(row["ticker"])
            price = money(row["price"], "price")
            if price <= 0:
                raise ValueError("price must be greater than zero")
            date.fromisoformat(row["as_of"])
            if ticker in prices:
                raise ValueError(f"duplicate ticker {ticker}")
            prices[ticker] = price
        except (ValueError, TypeError) as exc:
            raise ValueError(f"{path.name}, row {line}: {exc}") from exc
    return prices


def _write_rows(path: Path, columns: list[str], rows: Iterable[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_name = ""
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", newline="", delete=False, dir=path.parent,
            prefix=f".{path.name}.", suffix=".tmp",
        ) as file:
            tmp_name = file.name
            writer = csv.DictWriter(file, fieldnames=columns)
            writer.writeheader()
            writer.writerows(rows)
        os.replace(tmp_name, path)
    finally:
        if tmp_name and os.path.exists(tmp_name):
            os.unlink(tmp_name)


def append_trade(path: Path, trade: Trade) -> None:
    old = load_trades(path)
    _write_rows(path, TRADE_COLUMNS, [
        {"date": t.trade_date.isoformat(), "ticker": t.ticker, "side": t.side,
         "quantity": t.quantity, "price": str(t.price), "commission": str(t.commission)}
        for t in old + [trade]
    ])


def update_price(path: Path, ticker: str, price: object, as_of: date | None = None) -> None:
    ticker = clean_ticker(ticker)
    value = money(price, "price")
    if value <= 0:
        raise ValueError("price must be greater than zero")
    records = _read_rows(path, PRICE_COLUMNS)
    # Validate existing data instead of silently overwriting corrupted rows.
    load_prices(path)
    updated = False
    for row in records:
        if clean_ticker(row["ticker"]) == ticker:
            row["price"] = str(value)
            row["as_of"] = (as_of or date.today()).isoformat()
            updated = True
    if not updated:
        records.append({"ticker": ticker, "price": str(value), "as_of": (as_of or date.today()).isoformat()})
    _write_rows(path, PRICE_COLUMNS, records)


def export_report(path: Path, snapshot: Snapshot) -> None:
    _write_rows(path, REPORT_COLUMNS, [
        {"ticker": p.ticker, "quantity": p.quantity, "average_cost": f"{p.average_cost:.2f}",
         "market_price": f"{p.market_price:.2f}", "market_value": f"{p.market_value:.2f}",
         "unrealized_pnl": f"{p.unrealized_pnl:.2f}", "realized_pnl": f"{p.realized_pnl:.2f}"}
        for p in snapshot.positions
    ])
