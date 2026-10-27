# MOEX Paper Lab 📈

## Cloud research extension

The coursework console application remains available. The separate MOEX research pipeline downloads actual candles, checks forecasts on history and keeps an append-only forward ledger. It does not trade or import the sample portfolio. See [setup and methods](docs/CLOUD_SETUP_RU.md).

- [Latest cloud report](https://github.com/vbazulevv/MOEX-Paper-Lab/blob/moex-data/cloud_reports/latest.md)
- [Report for mobile and public data](https://vbazulevv.github.io/MOEX-Paper-Lab/)
- [Run status and manual start](https://github.com/vbazulevv/MOEX-Paper-Lab/actions/workflows/market-cloud.yml)

Scheduled updates: weekdays, every two hours from 06:17 to 22:17 Moscow time. Only pre-session runs can register new forward forecasts. Historical accuracy and live validation are reported separately.


**Mini-Project 2: Programming** — An offline Python console application for keeping a **fictional paper-trading portfolio**. It automates the repetitive calculations involved in recording stock trades, tracking holdings, estimating profit/loss, checking simple concentration and downside rules, and exporting a CSV report.

> **Educational project only.** The program does not connect to a brokerage account, submit orders, fetch live quotes, or recommend investments. All sample market prices and trades are **made up** for demonstration; the tickers are used as examples only. RUB is the display currency.

## Task automated

Instead of repeatedly updating a spreadsheet after each simulated transaction, the user can record a buy or sale in a terminal and immediately see their updated positions and profit/loss. Manual price updates let the program revalue the portfolio. All working data stays in simple local CSV files.

## Features

- Interactive menu, accessible by running `python3 main.py`
- Record simulated `BUY` and `SELL` transactions
- Track positive-integer share quantities and weighted-average purchase cost
- Calculate **realized P&L** (from sales) and **unrealized P&L** (from current manual prices), including simulated commissions
- Reject overselling, missing price data, malformed CSV rows, invalid dates and non-finite prices
- Warn if a single position exceeds **40%** of the portfolio or its price drops by more than **10%** below average cost (demo thresholds, **not** trading rules)
- Export the **currently open holdings** as CSV
- Run automated tests using Python's built-in `unittest`

## Requirements

- macOS, Linux or Windows
- Python **3.11 or newer** recommended
- No external Python packages; uses Python's standard library

## Quick start

Open Terminal in the repository folder, then run:

```bash
python3 main.py
```

On the first start, the program copies `data/sample_trades.csv` and `data/sample_prices.csv` into editable working copies (`data/trades.csv` and `data/prices.csv`). Your edits don't overwrite the committed sample files, and the working copies are excluded from Git.

**Menu:**

```text
=============================================
      MOEX PAPER LAB | PAPER TRADES ONLY
=============================================
1. View portfolio and P&L
2. Record a simulated trade
3. Update a manual market price
4. Check portfolio risk
5. Export CSV portfolio report
6. Exit
Select 1–6:
```

Example initial portfolio result from the synthetic sample data (before you add any trades):

```text
Ticker    Shares     Avg cost       Price         Value         U/P&L
---------------------------------------------------------------------
GAZP           8       150.19      147.50       1180.00        -21.50
SBER          12       103.50      118.00       1416.00        174.00
Market value: 2596.00 RUB
Realized P&L: +48.50 RUB | Unrealized P&L: +152.50 RUB | Total P&L: +201.00 RUB
```

Choose **2** to enter a simulated trade, or **3** to update a price. If you buy a ticker not yet present in the price file, update its price before trying to view your portfolio. Choose **5** to create `reports/portfolio_report.csv`. The report contains **open positions only**; the terminal summary also includes realized P&L from positions already closed.

### Optional: custom input files

```bash
python3 main.py --trades /path/to/my_trades.csv --prices /path/to/my_prices.csv
```

When using custom files, create them first with the schemas below. Only the default working-data paths get automatically initialized with sample values.

### Trade file format

```csv
date,ticker,side,quantity,price,commission
2026-10-01,SBER,BUY,10,100.00,1.50
2026-10-03,SBER,BUY,5,110.00,1.00
2026-10-07,SBER,SELL,3,120.00,1.00
```

`date` must be **YYYY-MM-DD**, `side` must be `BUY` or `SELL`, `quantity` is a positive integer, `price` is positive, and `commission` is zero or positive. Rows are processed **in file order**.

### Manual price file format

```csv
ticker,price,as_of
SBER,118.00,2026-10-25
GAZP,147.50,2026-10-25
```

These dates and prices are examples, not historical quotes. The program stores the `as_of` date, but does not check whether prices are stale.

## How the calculations work

**Buy:** new average cost = (previous quantity × previous average cost + purchased quantity × purchase price + purchase commission) / new quantity.

**Sell:** realized P&L increases by quantity sold × (sale price − average cost) − sale commission. A partial sale leaves the average cost of the remaining shares unchanged.

**Current valuation:** market value = current shares × manually entered price. Unrealized P&L = current shares × (price − average cost). Total P&L = realized + unrealized P&L.

All financial calculations use `decimal.Decimal` rather than binary floating-point numbers.

## Run tests

```bash
python3 -m unittest discover -s tests -p 'test_*.py' -v
```

Tests cover cost basis, commissions, partial sales, selling too many shares, closed positions, risk warnings, CSV input/output, invalid dates, and report export. The initial assistant-built version was tested in an isolated environment with **14 tests passing**. You should run these on your own computer as part of the coursework. The GitHub Actions workflow runs tests on pushes and pull requests.

## Repository structure

```text
moex-paper-lab/
├── main.py                      # Interactive console application
├── moex_paper_lab/
│   ├── models.py                # Validated trades, positions, snapshots
│   ├── portfolio.py             # Weighted-average cost and P&L
│   ├── storage.py               # CSV input, update and export
│   └── risk.py                  # Educational risk warnings
├── data/
│   ├── sample_trades.csv        # Fictional examples
│   └── sample_prices.csv        # Fictional examples
├── tests/                       # Python unittest suite
├── docs/AI_USAGE.md             # AI-assisted development & debugging log
├── .github/workflows/tests.yml  # Automated tests
├── requirements.txt             # No third-party dependencies
└── README.md
```

## AI-assisted development

AI assistance was used as requested by the assignment to plan and generate the program, create tests, diagnose a real input-validation defect, and write the documentation. In particular, a regression test revealed that Python accepted compact dates (e.g. `20261001`), even though the CSV contract requires `YYYY-MM-DD`. The date parsing was corrected and the new test subsequently passed.

See [`docs/AI_USAGE.md`](docs/AI_USAGE.md) for the actual development and debugging steps. Commits authored by the AI assistant are identified as such; the student's local testing and later contributions should be committed under their own Git identity.

## Limitations

The project is **not a prediction model or autonomous investment agent**. It is a small coursework-oriented part of a larger paper-trading idea. It does not model dividends, corporate actions, multiple currencies, short selling, leverage, slippage, taxes, broker lot sizes or account cash balances. Risk thresholds are arbitrary educational examples, not investor-specific advice. No live MOEX integration is included.

## Submitting the assignment

Push the repository to a **public GitHub repository** and submit its main URL to Blackboard. Verify that the README, source code, commit history, sample data and tests are publicly visible. See `docs/GITHUB_SETUP.md` for step-by-step macOS instructions.

## License

MIT License, see `LICENSE`.
