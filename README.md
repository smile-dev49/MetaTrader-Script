# MetaTrader 5 + Python — demo smoke test and trading helpers

This folder contains a **small, reliable layer** around the official [MetaTrader5](https://www.mql5.com/en/docs/integration/python_metatrader5) Python API: connect, place market orders, modify SL/TP, close positions, and **full logging** of retcodes and `last_error()`.

The **acceptance script** `demo_smoke_test.py` opens **one** test trade on your demo account, logs each step, then **closes** it.

## Requirements

- Windows (same machine where MetaTrader 5 is installed), or a setup where the MT5 terminal can run and accept API connections.
- **MetaTrader 5** installed, logged in to your broker (e.g. Go Markets demo).
- **Python 3.10+** recommended.

## Install

```bash
cd "D:\WorkType\Python\Freelancer Task"
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

Copy `.env.example` to `.env` and fill in **your** credentials (never commit `.env`):

| Variable | Meaning |
|----------|---------|
| `MT5_LOGIN` | Account number |
| `MT5_PASSWORD` | Main trading password |
| `MT5_SERVER` | Server name exactly as in MT5 (e.g. `GoMarkets-Demo`) |
| `MT5_TERMINAL_PATH` | Optional full path to `terminal64.exe` if init fails |

Alternatively, set the same variables in Windows **Environment Variables** instead of `.env`.

## Run the demo smoke test

1. Start **MT5** and confirm the demo account connects in the terminal (or rely on `mt5.login` from `.env`).
2. Ensure **TEST_SYMBOL** (e.g. `EURUSD`) is visible in **Market Watch**.
3. Edit **`demo_smoke_test.py`** — block `EDIT THESE`: symbol, volume, side, pips or fixed SL/TP, magic, deviation.
4. Run:

```bash
python demo_smoke_test.py
```

You should see timestamped lines for: initialize/login, account summary, order send, position details, close, shutdown. If something fails, the log includes **retcode name** and **`last_error()`** to decode broker rejections (invalid volume, market closed, stops level, etc.).

## Project files

| File | Role |
|------|------|
| `mt5_trading.py` | Reusable helpers: `connect`, `place_market_order`, `modify_position_sltp`, `close_position`, volume/stop normalization, filling mode. |
| `demo_smoke_test.py` | One-shot demo: open → log → close → log. |
| `003 5 pip Pullback and breakout code.py` | Separate strategy prototype; wire it to `mt5_trading.py` for production-style execution. |
| `requirements.txt` | `MetaTrader5`, `pandas`, `python-dotenv`. |

## Extending

- **Your bot**: `import mt5_trading as m` then `m.connect(...)`, `m.place_market_order(...)`, etc. Keep **magic numbers** unique per script so you can filter positions.
- **Backtesting**: the Python API does **not** run the MT5 Strategy Tester. For Python backtests, download history with `mt5.copy_rates_range` / `copy_rates_from_pos` and simulate signals in a loop; use this repo for **live/demo execution** only.
- **Errors**: always inspect logged `TRADE_RETCODE_*` and `mt5.last_error()`; common fixes are wrong filling mode, volume step, or SL/TP inside minimum stop distance.

## Troubleshooting

### `(-10003, 'IPC initialize failed, MetaTrader 5 x64 not found')`

Python’s `MetaTrader5` package talks to the **installed MT5 terminal** (64-bit). This error means it could not find that terminal.

1. **Install MT5** from your broker (e.g. Go Markets) if it is not installed yet — the web platform is not enough; you need the **desktop** terminal.
2. In File Explorer, search your PC for **`terminal64.exe`**. Typical folders:
   - `C:\Program Files\MetaTrader 5\`
   - `C:\Program Files\GO Markets MetaTrader 5\` (name may vary)
3. Put the **full path** in `.env`:
   ```env
   MT5_TERMINAL_PATH=C:\Program Files\MetaTrader 5\terminal64.exe
   ```
   (Use your actual path; quotes are not required in `.env` unless the path has spaces — then some loaders need quotes.)
4. Use **64-bit Python**. Check:
   ```bash
   python -c "import struct; print(struct.calcsize('P')*8)"
   ```
   It should print `64`. If it prints `32`, install Python x64 and use that for `pip` / `demo_smoke_test.py`.
5. **Launch MT5 once** after install so the terminal finishes its first-time setup, then run the script again.

## Security

- Do **not** commit `.env`, screenshots of passwords, or real credentials into git.
- Prefer rotating the trading password if it was ever shared in plain text.
