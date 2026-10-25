"""Long-only paper portfolio using weighted-average acquisition cost."""
from __future__ import annotations

from decimal import Decimal
from .models import PortfolioRow, Position, Snapshot, Trade


class Portfolio:
    def __init__(self) -> None:
        self.positions: dict[str, Position] = {}

    def apply_trade(self, trade: Trade) -> None:
        position = self.positions.get(trade.ticker)
        if position is None:
            position = Position(ticker=trade.ticker)
        if trade.side == "BUY":
            basis = position.average_cost * position.quantity
            new_qty = position.quantity + trade.quantity
            position.average_cost = (
                basis + trade.quantity * trade.price + trade.commission
            ) / Decimal(new_qty)
            position.quantity = new_qty
        else:
            if trade.quantity > position.quantity:
                raise ValueError(
                    f"cannot SELL {trade.quantity} {trade.ticker}: "
                    f"only {position.quantity} held"
                )
            position.realized_pnl += (
                trade.quantity * (trade.price - position.average_cost)
                - trade.commission
            )
            position.quantity -= trade.quantity
            if position.quantity == 0:
                position.average_cost = Decimal("0")
        self.positions[trade.ticker] = position

    def snapshot(self, prices: dict[str, Decimal]) -> Snapshot:
        rows: list[PortfolioRow] = []
        for ticker, pos in sorted(self.positions.items()):
            if pos.quantity == 0:
                continue
            if ticker not in prices:
                raise ValueError(f"missing market price for {ticker}; please update it")
            price = prices[ticker]
            if not price.is_finite() or price <= 0:
                raise ValueError(f"invalid market price for {ticker}")
            market_value = pos.quantity * price
            unrealized = pos.quantity * (price - pos.average_cost)
            rows.append(PortfolioRow(
                ticker=ticker,
                quantity=pos.quantity,
                average_cost=pos.average_cost,
                market_price=price,
                market_value=market_value,
                unrealized_pnl=unrealized,
                realized_pnl=pos.realized_pnl,
            ))
        realized = sum((p.realized_pnl for p in self.positions.values()), Decimal("0"))
        unrealized = sum((r.unrealized_pnl for r in rows), Decimal("0"))
        market_value = sum((r.market_value for r in rows), Decimal("0"))
        return Snapshot(
            positions=tuple(rows),
            market_value=market_value,
            realized_pnl=realized,
            unrealized_pnl=unrealized,
            total_pnl=realized + unrealized,
        )
