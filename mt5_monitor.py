"""
Poll MT5 for account and open positions at a fixed interval (no push API in MetaTrader5 Python).

The official Python API does not expose a subscription/socket for ticks or account events; polling
`account_info()` and `positions_get()` is the standard approach.

Usage (MT5 running, `.env` same as demo):

    python mt5_monitor.py
    python mt5_monitor.py --interval 3 --iterations 20
"""

from __future__ import annotations

import argparse
import sys
import time

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

import MetaTrader5 as mt5

from mt5_trading import ConnectConfig, connect, log_line, shutdown


def _log_positions() -> None:
    rows = mt5.positions_get()
    if not rows:
        log_line("  (no open positions)")
        return
    for p in rows:
        side = "buy" if p.type == mt5.POSITION_TYPE_BUY else "sell"
        log_line(
            f"  #{p.ticket} {p.symbol} {side} vol={p.volume} "
            f"open={p.price_open} sl={p.sl} tp={p.tp} profit={p.profit}"
        )


def run_monitor(*, interval_sec: float, max_iterations: int | None) -> int:
    log_line("=== MT5 monitor: start ===")
    if not connect(ConnectConfig.from_env()):
        log_line("Abort: could not connect.")
        return 1

    n = 0
    try:
        while max_iterations is None or n < max_iterations:
            ai = mt5.account_info()
            if not ai:
                log_line(f"account_info() failed: {mt5.last_error()}")
            else:
                log_line(
                    f"Account login={ai.login} balance={ai.balance} equity={ai.equity} "
                    f"margin={ai.margin} margin_free={ai.margin_free} profit={ai.profit}"
                )
            log_line("Open positions:")
            _log_positions()
            n += 1
            if max_iterations is not None and n >= max_iterations:
                break
            time.sleep(interval_sec)
    except KeyboardInterrupt:
        log_line("Monitor stopped (KeyboardInterrupt).")
    finally:
        shutdown()
        log_line("=== MT5 monitor: end ===")

    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Poll MT5 account and positions.")
    parser.add_argument(
        "--interval",
        type=float,
        default=2.0,
        help="Seconds between polls (default: 2).",
    )
    parser.add_argument(
        "--iterations",
        type=int,
        default=None,
        help="Stop after N polls (default: run until Ctrl+C).",
    )
    args = parser.parse_args()
    if args.interval <= 0:
        log_line("--interval must be positive.")
        return 2
    if args.iterations is not None and args.iterations < 1:
        log_line("--iterations must be >= 1 when set.")
        return 2
    return run_monitor(interval_sec=args.interval, max_iterations=args.iterations)


if __name__ == "__main__":
    sys.exit(main())
