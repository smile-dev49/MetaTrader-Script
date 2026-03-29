# ========================================================
# pullback_breakout_bot.py
# MT5 Pullback/Breakout Bot - Conservative + Advanced Trailing
# NEW: Every 5-pip profit → ADD double original volume (pyramiding)
#      SL always kept at original risk distance from current price
# ========================================================

import json
import math
import os
import time
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta, timezone
from typing import Dict, Optional

import MetaTrader5 as mt5
import pandas as pd


# ============================================================
# CONFIGURATION
# ============================================================
CONFIG = {
    "account": {
        "login": None,
        "password": None,
        "server": None,
    },
    "symbols": [
        "USDJPY", "GBPUSD", "USDCHF", "NZDUSD", "AUDUSD", "EURUSD",
        "XAUUSD", "XAGUSD", "BTCUSD"
    ],
    "strategy": {
        "htf_timeframe": mt5.TIMEFRAME_H1,
        "entry_timeframe": mt5.TIMEFRAME_M5,
        "structure_lookback_bars": 120,
        "atr_period": 14,
        "fast_ma_period": 50,
        "slow_ma_period": 200,
        "range_lookback_bars": 60,

        "pullback_zone_atr_multiple": 0.25,
        "breakout_buffer_atr_multiple": 0.15,
        "stop_buffer_atr_multiple": 0.35,
        "take_profit_r_multiple": 1.8,
        "partial_tp_r_multiple": 1.0,
        "move_to_be_after_partial": True,

        # Advanced Chandelier Trailing
        "trailing_start_after_r": 1.0,
        "trailing_atr_multiple_wide": 2.0,
        "trailing_atr_multiple_tight": 1.0,
        "trailing_tighten_after_r": 2.5,
        "trailing_max_lookback_bars": 60,

        # NEW: Pyramiding every 5 pips
        "pyramid_every_pips": 5.0,           # Every X pips profit, add double volume
    },
    "risk": {
        "risk_per_trade_pct": 0.25,
        "max_daily_loss_pct": 1.5,
        "max_total_drawdown_pct": 5.0,
        "cooldown_hours_after_total_drawdown": 72,
        "max_spread_pips_fx": 2.0,
        "max_spread_points_metals": 80,
        "max_slippage_points": 20,
        "min_lot": 0.01,
        "max_lot": 1.00,
        "lot_step": 0.01,
        "symbol_cooldown_minutes_after_loss": 60,
    },
    "timing": {
        "poll_seconds": 10,
        "timezone_offset_hours": 11,
        "trade_sessions": {
            "tokyo": False,
            "london": True,
            "new_york": True,
            "overlap": True,
        },
        "session_hours_sydney": {
            "tokyo": (9, 17),
            "london": (17, 1),
            "new_york": (23, 7),
            "overlap": (23, 1),
        },
    },
    "news": {"blackouts": []},
    "files": {
        "state_file": "bot_state.json",
        "trade_log_csv": "trade_log.csv",
        "debug_log": "bot_debug.log",
    },
}


