"""MOEX research pipeline. No brokerage integration, orders or invented prices.

Only standard-library modules are required. Historical forecasts are explicitly
backtests; the append-only forward ledger accepts only pre-session forecasts.
"""
from __future__ import annotations

import csv
import hashlib
import html
import json
import math
import os
import statistics
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, time as clock_time, timedelta, timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

MSK = ZoneInfo("Europe/Moscow")
VERSION = "shrink-drift20-v1"
CANDLE_FIELDS = ["ticker", "date", "begin", "end", "open", "high", "low", "close", "volume", "value"]


def get_json(url: str, attempts: int = 3) -> dict:
    for attempt in range(attempts):
        try:
            request = Request(url, headers={"User-Agent": "MOEX-Paper-Lab/2.0 research"})
            with urlopen(request, timeout=20) as response:
                return json.load(response)
        except (OSError, ValueError):
            if attempt + 1 == attempts:
                raise
            time.sleep(0.5 * (attempt + 1))
    raise RuntimeError("No response")


def candle_url(ticker: str, start: str, end: str, interval: int, offset: int) -> str:
    market, board = ("index", "SNDX") if ticker == "IMOEX" else ("shares", "TQBR")
    base = f"https://iss.moex.com/iss/engines/stock/markets/{market}/boards/{board}/securities/{ticker}/candles.json"
    return base + "?" + urlencode({"from": start, "till": end, "interval": interval,
                                   "start": offset, "iss.meta": "off", "iss.only": "candles"})


def validate_candle(row: dict) -> None:
    numbers = [row[k] for k in ("open", "high", "low", "close", "volume", "value")]
    if not all(math.isfinite(x) for x in numbers):
        raise ValueError("Non-finite candle")
    if min(row[k] for k in ("open", "high", "low", "close")) <= 0:
        raise ValueError("Non-positive OHLC price")
    if row["volume"] < 0 or row["value"] < 0:
        raise ValueError("Negative volume or turnover")
    if row["low"] > min(row["open"], row["close"]) or row["high"] < max(row["open"], row["close"]) or row["low"] > row["high"]:
        raise ValueError("Inconsistent OHLC candle")


def fetch_candles(ticker: str, start: str, end: str, interval: int = 24,
                  now: datetime | None = None, loader=None) -> tuple[list[dict], dict]:
    """Paginate until EMPTY, not until an assumed page size. Fail atomically."""
    now = (now or datetime.now(MSK)).astimezone(MSK)
    loader = loader or get_json
    rows, offset, seen_pages = {}, 0, set()
    first, last = date.fromisoformat(start), date.fromisoformat(end)
    for _ in range(1000):
        block = loader(candle_url(ticker, start, end, interval, offset))["candles"]
        page = block["data"]
        if not page:
            break
        signature = json.dumps(page, separators=(",", ":"))
        if signature in seen_pages:
            raise ValueError(f"{ticker}: pagination repeated a page")
        seen_pages.add(signature)
        for raw in page:
            item = dict(zip(block["columns"], raw))
            begin = datetime.fromisoformat(item["begin"]).replace(tzinfo=MSK)
            finish = datetime.fromisoformat(item["end"]).replace(tzinfo=MSK)
            day = begin.date()
            if not first <= day <= last or day.weekday() >= 5:
                continue
            # A daily row can keep changing through the evening. Never use today.
            if interval == 24 and day >= now.date():
                continue
            if interval != 24 and finish >= now - timedelta(minutes=15):
                continue
            row = {"ticker": ticker, "date": day.isoformat(), "begin": item["begin"], "end": item["end"]}
            row.update({k: float(item[k]) for k in ("open", "high", "low", "close", "volume", "value")})
            validate_candle(row)
            key = row["begin"]
            if key in rows and rows[key] != row:
                raise ValueError(f"{ticker}: conflicting duplicate candle {key}")
            rows[key] = row
        offset += len(page)
    else:
        raise ValueError(f"{ticker}: excessive pagination")
    result = [rows[key] for key in sorted(rows)]
    return result, {"ticker": ticker, "status": "ok" if result else "empty", "rows": len(result),
                    "last": result[-1]["begin"] if result else None,
                    "source": candle_url(ticker, start, end, interval, 0), "board": "SNDX" if ticker == "IMOEX" else "TQBR"}


