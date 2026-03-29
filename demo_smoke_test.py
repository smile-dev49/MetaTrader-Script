"""
Demo acceptance script: connect → place one market order → log → optional SL/TP modify → close → log.

1. Install MT5 terminal and log in to the demo account (or use env credentials).
2. Edit the TEST_* block below (symbol, volume, pips or fixed prices, modify demo flags).
3. Set MT5_LOGIN, MT5_PASSWORD, MT5_SERVER in .env or environment (see README).
   If you already logged in inside MT5, set MT5_USE_EXISTING_SESSION=1 to skip mt5.login.
4. Run: `python demo_smoke_test.py` or `python main.py` (same entry).

FX symbols often return TRADE_RETCODE_MARKET_CLOSED on weekends or off-session; run during open market hours.
"""

from __future__ import annotations

import sys
import time

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

import MetaTrader5 as mt5

from mt5_trading import (
    ConnectConfig,
    account_summary,
    close_position,
    connect,
    find_positions,
    log_line,
    modify_position_sltp,
    place_market_order,
    shutdown,
)


# =============================================================================
# EDIT THESE — main parameters the client asked to expose
# =============================================================================
TEST_SYMBOL = "EURUSD"
# If TEST_SYMBOL hits MARKET_CLOSED (e.g. weekend FX), set a symbol your broker keeps open (crypto/metal),
# add it to Market Watch, and the script will retry once. Leave empty to skip retry.
TEST_ALT_SYMBOL = ""
TEST_VOLUME = 0.01
TEST_SIDE = "buy"  # "buy" or "sell"

# Magic number to tag this script's trades (filter when closing)
TEST_MAGIC = 20260329

# Slippage in points (not pips)
TEST_DEVIATION = 20

# If True, use TEST_SL_PRICE and TEST_TP_PRICE (absolute prices).
# If False, use TEST_SL_PIPS / TEST_TP_PIPS relative to entry at send time.
TEST_USE_FIXED_PRICES = False
TEST_SL_PRICE = 1.0500
TEST_TP_PRICE = 1.1200

# Distance in pips from entry when TEST_USE_FIXED_PRICES is False
TEST_SL_PIPS = 30.0
TEST_TP_PIPS = 40.0

# After open, optionally tighten/extend stops (pip distances from the same entry price_open).
# Set TEST_ENABLE_MODIFY_DEMO=False to skip and go straight to close.
TEST_ENABLE_MODIFY_DEMO = True
TEST_MODIFY_SL_PIPS = 25.0
TEST_MODIFY_TP_PIPS = 50.0

# Seconds to wait before looking up the new position (latency / netting)
TEST_POSITION_WAIT_SEC = 1.0


# =============================================================================
# Helpers
# =============================================================================
def _pip_size(symbol: str) -> float:
    """Approximate one pip in price units for FX/metals (good enough for demo SL/TP)."""
    info = mt5.symbol_info(symbol)
    if not info:
        return 0.0001
    point = info.point
    digits = info.digits
    if digits == 3 or digits == 5:
        return point * 10
    if digits == 2:
        return point * 10
    return point * 10 if point < 0.001 else point


def _sl_tp_from_pips(
    symbol: str,
    side: str,
    entry: float,
    sl_pips: float,
    tp_pips: float,
) -> tuple[float, float]:
    pip = _pip_size(symbol)
    s = side.lower()
    if s == "buy":
        sl = entry - sl_pips * pip
        tp = entry + tp_pips * pip
    else:
        sl = entry + sl_pips * pip
        tp = entry - tp_pips * pip
    return sl, tp


def _is_market_closed_result(res: object) -> bool:
    return getattr(res, "retcode", None) == mt5.TRADE_RETCODE_MARKET_CLOSED


def _attempt_open_smoke(symbol: str) -> tuple[bool, object | None]:
    """Build SL/TP for symbol and call place_market_order."""
    tick = mt5.symbol_info_tick(symbol)
    if not tick:
        log_line(f"No tick for {symbol!r}. Is it visible in Market Watch?")
        return False, None

    entry_ref = tick.ask if TEST_SIDE.lower() == "buy" else tick.bid

    if TEST_USE_FIXED_PRICES:
        sl_f, tp_f = float(TEST_SL_PRICE), float(TEST_TP_PRICE)
        sl_tp_msg = f"Using fixed SL={sl_f} TP={tp_f} (ref entry ~ {entry_ref})"
    else:
        sl_f, tp_f = _sl_tp_from_pips(
            symbol, TEST_SIDE, entry_ref, TEST_SL_PIPS, TEST_TP_PIPS
        )
        sl_tp_msg = (
            f"Using SL/TP from pips: SL={TEST_SL_PIPS} TP={TEST_TP_PIPS} "
            f"→ sl={sl_f:.5f} tp={tp_f:.5f} (ref entry ~ {entry_ref:.5f})"
        )

    log_line(sl_tp_msg)
    ok, res = place_market_order(
        symbol,
        TEST_SIDE,
        TEST_VOLUME,
        sl=sl_f,
        tp=tp_f,
        magic=TEST_MAGIC,
        comment="demo_smoke",
        deviation=TEST_DEVIATION,
    )
    return ok, res