# ============================================================
# UTILITIES
# ============================================================
def log_debug(message: str) -> None:
    stamp = datetime.utcnow().isoformat()
    line = f"[{stamp}] {message}"
    print(line)
    try:
        with open(CONFIG["files"]["debug_log"], "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


@dataclass
class PositionPlan:
    symbol: str
    side: str
    entry: float
    sl: float
    tp: float
    volume: float
    reason: str
    atr: float
    htf_bias: str


@dataclass
class BotState:
    start_equity: float = 0.0
    daily_start_equity: float = 0.0
    daily_date: str = ""
    cooldown_until_utc: str = ""
    last_signal_time: Dict[str, str] = None
    original_volume: Dict[str, float] = None          # Original entry volume
    original_risk_distance: Dict[str, float] = None   # Fixed SL distance
    last_pyramid_level: Dict[str, float] = None       # Last profit pips where we pyramided

    def __post_init__(self):
        if self.last_signal_time is None: self.last_signal_time = {}
        if self.original_volume is None: self.original_volume = {}
        if self.original_risk_distance is None: self.original_risk_distance = {}
        if self.last_pyramid_level is None: self.last_pyramid_level = {}


def load_state() -> BotState:
    path = CONFIG["files"]["state_file"]
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return BotState(**data)
        except Exception:
            pass
    return BotState()


def save_state(state: BotState) -> None:
    try:
        with open(CONFIG["files"]["state_file"], "w", encoding="utf-8") as f:
            json.dump(asdict(state), f, indent=2)
    except Exception as e:
        log_debug(f"Failed to save state: {e}")


def append_trade_log(row: Dict) -> None:
    try:
        df = pd.DataFrame([row])
        header = not os.path.exists(CONFIG["files"]["trade_log_csv"])
        df.to_csv(CONFIG["files"]["trade_log_csv"], mode="a", header=header, index=False)
    except Exception:
        pass


# ============================================================
# MT5 HELPERS (shortened)
# ============================================================
def initialize_mt5() -> None:
    account_cfg = CONFIG["account"]
    ok = mt5.initialize(**{k: v for k, v in account_cfg.items() if v}) if any(account_cfg.values()) else mt5.initialize()
    if not ok:
        raise RuntimeError(f"MT5 init failed: {mt5.last_error()}")
    log_debug("MT5 initialized")


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def get_rates(symbol: str, timeframe: int, count: int) -> pd.DataFrame:
    rates = mt5.copy_rates_from_pos(symbol, timeframe, 0, count)
    if not rates or len(rates) == 0:
        raise RuntimeError(f"No rates for {symbol}")
    df = pd.DataFrame(rates)
    df["time"] = pd.to_datetime(df["time"], unit="s", utc=True)
    return df


def atr(df: pd.DataFrame, period: int) -> pd.Series:
    prev = df["close"].shift(1)
    tr = pd.concat([df["high"]-df["low"], (df["high"]-prev).abs(), (df["low"]-prev).abs()], axis=1).max(axis=1)
    return tr.rolling(period).mean()


def pip_distance(symbol: str, p1: float, p2: float) -> float:
    info = mt5.symbol_info(symbol)
    point = info.point if info else 0.00001
    multiplier = 10 if "JPY" in symbol or "XAU" in symbol or "XAG" in symbol or "BTC" in symbol else 1
    return abs(p1 - p2) / point / multiplier


# (Keep all your original functions: spread_ok, get_htf_bias, candle_parts, signal_pullback_rejection, 
#  signal_breakout_retest, estimate_position_size, place_market_order, risk checks, etc.)

# ============================================================
# MAIN POSITION MANAGEMENT - WITH PYRAMIDING + FIXED DISTANCE SL
# ============================================================
def manage_open_positions(symbol: str, state: BotState) -> None:
    positions = mt5.positions_get(symbol=symbol)
    if not positions:
        return

    tick = mt5.symbol_info_tick(symbol)
    if not tick:
        return

    pos_type = positions[0].type
    current_price = tick.bid if pos_type == mt5.POSITION_TYPE_BUY else tick.ask
    direction = 1 if pos_type == mt5.POSITION_TYPE_BUY else -1

    # Calculate current profit in pips from the first (original) entry
    orig_entry = positions[0].price_open
    profit_pips = pip_distance(symbol, current_price, orig_entry) * direction

    orig_volume = state.original_volume.get(symbol, positions[0].volume)
    orig_risk_dist = state.original_risk_distance.get(symbol, abs(positions[0].price_open - positions[0].sl))
    last_level = state.last_pyramid_level.get(symbol, 0.0)

    # === 1. FIXED DISTANCE TRAILING SL (SL stays same distance from current price) ===
    if orig_risk_dist > 0:
        new_sl = current_price - (orig_risk_dist * direction)
        for pos in positions:
            if abs(pos.sl - new_sl) > 0.00005:   # small threshold to avoid spam
                modify = {
                    "action": mt5.TRADE_ACTION_SLTP,
                    "position": pos.ticket,
                    "symbol": symbol,
                    "sl": new_sl,
                    "tp": pos.tp,
                }
                result = mt5.order_send(modify)
                if result and result.retcode == mt5.TRADE_RETCODE_DONE:
                    log_debug(f"Fixed-distance SL updated {symbol} | New SL = {new_sl:.5f} (dist={orig_risk_dist:.5f})")

    # === 2. PYRAMID: Add DOUBLE original volume every 5 pips profit ===
    pyramid_step = CONFIG["strategy"]["pyramid_every_pips"]
    next_level = last_level + pyramid_step

    if profit_pips >= next_level:
        new_volume = min(CONFIG["risk"]["max_lot"], orig_volume * 2.0)

        # Open additional position with double volume
        order_type = mt5.ORDER_TYPE_BUY if pos_type == mt5.POSITION_TYPE_BUY else mt5.ORDER_TYPE_SELL
        price = tick.ask if order_type == mt5.ORDER_TYPE_BUY else tick.bid

        new_sl = price - (orig_risk_dist * direction)
        new_tp = price + (price - new_sl) * CONFIG["strategy"]["take_profit_r_multiple"] if direction == 1 else price - (new_sl - price) * CONFIG["strategy"]["take_profit_r_multiple"]

        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": symbol,
            "volume": new_volume,
            "type": order_type,
            "price": price,
            "sl": new_sl,
            "tp": new_tp,
            "deviation": CONFIG["risk"]["max_slippage_points"],
            "magic": 26032026,
            "comment": "pyramid_double_volume",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }

        result = mt5.order_send(request)
        if result and result.retcode == mt5.TRADE_RETCODE_DONE:
            log_debug(f"PYRAMID ADDED {symbol} | +{new_volume:.2f} vol at {price:.5f} | Profit so far: {profit_pips:.1f} pips")

            # Update state
            state.original_volume[symbol] = orig_volume          # keep original base volume
            state.original_risk_distance[symbol] = orig_risk_dist
            state.last_pyramid_level[symbol] = next_level
            save_state(state)


# ============================================================
# MAIN LOOP
# ============================================================
def main_loop() -> None:
    initialize_mt5()
    state = load_state()

    log_debug("=== Pullback/Breakout Bot Started - Pyramiding Every 5 Pips + Fixed Distance SL ===")

    while True:
        try:
            # ... (your existing risk checks, session checks, daily loss, drawdown, etc. - keep as before)

            for symbol in CONFIG["symbols"]:
                try:
                    manage_open_positions(symbol, state)   # Now passes state

                    # Only look for new entries if we don't have positions yet
                    if len(mt5.positions_get(symbol=symbol) or []) == 0:
                        plan = get_signal(symbol, state)   # your existing get_signal function
                        if plan:
                            if place_market_order(plan):
                                # Save original values for pyramiding
                                state.original_volume[symbol] = plan.volume
                                state.original_risk_distance[symbol] = abs(plan.entry - plan.sl)
                                state.last_pyramid_level[symbol] = 0.0
                                state.last_signal_time[symbol] = now_utc().isoformat()
                                save_state(state)
                except Exception as e:
                    log_debug(f"Error on {symbol}: {e}")

            time.sleep(CONFIG["timing"]["poll_seconds"])

        except KeyboardInterrupt:
            log_debug("Bot stopped by user")
            break
        except Exception as e:
            log_debug(f"Main loop error: {e}")
            time.sleep(CONFIG["timing"]["poll_seconds"])

    mt5.shutdown()


if __name__ == "__main__":
    main_loop()