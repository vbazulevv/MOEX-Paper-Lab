"""Boundary tests for pagination, information timing and persistent forecasts."""
import unittest
from datetime import datetime

from moex_paper_lab.cloud import (
    MSK, VERSION, backtest, fetch_candles, forecast_point, register_forecasts,
    settle_forecasts, validate_candle,
)


def block(rows):
    return {"candles": {"columns": ["open", "close", "high", "low", "value", "volume", "begin", "end"], "data": rows}}


def raw(day, price=100):
    return [price, price, price + 1, price - 1, 10000, 100, f"{day} 00:00:00", f"{day} 23:59:59"]


class CloudTests(unittest.TestCase):
    def test_pagination_does_not_assume_500_rows(self):
        calls = []
        pages = [block([raw("2026-10-22")]), block([raw("2026-10-23")]), block([])]
        def load(url):
            calls.append(url)
            return pages.pop(0)
        rows, status = fetch_candles("SOFL", "2026-10-01", "2026-10-26", now=datetime(2026, 10, 27, tzinfo=MSK), loader=load)
        self.assertEqual(len(rows), 2)
        self.assertIn("start=2", calls[-1])

    def test_no_incomplete_today_or_weekends(self):
        pages = [block([raw("2026-10-23"), raw("2026-10-24"), raw("2026-10-27")]), block([])]
        rows, _ = fetch_candles("SOFL", "2026-10-01", "2026-10-27", now=datetime(2026, 10, 27, 19, tzinfo=MSK), loader=lambda _: pages.pop(0))
        self.assertEqual([r["date"] for r in rows], ["2026-10-23"])

    def test_repeated_page_fails_instead_of_looping(self):
        with self.assertRaisesRegex(ValueError, "repeated"):
            fetch_candles("SOFL", "2026-10-01", "2026-10-26", now=datetime(2026, 10, 27, tzinfo=MSK), loader=lambda _: block([raw("2026-10-22")]))

    def test_failure_after_first_page_never_returns_partial_history(self):
        pages = [block([raw("2026-10-22")])]
        def load(_):
            if pages:
                return pages.pop()
            raise OSError("connection lost")
        with self.assertRaises(OSError):
            fetch_candles("SOFL", "2026-10-01", "2026-10-26", now=datetime(2026, 10, 27, tzinfo=MSK), loader=load)

    def test_nonfinite_ohlc_rejected(self):
        with self.assertRaises(ValueError):
            validate_candle(dict(open=1, close=float("nan"), low=1, high=1, volume=1, value=1))

    def test_future_prices_do_not_change_an_existing_prediction(self):
        prices = [100 + i / 10 for i in range(150)]
        origin = 125
        before = forecast_point(prices[:origin + 1], 3)
        prices[origin + 1:] = [1_000_000] * (len(prices) - origin - 1)
        self.assertEqual(before, forecast_point(prices[:origin + 1], 3))

    def test_constant_prices_have_zero_error_without_fake_direction_accuracy(self):
        test = backtest([100.0] * 150, 5)
        self.assertEqual(test["mae_rub"], 0)
        self.assertEqual(test["interval_coverage_pct"], 100)
        self.assertIsNone(test["directional_accuracy_pct"])
        self.assertIsNone(test["mae_improvement_pct"])

    def test_only_pre_session_ledger_and_idempotency(self):
        item = {"ticker": "SOFL", "as_of": "2026-10-26", "status": "ok", "close": 100,
                "forecasts": [{"horizon": 1, "point": 101, "lower95_empirical": 98, "upper95_empirical": 104}]}
        self.assertEqual(register_forecasts([item], [], datetime(2026, 10, 27, 19, tzinfo=MSK)), [])
        registered = register_forecasts([item], [], datetime(2026, 10, 27, 6, 17, tzinfo=MSK))
        self.assertEqual(len(registered), 1)
        self.assertEqual(register_forecasts([item], registered, datetime(2026, 10, 27, 6, 20, tzinfo=MSK)), [])
        self.assertEqual(register_forecasts([item], [], datetime(2026, 10, 27, 6, 30, tzinfo=MSK)), [])

    def test_settlement_waits_for_horizon_and_rejects_late_forecast(self):
        f = {"forecast_id": "one", "ticker": "SOFL", "as_of": "2026-10-26", "issued_at": "2026-10-27T06:17:00+03:00",
             "horizon": 1, "point": 101, "reference_close": 100, "lower95_empirical": 98, "upper95_empirical": 104}
        self.assertEqual(settle_forecasts([f], [], {"SOFL": []}), [])
        data = {"SOFL": [{"date": "2026-10-27", "close": 102}]}
        settled = settle_forecasts([f], [], data)
        self.assertEqual(settled[0]["absolute_error"], 1)
        self.assertTrue(settled[0]["covered"])
        self.assertEqual(settle_forecasts([f], settled, data), [])
        f["issued_at"] = "2026-10-27T19:17:00+03:00"
        self.assertEqual(settle_forecasts([f], [], data)[0]["status"], "invalid_late_forecast")


if __name__ == "__main__":
    unittest.main()
