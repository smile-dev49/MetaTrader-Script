# Legacy prototypes

`pullback_breakout_bot.py` is an **archived** pullback/breakout experiment. It was developed separately from `mt5_trading.py` and is **not** wired to the shared connection/order helpers. References inside the file to functions such as `get_signal` and `place_market_order` are placeholders from an older draft; the script is **not** runnable end-to-end without restoration work.

For live or demo execution, use the supported stack in the repository root:

- `mt5_trading.py` — connect, market orders, modify SL/TP, close
- `demo_smoke_test.py` / `main.py` — acceptance demo
- `mt5_monitor.py` — polling monitor

If you port this strategy, import `mt5_trading` for MT5 I/O and keep risk/session logic in a dedicated module.
