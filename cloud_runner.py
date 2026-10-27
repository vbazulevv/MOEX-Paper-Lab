"""Run cloud market research with Python 3.11+ and no pip install."""
import argparse
import json
from pathlib import Path

from moex_paper_lab.cloud import run_pipeline


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=Path("cloud_config.json"))
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--output", type=Path, default=Path("cloud_reports"))
    parser.add_argument("--offline", action="store_true", help="Use saved CSVs; do not register forward forecasts")
    args = parser.parse_args()
    config = json.loads(args.config.read_text(encoding="utf-8"))
    report = run_pipeline(config, args.root, args.output, offline=args.offline)
    print(f"\nReport: {args.output / 'latest.md'}")
    print(f"Stocks: {len(report['research'])}/{report['requested_tickers']}; daily rows: {report['daily_rows']}")
    raise SystemExit(1 if report["all_failed"] else 0)


if __name__ == "__main__":
    main()