def main() -> int:
    log_line("=== Demo smoke test: start ===")

    if not connect(ConnectConfig.from_env()):
        log_line("Abort: could not connect.")
        return 1

    try:
        account_summary()

        active_symbol = TEST_SYMBOL
        ok, res = _attempt_open_smoke(active_symbol)

        if (
            not ok
            and _is_market_closed_result(res)
            and (TEST_ALT_SYMBOL or "").strip()
        ):
            alt = (TEST_ALT_SYMBOL or "").strip()
            log_line(
                f"{TEST_SYMBOL!r} is market-closed on the server; retrying with TEST_ALT_SYMBOL={alt!r}."
            )
            active_symbol = alt
            ok, res = _attempt_open_smoke(active_symbol)

        if not ok and _is_market_closed_result(res):
            log_line(
                "Market is still closed for this symbol. You cannot fix that from code: wait for "
                "FX session (usually Mon–Fri) or set TEST_ALT_SYMBOL to an instrument your broker "
                "quotes 24/5 or 24/7 (verify exact name in Market Watch)."
            )

        if not ok:
            log_line("Open step failed; skipping close.")
            return 2

        time.sleep(TEST_POSITION_WAIT_SEC)

        positions = find_positions(symbol=active_symbol, magic=TEST_MAGIC)
        if not positions:
            positions = find_positions(symbol=active_symbol, magic=None)
            log_line(
                f"No position with magic={TEST_MAGIC}; open positions on {active_symbol}: {len(positions)}."
            )
            if len(positions) == 0:
                log_line(
                    "No open position found after fill — check Experts/Journal in MT5 or increase TEST_POSITION_WAIT_SEC."
                )
                return 3
            if len(positions) == 1:
                log_line("Closing the only open position on this symbol (demo fallback).")
                pos = positions[0]
            else:
                log_line("Multiple positions on symbol; cannot pick one safely. Close manually or use a unique magic.")
                return 3
        else:
            pos = positions[0]

        log_line(
            f"Open position: ticket={pos.ticket} vol={pos.volume} "
            f"price_open={pos.price_open} sl={pos.sl} tp={pos.tp}"
        )

        if TEST_ENABLE_MODIFY_DEMO:
            if TEST_USE_FIXED_PRICES:
                log_line(
                    "TEST_ENABLE_MODIFY_DEMO is True but TEST_USE_FIXED_PRICES is True — "
                    "skipping modify demo (set pip mode or extend script for fixed-price edits)."
                )
            else:
                new_sl, new_tp = _sl_tp_from_pips(
                    active_symbol,
                    TEST_SIDE,
                    pos.price_open,
                    TEST_MODIFY_SL_PIPS,
                    TEST_MODIFY_TP_PIPS,
                )
                log_line(
                    f"Modify step: new SL/TP from pips "
                    f"SL={TEST_MODIFY_SL_PIPS} TP={TEST_MODIFY_TP_PIPS} "
                    f"→ sl={new_sl:.5f} tp={new_tp:.5f} (entry {pos.price_open:.5f})"
                )
                if not modify_position_sltp(
                    int(pos.ticket),
                    active_symbol,
                    new_sl,
                    new_tp,
                ):
                    log_line("Modify step failed; attempting close anyway.")
                else:
                    refreshed = find_positions(symbol=active_symbol, magic=TEST_MAGIC)
                    if not refreshed:
                        refreshed = find_positions(symbol=active_symbol, magic=None)
                    if refreshed:
                        p2 = refreshed[0]
                        log_line(
                            f"Position after modify: ticket={p2.ticket} sl={p2.sl} tp={p2.tp}"
                        )

        again = mt5.positions_get(ticket=pos.ticket)
        if again:
            pos = again[0]

        c_ok, c_res = close_position(pos, deviation=TEST_DEVIATION, comment="demo_smoke_close")
        if not c_ok:
            log_line("Close step failed.")
            return 4

        log_line("=== Demo smoke test: completed successfully ===")
        return 0

    finally:
        shutdown()

    return 0


if __name__ == "__main__":
    sys.exit(main())
