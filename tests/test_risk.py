from datetime import date
from decimal import Decimal as D
import unittest

from moex_paper_lab.models import Trade
from moex_paper_lab.portfolio import Portfolio
from moex_paper_lab.risk import assess_risk


class RiskTests(unittest.TestCase):
    def setUp(self) -> None:
        self.p = Portfolio()
        self.p.apply_trade(Trade(date(2026, 10, 1), "SBER", "BUY", 9, D("100")))
        self.p.apply_trade(Trade(date(2026, 10, 1), "GAZP", "BUY", 1, D("100")))

    def test_concentration_warning(self) -> None:
        flags = assess_risk(self.p.snapshot({"SBER": D("100"), "GAZP": D("100")}))
        self.assertTrue(any(f.rule == "concentration" and f.ticker == "SBER" for f in flags))

    def test_loss_warning(self) -> None:
        flags = assess_risk(self.p.snapshot({"SBER": D("80"), "GAZP": D("100")}))
        self.assertTrue(any(f.rule == "paper_loss" and f.ticker == "SBER" for f in flags))

    def test_bad_thresholds(self) -> None:
        snap = self.p.snapshot({"SBER": D("100"), "GAZP": D("100")})
        with self.assertRaises(ValueError):
            assess_risk(snap, max_position_weight="NaN")


if __name__ == "__main__":
    unittest.main()
