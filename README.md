# MetaTrader 5 + Python — trading helpers and demo

This repository provides a **small, reliable layer** around the official [MetaTrader5](https://www.mql5.com/en/docs/integration/python_metatrader5) Python package: connect (with optional login or existing terminal session), place market orders, **modify** SL/TP, close positions, and **timestamped logging** of retcodes and `last_error()`.

The **acceptance demo** opens **one** test trade on your account (use **demo**), optionally **adjusts SL/TP**, logs each step, then **closes** the position.

## Requirements

- **Windows** on the same machine where **MetaTrader 5** (64-bit) is installed, unless you have a supported setup where the terminal and Python can connect via the API.
- **MetaTrader 5** installed and able to log in to your broker.
- **Python 3.10+** recommended (64-bit Python to match the terminal).

## Install and project layout

1. Clone or copy this folder to your machine. All commands below assume a **shell open in the project root** (the directory that contains `requirements.txt`, `mt5_trading.py`, and `main.py`).

   ```powershell
   cd D:\Freelancer\MetaTrader\MetaTrader-Script
   ```

   Replace the path with wherever your copy of the project actually lives.

2. Create a virtual environment and install dependencies:

   ```powershell
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1
   pip install -r requirements.txt
   ```

3. Copy `.env.example` to `.env` and fill in your values (never commit `.env`).

| Variable | Meaning |
|----------|---------|
| `MT5_LOGIN` | Account number |
| `MT5_PASSWORD` | Main trading password |
| `MT5_SERVER` | Server name exactly as shown in MT5 |
| `MT5_TERMINAL_PATH` | Optional full path to `terminal64.exe` if `initialize()` cannot find the terminal |
| `MT5_USE_EXISTING_SESSION` | Set to `1` or `true` to **skip** `mt5.login` and use the account already logged in inside MT5 (recommended if you sign in manually in the terminal) |

You can set the same names in Windows **Environment Variables** instead of `.env`.

## Entry points (what to run)

| Command | Purpose |
|---------|---------|
| `python main.py` | **Recommended for clients:** same behavior as the demo script below. |
| `python demo_smoke_test.py` | Same as `main.py` — use this if you prefer an explicit script name. |
| `python mt5_monitor.py` | Polls account equity/balance and lists open positions until you press **Ctrl+C** (or use `--iterations`). |

There is **no** separate `main.py` trading engine beyond delegating to the demo; the **canonical implementation** of the flow lives in `demo_smoke_test.py`.

## Run the demo (test trade + optional modify + close)

**User actions you must do:**

1. Start **MetaTrader 5** and connect the **demo** account (or accept the risk if you use a live account — not recommended for testing).
2. If you log in **inside the terminal only**, set `MT5_USE_EXISTING_SESSION=1` in `.env` so Python does not call `mt5.login` (avoids many IPC/login timeouts).
3. Add your symbol to **Market Watch** (e.g. `EURUSD`).
4. In `demo_smoke_test.py`, edit the block marked **`# EDIT THESE`** — symbol, volume, side, SL/TP (pips or fixed prices), **modify demo** toggles (`TEST_ENABLE_MODIFY_DEMO`, `TEST_MODIFY_*`), magic number, deviation, wait time.
5. From the project root, with the venv activated:

   ```powershell
   python main.py
   ```

**Expected log sequence:** initialize / session → account line → order send → open position → (optional) modify SL/TP → position snapshot after modify → close → success → shutdown.

If something fails, logs include **retcode names** and **`last_error()`** (e.g. market closed, invalid volume, stops level).

FX symbols often return `TRADE_RETCODE_MARKET_CLOSED` outside session hours; run during liquid market hours or set `TEST_ALT_SYMBOL` to an instrument your broker quotes.

## Real-time monitoring (polling)

The MetaTrader5 Python API does **not** offer WebSocket-style subscriptions for account or positions. This project uses **polling**, which is the usual approach.

```powershell
python mt5_monitor.py
python mt5_monitor.py --interval 3 --iterations 30
```

- **`--interval`**: seconds between polls (default `2`).
- **`--iterations`**: stop after N polls; omit to run until **Ctrl+C**.

## Automated tests (no MT5 required)

```powershell
python -m pytest tests/test_mt5_trading.py -v
```

Tests mock the MT5 module and cover configuration parsing, volume normalization, stop-distance adjustment, and logging helpers.

## Project files

| File | Role |
|------|------|
| `mt5_trading.py` | Shared helpers: `connect`, `place_market_order`, `modify_position_sltp`, `close_position`, volume/stop normalization, filling mode. |
| `demo_smoke_test.py` | Demo flow: open → optional SL/TP modify → close (all parameters in `TEST_*` block). |
| `main.py` | Delegates to `demo_smoke_test.main()` for a single obvious entry point. |
| `mt5_monitor.py` | CLI polling monitor for account and positions. |
| `tests/test_mt5_trading.py` | Pytest unit tests. |
| `legacy/pullback_breakout_bot.py` | Archived strategy draft (not wired to `mt5_trading.py`); see `legacy/README.md`. |
| `requirements.txt` | Runtime + `pytest`. |

## Extending

- Import **`mt5_trading`** in your own scripts: `connect`, `place_market_order`, `modify_position_sltp`, `close_position`, etc. Use a **unique magic number** per strategy so you can filter positions.
- **Backtesting:** the Python API does **not** run the MT5 Strategy Tester. For research, pull history with `mt5.copy_rates_range` / `copy_rates_from_pos` and simulate signals in Python; use this repo for **live/demo execution**.
- On errors, inspect `TRADE_RETCODE_*` and `mt5.last_error()`; common issues are filling mode, lot step, or SL/TP inside minimum stop distance.

## Deployment notes

- Treat **`main.py` / `demo_smoke_test.py`** as **acceptance and learning tools**, not unattended production bots, unless you add your own risk controls, reconnect logic, and monitoring.
- Run under a **dedicated demo account** first; keep credentials out of source control.
- Ensure the MT5 terminal stays **running and connected** while scripts run.

## Troubleshooting

### `(-10003, 'IPC initialize failed, MetaTrader 5 x64 not found')`

Python talks to the **installed** 64-bit MT5 terminal; the web terminal is not enough.

1. Install MT5 from your broker and locate **`terminal64.exe`** (e.g. under `C:\Program Files\MetaTrader 5\` or your broker’s folder).
2. Set `MT5_TERMINAL_PATH` in `.env` to that full path.
3. Confirm 64-bit Python:

   ```powershell
   python -c "import struct; print(struct.calcsize('P')*8)"
   ```

   It should print `64`.

4. Open MT5 once after install to finish first-time setup, then retry.

### Algorithmic trading disabled

In MT5: **Tools → Options → Expert Advisors** — enable **Allow algorithmic trading**. Run Python and MT5 at the same elevation (both normal or both admin).

## Security

- Do **not** commit `.env`, passwords, or screenshots of credentials.
- Rotate passwords if they were ever exposed in plain text.
