"""Validated data models for simulated trades."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
import re

TICKER_PATTERN = re.compile(r"^[A-Z0-9][A-Z0-9._-]{0,14}$")


def money(value: object, label: str = "number") -> Decimal:
    """Parse a finite decimal; never use floats for stored currency amounts."""
    try:
        result = Decimal(str(value).strip())
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ValueError(f"{label} must be a valid number") from exc
    if not result.is_finite():
        raise ValueError(f"{label} must be a finite number")
    return result


def clean_ticker(value: str) -> str:
    ticker = str(value).strip().upper()
    if not TICKER_PATTERN.fullmatch(ticker):
        raise ValueError("ticker must contain 1–15 letters, digits, dots, dashes or underscores")
    return ticker


@dataclass(frozen=True)
class Trade:
    trade_date: date
    ticker: str
    side: str
    quantity: int
    price: Decimal
    commission: Decimal = Decimal("0")

    def __post_init__(self) -> None:
        if not isinstance(self.trade_date, date):
            raise ValueError("trade date must be a valid date")
        object.__setattr__(self, "ticker", clean_ticker(self.ticker))
        side = str(self.side).strip().upper()
        if side not in ("BUY", "SELL"):
            raise ValueError("side must be BUY or SELL")
        object.__setattr__(self, "side", side)
        if type(self.quantity) is not int or self.quantity <= 0:
            raise ValueError("quantity must be a positive whole number")
        price = money(self.price, "price")
        commission = money(self.commission, "commission")
        if price <= 0:
            raise ValueError("price must be greater than zero")
        if commission < 0:
            raise ValueError("commission must not be negative")
        object.__setattr__(self, "price", price)
        object.__setattr__(self, "commission", commission)


@dataclass
class Position:
    ticker: str
    quantity: int = 0
    average_cost: Decimal = Decimal("0")
    realized_pnl: Decimal = Decimal("0")


@dataclass(frozen=True)
class PortfolioRow:
    ticker: str
    quantity: int
    average_cost: Decimal
    market_price: Decimal
    market_value: Decimal
    unrealized_pnl: Decimal
    realized_pnl: Decimal


@dataclass(frozen=True)
class Snapshot:
    positions: tuple[PortfolioRow, ...]
    market_value: Decimal
    realized_pnl: Decimal
    unrealized_pnl: Decimal
    total_pnl: Decimal


@dataclass(frozen=True)
class RiskFlag:
    ticker: str
    rule: str
    message: str
