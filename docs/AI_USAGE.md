# AI Usage & Debugging Log

This file documents what actually happened while developing the initial assistant-generated coursework draft on **25 October 2026**. It distinguishes AI-authored material from work still to be performed by the student.

## Goal / user request

The student selected their MOEX Paper Lab idea for a university Mini-Project 2 assignment, which asks for an AI-assisted Python console script automating an everyday task, a README, AI-assisted debugging, Git history and a public GitHub link.

The student asked an AI assistant to turn this concept into a GitHub-ready working project. The assistant chose to **narrow the scope to offline paper-trade recordkeeping**, not recreate any real-money trading system.

## AI contributions

1. **Research and design.** Proposed standard-library-only Python architecture, separate accounting/storage/risk modules, local synthetic CSV sample data, `unittest`, an interactive menu and GitHub Actions.
2. **Initial implementation.** Generated `main.py`, `models.py`, `portfolio.py`, `risk.py` and `storage.py` to record and value simulated trades.
3. **Unit tests.** Generated test coverage for weighted-average cost, partial sales, commissions, overselling, closed positions, risk alerts and CSV I/O.
4. **Console smoke test.** Ran `python main.py` with scripted menu inputs `1`, `4`, `5`, `6`. The example portfolio displayed market value **2596.00 RUB**, realized P&L **48.50 RUB**, unrealized P&L **152.50 RUB** and total P&L **201.00 RUB**, matching the fictional sample trades. The CSV report was created.
5. **Real debugging exercise.** Found that `date.fromisoformat('20261001')` accepts a compact date although the documented schema requires `YYYY-MM-DD`. Added `test_reject_non_iso_trade_date` and ran it: **FAIL** (`AssertionError: ValueError not raised`). Introduced a strict `parse_iso_date()` validator and used it for trade dates, price dates, and console input. Re-ran the suite: **14 tests passed**.
6. **Documentation.** Generated this log and the main README explaining setup, usage, formulas, limitations and AI involvement.

## Genuine Git milestones in the draft

These commits were created as part of the assistant's local build with the Git identity `OpenAI Assistant (draft)`. They are **not** represented as student-authored commits:

- `feat: implement offline paper-trading CLI and accounting`
- `test: add portfolio storage and risk validation suite`
- `test: expose compact-date validation defect` (failing test captured)
- `fix: enforce documented ISO date format in CSV and CLI` (test passing)
- `docs: add reproducible setup and AI-assisted development log`

Commit messages describe the actual content of the commits; the student should make further commits only for work they genuinely perform.

## What the student should do next

- Run the program and test suite on their **own Mac**, and review the code and numerical examples.
- Experiment with a fake `BUY`, `SELL`, and price update, and check the exported report.
- Discuss any confusing behavior or errors with the AI assistant, record the genuine conversation/debugging steps here, and commit any improvements under their own Git identity.
- Create or connect a **public GitHub repository**, push this history, and submit the root repository URL via Blackboard.

No account credentials, real trades or personal portfolio exports should be added to the public repository.
