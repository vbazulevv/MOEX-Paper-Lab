from datetime import date
from decimal import Decimal as D
from pathlib import Path
import tempfile
import unittest

from moex_paper_lab.models import Trade
from moex_paper_lab.portfolio import Portfolio
from moex_paper_lab.storage import append_trade, export_report, load_prices, load_trades, update_price


class StorageTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.trades = self.root / "trades.csv"
        self.prices = self.root / "prices.csv"
        self.trades.write_text("date,ticker,side,quantity,price,commission\n", encoding="utf-8")
        self.prices.write_text("ticker,price,as_of\nSBER,100,2026-10-01\n", encoding="utf-8")

    def test_trade_roundtrip(self) -> None:
        original = Trade(date(2026, 10, 1), "SBER", "BUY", 2, D("100"), D("0.5"))
        append_trade(self.trades, original)
        self.assertEqual(load_trades(self.trades), [original])

    def test_price_update_and_new_ticker(self) -> None:
        update_price(self.prices, "SBER", "110", date(2026, 10, 2))
        update_price(self.prices, "GAZP", "50", date(2026, 10, 2))
        self.assertEqual(load_prices(self.prices), {"SBER": D("110"), "GAZP": D("50")})

    def test_bad_csv_reports_row(self) -> None:
        self.trades.write_text(
            "date,ticker,side,quantity,price,commission\n2026-10-01,SBER,BUY,ten,100,0\n", encoding="utf-8"
        )
        with self.assertRaisesRegex(ValueError, "row 2"):
            load_trades(self.trades)

    def test_reject_non_iso_trade_date(self) -> None:
        # The documented CSV schema requires YYYY-MM-DD, not compact YYYYMMDD.
        self.trades.write_text(
            "date,ticker,side,quantity,price,commission\n20261001,SBER,BUY,2,100,0\n",
            encoding="utf-8",
        )
        with self.assertRaisesRegex(ValueError, "row 2"):
            load_trades(self.trades)

    def test_report_export(self) -> None:
        p = Portfolio()
        p.apply_trade(Trade(date(2026, 10, 1), "SBER", "BUY", 2, D("100")))
        report = self.root / "reports" / "portfolio.csv"
        export_report(report, p.snapshot({"SBER": D("110")}))
        self.assertIn("20.00", report.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
