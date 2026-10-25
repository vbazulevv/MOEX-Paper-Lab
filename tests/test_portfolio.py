"""Core accounting regression tests for paper trades."""
from datetime import date
from decimal import Decimal as D
import unittest

from moex_paper_lab.models import Trade
from moex_paper_lab.portfolio import Portfolio


def trade(side: str, qty: int, price: str, fee: str = "0", ticker: str = "SBER") -> Trade:
    return Trade(date(2026, 10, 1), ticker, side, qty, D(price), D(fee))


class PortfolioTests(unittest.TestCase):
    def test_weighted_average_after_two_buys(self) -> None:
        portfolio = Portfolio()
        portfolio.apply_trade(trade("BUY", 10, "100"))
        portfolio.apply_trade(trade("BUY", 10, "120"))
        self.assertEqual(portfolio.positions["SBER"].quantity, 20)
        self.assertEqual(portfolio.positions["SBER"].average_cost, D("110"))

    def test_partial_sale_preserves_average_cost_and_calculates_pnl(self) -> None:
        portfolio = Portfolio()
        portfolio.apply_trade(trade("BUY", 10, "100"))
        portfolio.apply_trade(trade("BUY", 10, "120"))
        portfolio.apply_trade(trade("SELL", 5, "130"))
        pos = portfolio.positions["SBER"]
        snap = portfolio.snapshot({"SBER": D("125")})
        self.assertEqual((pos.quantity, pos.average_cost), (15, D("110")))
        self.assertEqual(snap.realized_pnl, D("100"))
        self.assertEqual(snap.unrealized_pnl, D("225"))
        self.assertEqual(snap.total_pnl, D("325"))

    def test_commissions_count_in_cost_basis_and_sale_profit(self) -> None:
        portfolio = Portfolio()
        portfolio.apply_trade(trade("BUY", 10, "100", "10"))
        self.assertEqual(portfolio.positions["SBER"].average_cost, D("101"))
        portfolio.apply_trade(trade("SELL", 5, "110", "2"))
        self.assertEqual(portfolio.positions["SBER"].realized_pnl, D("43"))

    def test_cannot_oversell_and_state_is_unchanged(self) -> None:
        portfolio = Portfolio()
        portfolio.apply_trade(trade("BUY", 3, "100"))
        with self.assertRaisesRegex(ValueError, "only 3 held"):
            portfolio.apply_trade(trade("SELL", 4, "110"))
        self.assertEqual(portfolio.positions["SBER"].quantity, 3)

    def test_closed_position_retains_realized_pnl(self) -> None:
        portfolio = Portfolio()
        portfolio.apply_trade(trade("BUY", 3, "100"))
        portfolio.apply_trade(trade("SELL", 3, "110"))
        snap = portfolio.snapshot({})
        self.assertEqual(snap.realized_pnl, D("30"))
        self.assertEqual(snap.market_value, D("0"))
        self.assertFalse(snap.positions)

    def test_invalid_prices_and_missing_market_price_rejected(self) -> None:
        with self.assertRaises(ValueError):
            trade("BUY", 2, "NaN")
        with self.assertRaises(ValueError):
            trade("BUY", 2, "-1")
        portfolio = Portfolio()
        portfolio.apply_trade(trade("BUY", 1, "100"))
        with self.assertRaisesRegex(ValueError, "missing market price"):
            portfolio.snapshot({})


if __name__ == "__main__":
    unittest.main()
