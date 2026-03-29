"""
Reusable MetaTrader 5 helpers for Python: connect, market orders, modify SL/TP, close.
Uses the official MetaTrader5 package. Logs retcodes and last_error() for debugging.
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import MetaTrader5 as mt5


def log_line(message: str, *, to_print: bool = True) -> str:
    """Timestamped log line (UTC)."""
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    line = f"[{stamp}] {message}"
    if to_print:
        print(line)
    return line


def _retcode_name(code: int) -> str:
    for name in dir(mt5):
        if name.startswith("TRADE_RETCODE_") and getattr(mt5, name) == code:
            return name
    return str(code)


@dataclass
class ConnectConfig:
    """Credentials from env or explicit values (never commit real passwords)."""

    login: Optional[int] = None
    password: Optional[str] = None
    server: Optional[str] = None
    terminal_path: Optional[str] = None

    @classmethod
    def from_env(cls) -> "ConnectConfig":
        login_raw = os.environ.get("MT5_LOGIN", "").strip()
        password = os.environ.get("MT5_PASSWORD", "").strip() or None
        server = os.environ.get("MT5_SERVER", "").strip() or None
        path = os.environ.get("MT5_TERMINAL_PATH", "").strip() or None
        login: Optional[int] = None
        if login_raw.isdigit():
            login = int(login_raw)
        return cls(login=login, password=password, server=server, terminal_path=path)


def connect(cfg: Optional[ConnectConfig] = None) -> bool:
    """
    Initialize MT5 and optionally log in.
    If login/password/server are set, uses them; else uses logged-in terminal session.
    """
    cfg = cfg or ConnectConfig.from_env()
    kwargs: Dict[str, Any] = {}
    if cfg.terminal_path:
        kwargs["path"] = cfg.terminal_path

    if not mt5.initialize(**kwargs):
        err = mt5.last_error()
        log_line(f"initialize() failed: {err}")
        code = err[0] if isinstance(err, tuple) and err else None
        if code == -10003 or (
            isinstance(err, tuple)
            and len(err) > 1
            and isinstance(err[1], str)
            and "not found" in err[1].lower()
        ):
            log_line(
                "Hint (-10003): Install MetaTrader 5 (64-bit) from your broker, then set "
                "MT5_TERMINAL_PATH in .env to the full path of terminal64.exe — for example "
                r"'C:\Program Files\MetaTrader 5\terminal64.exe' or under 'GO Markets MetaTrader 5'."
            )
            log_line(
                "Also use 64-bit Python: py -c \"import struct; print(struct.calcsize('P')*8)\"  → should print 64."
            )
        return False

    log_line("MT5 initialized.")

    if cfg.login and cfg.password and cfg.server:
        if not mt5.login(cfg.login, password=cfg.password, server=cfg.server):
            log_line(f"login() failed: {mt5.last_error()}")
            mt5.shutdown()
            return False
        log_line(f"Logged in to server {cfg.server!r} as {cfg.login}.")
    else:
        ti = mt5.terminal_info()
        if ti:
            log_line(f"Using existing terminal session: {ti.name!r} connected={ti.connected}")
        else:
            log_line("Warning: terminal_info() unavailable.")

    return True


def shutdown() -> None:
    mt5.shutdown()
    log_line("MT5 shutdown.")


def ensure_symbol(symbol: str) -> bool:
    if not mt5.symbol_select(symbol, True):
        log_line(f"symbol_select({symbol!r}) failed: {mt5.last_error()}")
        return False
    return True


def account_summary() -> None:
    ai = mt5.account_info()
    if not ai:
        log_line(f"account_info() failed: {mt5.last_error()}")
        return
    log_line(
        f"Account: login={ai.login} server={ai.server!r} "
        f"balance={ai.balance} equity={ai.equity} margin_free={ai.margin_free}"
    )


def get_filling_mode(symbol: str) -> int:
    """Pick a supported ORDER_FILLING_* for this symbol."""
    info = mt5.symbol_info(symbol)
    if not info:
        return mt5.ORDER_FILLING_IOC
    mode = info.filling_mode
    if mode & mt5.SYMBOL_FILLING_FOK:
        return mt5.ORDER_FILLING_FOK
    if mode & mt5.SYMBOL_FILLING_IOC:
        return mt5.ORDER_FILLING_IOC
    return mt5.ORDER_FILLING_RETURN


def normalize_volume(symbol: str, volume: float) -> float:
    """Clamp volume to broker min/max/step."""
    info = mt5.symbol_info(symbol)
    if not info:
        return volume
    step = info.volume_step
    vmin = info.volume_min
    vmax = info.volume_max
    if step <= 0:
        return max(vmin, min(vmax, volume))
    steps = round(volume / step)
    v = max(vmin, min(vmax, steps * step))
    return float(v)


def _min_stop_distance(symbol: str) -> float:
    info = mt5.symbol_info(symbol)
    if not info:
        return 0.0
    point = info.point
    level = info.trade_stops_level
    if level and level > 0:
        return level * point
    # Sensible default if broker reports 0
    return point * 10


def adjust_stops(
    symbol: str,
    order_type: int,
    price: float,
    sl: Optional[float],
    tp: Optional[float],
) -> Tuple[Optional[float], Optional[float], List[str]]:
    """
    Ensure SL/TP respect SYMBOL_TRADE_STOPS_LEVEL. Returns (sl, tp, notes).
    """
    info = mt5.symbol_info(symbol)
    if not info:
        return sl, tp, ["symbol_info missing"]
    digits = info.digits
    dist = _min_stop_distance(symbol)
    notes: List[str] = []

    def rnd(x: float) -> float:
        return round(x, digits)

    if order_type == mt5.ORDER_TYPE_BUY:
        if sl is not None and price - sl < dist:
            sl = rnd(price - dist)
            notes.append(f"SL raised to minimum distance ({dist}) below entry.")
        if tp is not None and tp - price < dist:
            tp = rnd(price + dist)
            notes.append(f"TP lowered to minimum distance ({dist}) above entry.")
    else:
        if sl is not None and sl - price < dist:
            sl = rnd(price + dist)
            notes.append(f"SL lowered to minimum distance ({dist}) above entry.")
        if tp is not None and price - tp < dist:
            tp = rnd(price - dist)
            notes.append(f"TP raised to minimum distance ({dist}) below entry.")

    if sl is not None:
        sl = rnd(sl)
    if tp is not None:
        tp = rnd(tp)
    return sl, tp, notes


def place_market_order(
    symbol: str,
    side: str,
    volume: float,
    *,
    sl: Optional[float] = None,
    tp: Optional[float] = None,
    magic: int = 0,
    comment: str = "python_mt5",
    deviation: int = 20,
) -> Tuple[bool, Optional[Any]]:
    """
    Open a market position. side: 'buy' or 'sell'.
    Returns (ok, result_or_none).
    """
    if not ensure_symbol(symbol):
        return False, None

    side_l = side.lower().strip()
    if side_l not in ("buy", "sell"):
        log_line(f"Invalid side {side!r}; use 'buy' or 'sell'.")
        return False, None

    vol = normalize_volume(symbol, volume)
    if vol <= 0:
        log_line("Normalized volume is zero; check min lot.")
        return False, None

    tick = mt5.symbol_info_tick(symbol)
    if not tick:
        log_line(f"No tick for {symbol}: {mt5.last_error()}")
        return False, None

    order_type = mt5.ORDER_TYPE_BUY if side_l == "buy" else mt5.ORDER_TYPE_SELL
    price = tick.ask if order_type == mt5.ORDER_TYPE_BUY else tick.bid

    sl_adj, tp_adj, notes = adjust_stops(symbol, order_type, price, sl, tp)
    for n in notes:
        log_line(n)

    filling = get_filling_mode(symbol)
    request: Dict[str, Any] = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": symbol,
        "volume": vol,
        "type": order_type,
        "price": price,
        "deviation": deviation,
        "magic": magic,
        "comment": comment[:31],
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": filling,
    }
    if sl_adj is not None:
        request["sl"] = sl_adj
    if tp_adj is not None:
        request["tp"] = tp_adj

    log_line(
        f"Sending MARKET {side_l.upper()} {symbol} vol={vol} price={price} "
        f"sl={sl_adj} tp={tp_adj} filling={filling} deviation={deviation}"
    )

    result = mt5.order_send(request)
    if result is None:
        log_line(f"order_send returned None: {mt5.last_error()}")
        return False, None

    if result.retcode != mt5.TRADE_RETCODE_DONE:
        log_line(
            f"order_send failed: retcode={result.retcode} ({_retcode_name(result.retcode)}) "
            f"comment={getattr(result, 'comment', '')!r} last_error={mt5.last_error()}"
        )
        return False, result

    log_line(
        f"Order done: deal={result.deal} order={result.order} "
        f"volume={result.volume} price={result.price}"
    )
    return True, result


def modify_position_sltp(
    position_ticket: int,
    symbol: str,
    sl: Optional[float],
    tp: Optional[float],
) -> bool:
    """Modify SL/TP on an open position."""
    request = {
        "action": mt5.TRADE_ACTION_SLTP,
        "position": position_ticket,
        "symbol": symbol,
        "sl": sl if sl is not None else 0.0,
        "tp": tp if tp is not None else 0.0,
    }
    log_line(f"Modifying SLTP position={position_ticket} {symbol} sl={sl} tp={tp}")
    result = mt5.order_send(request)
    if result is None:
        log_line(f"modify SLTP None: {mt5.last_error()}")
        return False
    if result.retcode != mt5.TRADE_RETCODE_DONE:
        log_line(
            f"modify SLTP failed: {_retcode_name(result.retcode)} {mt5.last_error()}"
        )
        return False
    log_line("SL/TP updated.")
    return True


def find_positions(
    symbol: Optional[str] = None,
    magic: Optional[int] = None,
) -> Tuple[mt5.TradePosition, ...]:
    """Return open positions, optionally filtered by symbol and magic."""
    positions = mt5.positions_get(symbol=symbol) if symbol else mt5.positions_get()
    if not positions:
        return tuple()
    if magic is None:
        return positions
    return tuple(p for p in positions if p.magic == magic)


def close_position(
    position: Any,
    *,
    deviation: int = 20,
    comment: str = "python_close",
) -> Tuple[bool, Optional[Any]]:
    """Close a single position by ticket (market close)."""
    symbol = position.symbol
    if not ensure_symbol(symbol):
        return False, None

    tick = mt5.symbol_info_tick(symbol)
    if not tick:
        log_line(f"No tick for close {symbol}: {mt5.last_error()}")
        return False, None

    if position.type == mt5.POSITION_TYPE_BUY:
        order_type = mt5.ORDER_TYPE_SELL
        price = tick.bid
    else:
        order_type = mt5.ORDER_TYPE_BUY
        price = tick.ask

    filling = get_filling_mode(symbol)
    request: Dict[str, Any] = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": symbol,
        "volume": position.volume,
        "type": order_type,
        "position": position.ticket,
        "price": price,
        "deviation": deviation,
        "magic": position.magic,
        "comment": comment[:31],
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": filling,
    }

    log_line(
        f"Closing position ticket={position.ticket} {symbol} vol={position.volume} "
        f"type={order_type} price={price}"
    )

    result = mt5.order_send(request)
    if result is None:
        log_line(f"close order_send None: {mt5.last_error()}")
        return False, None
    if result.retcode != mt5.TRADE_RETCODE_DONE:
        log_line(
            f"Close failed: {_retcode_name(result.retcode)} {mt5.last_error()} "
            f"comment={getattr(result, 'comment', '')!r}"
        )
        return False, result

    log_line(
        f"Position closed: deal={result.deal} volume={result.volume} price={result.price}"
    )
    return True, result


def close_positions_by_filter(
    symbol: str,
    *,
    magic: Optional[int] = None,
    deviation: int = 20,
    pause_sec: float = 0.25,
) -> int:
    """
    Close all positions for symbol (optional magic). Returns number closed successfully.
    """
    closed = 0
    # Re-fetch until none left (hedging may have multiple)
    while True:
        positions = find_positions(symbol=symbol, magic=magic)
        if not positions:
            break
        pos = positions[0]
        ok, _ = close_position(pos, deviation=deviation)
        if ok:
            closed += 1
        time.sleep(pause_sec)
    return closed