def atomic_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    temporary.replace(path)


def write_candles(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=CANDLE_FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    temporary.replace(path)


def quantile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    pos = fraction * (len(ordered) - 1)
    lower = int(pos)
    upper = min(lower + 1, len(ordered) - 1)
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (pos - lower)


def forecast_point(closes: list[float], horizon: int, model: str = VERSION) -> float:
    if model == "naive":
        return closes[-1]
    history = closes[-21:]
    # Log returns telescope; this equals their mean without repeated summation.
    drift = math.log(history[-1] / history[0]) / (len(history) - 1) if len(history) > 1 else 0.0
    return closes[-1] * math.exp(0.25 * drift * horizon)


def forecast_interval(closes: list[float], horizon: int) -> tuple[float | None, float | None, int]:
    # At this origin only residuals with ALREADY OBSERVED targets are available.
    residuals = [math.log(closes[k + horizon] / forecast_point(closes[:k + 1], horizon))
                 for k in range(59, len(closes) - horizon)]
    if len(residuals) < 30:
        return None, None, len(residuals)
    point = forecast_point(closes, horizon)
    return (point * math.exp(quantile(residuals, 0.025)),
            point * math.exp(quantile(residuals, 0.975)), len(residuals))


def metrics(actual: list[float], predicted: list[float], references: list[float]) -> dict:
    errors = [a - p for a, p in zip(actual, predicted)]
    directions = [(p - r, a - r) for a, p, r in zip(actual, predicted, references) if p != r and a != r]
    return {"n": len(errors), "mae_rub": statistics.mean(abs(e) for e in errors),
            "rmse_rub": math.sqrt(statistics.mean(e * e for e in errors)),
            "smape_pct": statistics.mean(200 * abs(a - p) / (abs(a) + abs(p)) for a, p in zip(actual, predicted)),
            "directional_accuracy_pct": 100 * sum(p * a > 0 for p, a in directions) / len(directions) if directions else None,
            "directional_n": len(directions)}


def backtest(closes: list[float], horizon: int) -> dict:
    origins = list(range(119, len(closes) - horizon))
    actual = [closes[i + horizon] for i in origins]
    reference = [closes[i] for i in origins]
    predicted = [forecast_point(closes[:i + 1], horizon) for i in origins]
    naive = metrics(actual, reference, reference)
    result = metrics(actual, predicted, reference)
    covered, interval_n = 0, 0
    for i in origins:
        low, high, _ = forecast_interval(closes[:i + 1], horizon)
        if low is not None:
            interval_n += 1
            covered += low <= closes[i + horizon] <= high
    result.update({"horizon": horizon, "model": VERSION, "naive": naive,
                   "mae_improvement_pct": 100 * (1 - result["mae_rub"] / naive["mae_rub"]) if naive["mae_rub"] else None,
                   "interval_coverage_pct": 100 * covered / interval_n if interval_n else None,
                   "interval_n": interval_n,
                   "evaluation": "walk-forward historical backtest; overlapping targets; no parameter search"})
    return result


def research_daily(ticker: str, rows: list[dict], benchmark: list[dict], config: dict) -> dict:
    closes = [r["close"] for r in rows]
    current = rows[-1]
    result = {"ticker": ticker, "as_of": current["date"], "close": closes[-1], "observations": len(rows)}
    result["median_turnover20_rub"] = statistics.median(r["value"] for r in rows[-20:])
    result["liquid"] = result["median_turnover20_rub"] >= config["min_median_turnover_rub"]
    result["return20_pct"] = 100 * (closes[-1] / closes[-21] - 1) if len(rows) >= 21 else None
    index = {r["date"]: r["close"] for r in benchmark}
    result["relative_strength20_pp"] = None
    if len(rows) >= 21 and rows[-21]["date"] in index and current["date"] in index:
        result["relative_strength20_pp"] = result["return20_pct"] - 100 * (index[current["date"]] / index[rows[-21]["date"]] - 1)
    true_ranges = [max(rows[i]["high"] - rows[i]["low"], abs(rows[i]["high"] - rows[i - 1]["close"]),
                       abs(rows[i]["low"] - rows[i - 1]["close"])) for i in range(max(1, len(rows) - 14), len(rows))]
    result["atr14_rub"] = statistics.mean(true_ranges) if true_ranges else None
    changes = [b - a for a, b in zip(closes[-15:], closes[-14:])] if len(closes) >= 15 else []
    gains = statistics.mean(max(c, 0) for c in changes) if changes else 0
    losses = statistics.mean(max(-c, 0) for c in changes) if changes else 0
    result["rsi14_simple"] = (100 - 100 / (1 + gains / losses)) if losses else (100 if gains else 50)
    result["status"] = "ok" if len(rows) >= config["min_history"] + max(config["horizons"]) else "insufficient_history"
    result["forecasts"], result["backtests"] = [], []
    if result["status"] == "ok":
        for horizon in config["horizons"]:
            low, high, n = forecast_interval(closes, horizon)
            result["forecasts"].append({"horizon": horizon, "point": forecast_point(closes, horizon),
                                         "lower95_empirical": low, "upper95_empirical": high,
                                         "calibration_n": n, "baseline": closes[-1]})
            result["backtests"].append(backtest(closes, horizon))
    return result


def scan_hourly(rows: list[dict], daily: dict, now: datetime) -> dict:
    if not rows:
        return {"status": "no_intraday_data"}
    last = rows[-1]
    hour = last["begin"][11:13]
    comparable = [r["volume"] for r in rows[:-1] if r["begin"][11:13] == hour and r["date"] < last["date"]][-10:]
    ratio = last["volume"] / statistics.median(comparable) if comparable and statistics.median(comparable) else None
    move = 100 * (last["close"] / last["open"] - 1)
    finish = datetime.fromisoformat(last["end"]).replace(tzinfo=MSK)
    stale = last["date"] != now.date().isoformat() or now - finish > timedelta(hours=3)
    confirmed = (not stale and daily.get("liquid", False) and len(comparable) >= 5 and ratio is not None and ratio >= 1.5
                 and move >= 0.5 and (daily.get("relative_strength20_pp") or 0) > 0)
    return {"status": "price_volume_watch" if confirmed else ("stale" if stale else "no_confirmation"),
            "begin_msk": last["begin"], "end_msk": last["end"], "close": last["close"],
            "hour_return_pct": move, "same_hour_volume_ratio": ratio, "comparison_n": len(comparable),
            "note": "Completed delayed hour; watchlist filter only; no news/catalyst validation or trade execution"}


def read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def append_jsonl(path: Path, records: list[dict]) -> None:
    if not records:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as stream:
        for record in records:
            stream.write(json.dumps(record, ensure_ascii=False, allow_nan=False) + "\n")
        stream.flush()
        os.fsync(stream.fileno())


def settle_forecasts(forecasts: list[dict], outcomes: list[dict], data: dict[str, list[dict]]) -> list[dict]:
    done = {r["forecast_id"] for r in outcomes}
    new = []
    for forecast in forecasts:
        if forecast["forecast_id"] in done:
            continue
        rows = data.get(forecast["ticker"], [])
        future = [r for r in rows if r["date"] > forecast["as_of"]]
        if len(future) < forecast["horizon"]:
            continue
        issued = datetime.fromisoformat(forecast["issued_at"]).astimezone(MSK)
        earliest = datetime.combine(date.fromisoformat(future[0]["date"]), clock_time(6, 50), MSK)
        if issued >= earliest:
            new.append({"forecast_id": forecast["forecast_id"], "status": "invalid_late_forecast"})
            continue
        target = future[forecast["horizon"] - 1]
        actual = target["close"]
        low, high = forecast["lower95_empirical"], forecast["upper95_empirical"]
        new.append({"forecast_id": forecast["forecast_id"], "status": "settled", "ticker": forecast["ticker"],
                    "horizon": forecast["horizon"], "target_date": target["date"], "actual": actual,
                    "point": forecast["point"], "baseline": forecast["reference_close"],
                    "absolute_error": abs(actual - forecast["point"]),
                    "naive_absolute_error": abs(actual - forecast["reference_close"]),
                    "covered": low <= actual <= high if low is not None and high is not None else None})
    return new


def register_forecasts(research: list[dict], existing: list[dict], now: datetime) -> list[dict]:
    now = now.astimezone(MSK)
    # Later runs still refresh research and scans, but cannot backdate a forecast.
    if now.weekday() >= 5 or now.time() >= clock_time(6, 30):
        return []
    keys = {f["forecast_id"] for f in existing}
    new = []
    for item in research:
        age = (now.date() - date.fromisoformat(item["as_of"])).days
        if item["status"] != "ok" or not 1 <= age <= 4:
            continue
        for prediction in item["forecasts"]:
            key = hashlib.sha256(f"{VERSION}:{item['ticker']}:{item['as_of']}:{prediction['horizon']}".encode()).hexdigest()[:24]
            if key in keys:
                continue
            keys.add(key)
            new.append({"forecast_id": key, "ticker": item["ticker"], "as_of": item["as_of"],
                        "issued_at": now.isoformat(), "model": VERSION, "reference_close": item["close"],
                        "research_only": True, **prediction})
    return new


def render_report(report: dict) -> str:
    def number(value, digits=2):
        return "—" if value is None else f"{value:,.{digits}f}"
    research = report["research"]
    errors = [r for r in report["sources"] if r["status"] != "ok"]
    lines = ["# MOEX Paper Lab · облачная исследовательская версия", "",
             f"Сформировано: {report['generated_at_msk']}. Данные: MOEX ISS, TQBR / IMOEX SNDX.", "",
             f"Загружено акций: **{len(research)} / {report['requested_tickers']}**. Дневных наблюдений с индексом: **{report['daily_rows']}**.",
             f"Новых прогнозов, записанных ДО сессии: **{report['new_forward_forecasts']}**. Проверено живых прогнозов: **{report['settled_forward_forecasts']}**.", "",
             "Снимок использует только завершённые прошлые календарные дни. Прогнозы ниже отсчитываются от указанного закрытия, а не от текущей цены. "
             "Утренний запуск до 06:30 МСК фиксирует прогнозы в неизменяемом журнале. В другое время обновляются только исследовательский снимок и часовой скрининг.", "",
             "## Часовой скрининг", "", "Сравнение объёма последнего завершённого часа с тем же часом предыдущих дней. Публичные данные могут запаздывать. "
             "Статус «наблюдать» означает ценовой фильтр; новости и торговые условия требуют отдельной проверки.", "",
             "| Акция | Конец часа, МСК | Цена часа, ₽ | За час | Объём / медиана | Статус |", "|---|---|---:|---:|---:|---|"]
    labels = {"price_volume_watch": "наблюдать", "no_confirmation": "нет подтверждения", "stale": "устарело", "no_intraday_data": "нет данных"}
    for item in sorted(research, key=lambda r: (r.get("intraday", {}).get("status") != "price_volume_watch", r["ticker"])):
        s = item.get("intraday", {})
        lines.append(f"| {item['ticker']} | {s.get('end_msk', '—')} | {number(s.get('close'), 4)} | {number(s.get('hour_return_pct'))}% | {number(s.get('same_hour_volume_ratio'))} | {labels.get(s.get('status'), 'отключено')} |")
    lines += ["", "## Price Oracle", "", "Фиксированная модель: 25% среднего логарифмического изменения за последние 20 наблюдений. "
              "Базовый прогноз: цена не изменится. Интервал — эмпирические 2,5–97,5% прошлых ошибок; 95% покрытия заранее не гарантировано. "
              "Горизонт означает следующие доступные будние дневные наблюдения TQBR, без предположения о точной дате закрытых праздников.", "",
              "| Акция | Дата закрытия | Закрытие, ₽ | Горизонт | Прогноз, ₽ | Нижняя / верхняя граница, ₽ | MAE vs baseline | Историческое покрытие |", "|---|---|---:|---:|---:|---:|---:|---:|"]
    for item in research:
        for prediction, test in zip(item["forecasts"], item["backtests"]):
            lines.append(f"| {item['ticker']} | {item['as_of']} | {number(item['close'], 4)} | {prediction['horizon']} | {number(prediction['point'], 4)} | "
                         f"{number(prediction['lower95_empirical'], 4)} / {number(prediction['upper95_empirical'], 4)} | {number(test['mae_improvement_pct'])}% | {number(test['interval_coverage_pct'])}% (n={test['interval_n']}) |")
    lines += ["", "Положительный MAE vs baseline означает меньшую ошибку. Отрицательный — модель хуже простого сохранения цены. "
              "В JSON также сохранены MAE, RMSE, sMAPE и точность направления. Исторический walk-forward не заменяет проверку новых прогнозов. "
              "Ошибки перекрывающихся горизонтов статистически зависимы. Параметры не подбирались по тестовым результатам.", "",
              "## Ограничения и журнал", "", "Котировки не скорректированы на дивиденды и корпоративные действия. Вселенная задана заранее и содержит surviving-ticker bias. "
              "Доходность торговой стратегии, цель 100 000 ₽ и точность 95% этой версией не доказаны. Брокерских подключений и автоматических сделок нет. "
              "Демонстрационный учебный портфель хранится отдельно. Реальные позиции пользователя не импортируются.", "",
              f"Всего записей прогноза: {report['forward_forecasts_total']}. Завершено валидных проверок: {report['settled_forward_forecasts']}.", ""]
    if report["all_failed"]:
        lines += ["**ОШИБКА: котировки акций не получены. Отчёт не является успешным обновлением.**", ""]
    if errors:
        lines += ["### Недоступные данные", ""]
        for error in errors:
            lines.append(f"- {error['ticker']} / interval={error['interval']}: {error['status']} {error.get('error', '')}")
    lines += ["", "Источники и параметры каждого запроса: `cloud_data/source_status.json`. "
              "Прогнозы: `cloud_state/forecasts.jsonl`. Отдельные результаты проверки: `cloud_state/outcomes.jsonl`.", ""]
    return "\n".join(lines)


def render_html(report: dict) -> str:
    def esc(value):
        return html.escape(str(value), quote=True)
    def num(value, digits=2):
        return "—" if value is None else f"{value:,.{digits}f}"
    def table(headers, rows):
        head = "".join(f"<th>{esc(h)}</th>" for h in headers)
        body = "".join("<tr>" + "".join(f"<td>{esc(c)}</td>" for c in row) + "</tr>" for row in rows)
        return f'<div class="scroll"><table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>'
    research = report["research"]
    labels = {"price_volume_watch": "Наблюдать", "no_confirmation": "Нет подтверждения", "stale": "Устарело", "no_intraday_data": "Нет данных"}
    watch = sum(r.get("intraday", {}).get("status") == "price_volume_watch" for r in research)
    latest = max((r["as_of"] for r in research), default="Нет данных")
    hour_rows, forecast_rows, comparison_rows = [], [], []
    for item in sorted(research, key=lambda r: (r.get("intraday", {}).get("status") != "price_volume_watch", r["ticker"])):
        hour = item.get("intraday", {})
        hour_rows.append([item["ticker"], hour.get("end_msk", "—"), num(hour.get("close"), 4),
                          num(hour.get("hour_return_pct")) + "%", num(hour.get("same_hour_volume_ratio")),
                          labels.get(hour.get("status"), "Отключено")])
        for prediction, test in zip(item["forecasts"], item["backtests"]):
            forecast_rows.append([item["ticker"], item["as_of"], num(item["close"], 4), prediction["horizon"],
                                  num(prediction["point"], 4), num(prediction["lower95_empirical"], 4) + " – " + num(prediction["upper95_empirical"], 4),
                                  num(test["mae_improvement_pct"]) + "%"])
    for horizon in sorted({t["horizon"] for r in research for t in r["backtests"]}):
        tests = [t for r in research for t in r["backtests"] if t["horizon"] == horizon]
        improvements = [t["mae_improvement_pct"] for t in tests if t["mae_improvement_pct"] is not None]
        directions = [t["directional_accuracy_pct"] for t in tests if t["directional_accuracy_pct"] is not None]
        coverages = [t["interval_coverage_pct"] for t in tests if t["interval_coverage_pct"] is not None]
        comparison_rows.append([horizon, len(tests), num(statistics.median(improvements)) + "%" if improvements else "—",
                                num(statistics.median(directions)) + "%" if directions else "—",
                                num(statistics.median(coverages)) + "%" if coverages else "—"])
    errors = [s for s in report["sources"] if s["status"] != "ok"]
    errors_html = "" if not errors else '<section><h2>Недоступные данные</h2>' + table(
        ["Инструмент", "Интервал", "Статус", "Причина"],
        [[s["ticker"], s["interval"], s["status"], s.get("error", "Пустой ответ")] for s in errors]) + '</section>'
    status = '<p class="notice">Котировки акций не получены. Это обновление завершилось ошибкой.</p>' if report["all_failed"] else ''
    return '''<!doctype html><html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>MOEX Paper Lab</title>
<style>:root{color-scheme:light}*{box-sizing:border-box}body{margin:0;background:#edf1f6;color:#172638;font:15px/1.6 system-ui,-apple-system,sans-serif}main{max-width:1180px;margin:auto;padding:32px 20px 56px}header{background:#122c44;color:#fff;padding:32px;border-radius:20px}header p{color:#d1e0ec;max-width:740px;margin-bottom:0}.eyebrow{font-size:12px;letter-spacing:.13em;text-transform:uppercase;color:#95d8d3}h1{font-size:clamp(28px,6vw,44px);line-height:1.1;margin:10px 0 16px}h2{font-size:22px;line-height:1.25;margin:0 0 12px}p{margin:8px 0 16px}.stats{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin:18px 0}.stat{background:#fff;padding:20px;border-radius:14px;border:1px solid #dde5ed}.stat strong{font-size:26px;display:block;line-height:1.3}.stat span{font-size:12px;color:#516378}section{background:white;border:1px solid #dde5ed;border-radius:16px;padding:24px;margin:18px 0}.note{font-size:13px;color:#526477}.notice{background:#fff0df;padding:14px;border-radius:10px;color:#7e4109}.scroll{overflow:auto}table{width:100%;border-collapse:collapse;white-space:nowrap;font-variant-numeric:tabular-nums}th,td{padding:12px 14px;border-bottom:1px solid #e5ebf1;text-align:right;font-size:13px}th{color:#53657a;font-size:11px;text-transform:uppercase;background:#f7f9fc;letter-spacing:.03em}td:first-child,th:first-child{text-align:left;font-weight:650}a{color:#126c82}input{width:100%;max-width:340px;padding:12px;border:1px solid #b8c8d6;border-radius:9px;font:inherit;margin-bottom:14px}footer{color:#53657a;font-size:12px}@media(max-width:650px){main{padding:14px 10px 36px}header{padding:24px 20px}.stats{grid-template-columns:repeat(2,1fr);gap:8px}.stat{padding:16px}.stat strong{font-size:22px}section{padding:20px 14px}th,td{padding:10px;font-size:12px}}</style></head><body><main>''' + \
        f'<header><div class="eyebrow">Исследовательская модель · без сделок</div><h1>MOEX Paper Lab</h1><p>Котировки, часовой скрининг и проверка прогнозов на истории.</p><p class="note" style="color:#b8d0df">Снимок: {esc(report["generated_at_msk"])} МСК</p></header>{status}' + \
        '<div class="stats">' + ''.join(f'<div class="stat"><span>{esc(label)}</span><strong>{esc(value)}</strong></div>' for label, value in [
            ("Акций загружено", f'{len(research)} / {report["requested_tickers"]}'), ("Последний полный день", latest),
            ("В часовом наблюдении", watch), ("Живых прогнозов проверено", report["settled_forward_forecasts"])]) + '</div>' + \
        '<section><h2>Что уже проверено</h2><p>Медианы метрик по акциям. Это исторический walk-forward фиксированной модели. Живой журнал оценивается отдельно.</p>' + \
        table(["Горизонт", "Акций", "Улучшение MAE", "Направление угадано", "Покрытие интервала"], comparison_rows) + \
        '<p class="note">Положительное улучшение MAE — ошибка ниже базового прогноза «цена останется прежней». Отрицательное — модель хуже базы. Точность выше 95% и торговая доходность не подтверждены.</p></section>' + \
        '<section><h2>Часовой скрининг</h2><p>Сравнивается объём одного завершённого часа с тем же часом прошлых дней. «Наблюдать» — повод проверить новости и условия, без торгового решения.</p>' + \
        table(["Акция", "Конец часа, МСК", "Цена, ₽", "За час", "Объём / медиана", "Статус"], hour_rows) + '</section>' + \
        '<section id="forecasts"><h2>Прогнозы от последнего закрытия</h2><p>Дневные снимки отсчитываются от указанной исторической цены, а не от текущего внутридневного курса. Горизонт — следующее доступное буднее дневное наблюдение.</p><input id="ticker" aria-label="Фильтр по тикеру" placeholder="Найти акцию, например SOFL">' + \
        table(["Акция", "Дата закрытия", "Закрытие, ₽", "Горизонт", "Прогноз, ₽", "Эмпирический интервал 95%, ₽", "Улучшение MAE"], forecast_rows) + \
        '<p class="note">Интервал основан на прошлых ошибках. Его заявленная ширина не гарантирует 95% фактического покрытия и не означает 95% вероятности угадать цену.</p></section>' + errors_html + \
        f'<section><h2>Журнал новых прогнозов</h2><p>Добавлено до открытия сессии в этом запуске: <strong>{report["new_forward_forecasts"]}</strong>. Всего записей: <strong>{report["forward_forecasts_total"]}</strong>. Завершено живых проверок: <strong>{report["settled_forward_forecasts"]}</strong>.</p><p class="note">Новые записи принимаются только до 06:30 МСК по будням. Запуски днём не создают прогнозы задним числом. Исходные записи сохраняются, результат добавляется отдельно.</p></section>' + \
        '<footer><p>Модель: shrink-drift20-v1. OHLCV не скорректированы на дивиденды и корпоративные действия. Выборка тикеров задана заранее; перекрывающиеся горизонты зависимы. Новости, TP/SL и исполнение этой версией не моделируются.</p><p>Источник: <a href="https://www.moex.com/a2920">MOEX ISS</a>. Публичные данные могут запаздывать. Данные портфеля пользователя не используются.</p></footer>' + \
        '''</main><script>document.getElementById('ticker').addEventListener('input',function(){const q=this.value.trim().toUpperCase();document.querySelectorAll('#forecasts tbody tr').forEach(function(row){row.hidden=!row.cells[0].textContent.toUpperCase().includes(q)})})</script></body></html>'''


def run_pipeline(config: dict, root: Path, output: Path, now: datetime | None = None, offline: bool = False) -> dict:
    simulated_clock = now is not None
    now = (now or datetime.now(MSK)).astimezone(MSK)
    data_dir, state = root / "cloud_data", root / "cloud_state"
    daily, hourly, sources = {}, {}, []
    tickers = list(dict.fromkeys(config["tickers"]))
    requests = [(t, 24) for t in tickers + ["IMOEX"]]
    if config.get("intraday"):
        requests += [(t, 60) for t in tickers]
    def obtain(ticker, interval):
        start = config["history_start"] if interval == 24 else (now.date() - timedelta(days=28)).isoformat()
        end = (now.date() - timedelta(days=1)).isoformat() if interval == 24 else now.date().isoformat()
        if offline:
            path = data_dir / f"{ticker}_{interval}.csv"
            with path.open(encoding="utf-8", newline="") as f:
                rows = list(csv.DictReader(f))
            for row in rows:
                for key in ("open", "high", "low", "close", "volume", "value"):
                    row[key] = float(row[key])
                validate_candle(row)
                if row["date"] >= now.date().isoformat() and interval == 24:
                    raise ValueError("Offline input includes incomplete/future daily candle")
            return rows, {"ticker": ticker, "status": "ok" if rows else "empty", "rows": len(rows), "offline": True,
                          "source": candle_url(ticker, start, end, interval, 0),
                          "cached_file_modified_at_msk": datetime.fromtimestamp(path.stat().st_mtime, MSK).isoformat(),
                          "last": rows[-1]["begin"] if rows else None,
                          "board": "SNDX" if ticker == "IMOEX" else "TQBR"}
        return fetch_candles(ticker, start, end, interval, now)
    with ThreadPoolExecutor(max_workers=config.get("workers", 4)) as pool:
        futures = {pool.submit(obtain, ticker, interval): (ticker, interval) for ticker, interval in requests}
        for future in as_completed(futures):
            ticker, interval = futures[future]
            try:
                rows, status = future.result()
                if rows:
                    (daily if interval == 24 else hourly)[ticker] = rows
                    if not offline:
                        write_candles(data_dir / f"{ticker}_{interval}.csv", rows)
            except Exception as exc:
                status = {"ticker": ticker, "status": "error", "error": f"{type(exc).__name__}: {exc}"[:250]}
            status["interval"] = interval
            sources.append(status)
            print(f"{ticker:6s} interval={interval:<2} {status['status']:5s} rows={status.get('rows', 0)}", flush=True)
    if not offline:
        atomic_json(data_dir / "source_status.json", sorted(sources, key=lambda s: (s["ticker"], s["interval"])))
    research = []
    for ticker in tickers:
        if ticker not in daily:
            continue
        item = research_daily(ticker, daily[ticker], daily.get("IMOEX", []), config)
        item["data_age_calendar_days"] = (now.date() - date.fromisoformat(item["as_of"])).days
        if item["data_age_calendar_days"] > 4:
            item["status"] = "stale_daily_data"
        if config.get("intraday"):
            item["intraday"] = scan_hourly(hourly.get(ticker, []), item, now)
        research.append(item)
    forecasts = read_jsonl(state / "forecasts.jsonl")
    outcomes = read_jsonl(state / "outcomes.jsonl")
    new_outcomes = settle_forecasts(forecasts, outcomes, daily)
    if not offline and not simulated_clock:
        append_jsonl(state / "outcomes.jsonl", new_outcomes)
    # Actual completion time, not request-start time: a delayed run must not
    # claim that a forecast calculated after the cutoff was issued beforehand.
    issued_now = datetime.now(MSK)
    new_forecasts = [] if offline or simulated_clock else register_forecasts(research, forecasts, issued_now)
    append_jsonl(state / "forecasts.jsonl", new_forecasts)
    outcomes = outcomes + new_outcomes
    report = {"schema_version": 1, "model_version": VERSION, "generated_at_msk": issued_now.isoformat(),
              "snapshot_cutoff_msk": now.isoformat(),
              "requested_tickers": len(tickers), "daily_rows": sum(map(len, daily.values())),
              "research": research, "sources": sorted(sources, key=lambda s: (s["ticker"], s["interval"])),
              "all_failed": not research, "offline": offline,
              "new_forward_forecasts": len(new_forecasts), "forward_forecasts_total": len(forecasts) + len(new_forecasts),
              "settled_forward_forecasts": sum(o["status"] == "settled" for o in outcomes)}
    atomic_json(output / "latest.json", report)
    markdown = render_report(report)
    (output / "latest.md").write_text(markdown, encoding="utf-8")
    (output / "index.html").write_text(render_html(report), encoding="utf-8")
    return report
