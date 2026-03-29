"""Unit tests for mt5_trading helpers (mocked MT5; no terminal required)."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

import mt5_trading as m


def test_log_line_format():
    line = m.log_line("hello", to_print=False)
    assert "] hello" in line
    assert line.startswith("[")


def test_connect_config_from_env(monkeypatch):
    monkeypatch.setenv("MT5_LOGIN", "12345")
    monkeypatch.setenv("MT5_PASSWORD", "secret")
    monkeypatch.setenv("MT5_SERVER", "Broker-Demo")
    monkeypatch.setenv("MT5_TERMINAL_PATH", r"C:\MT5\terminal64.exe")
    monkeypatch.setenv("MT5_USE_EXISTING_SESSION", "1")
    cfg = m.ConnectConfig.from_env()
    assert cfg.login == 12345
    assert cfg.password == "secret"
    assert cfg.server == "Broker-Demo"
    assert cfg.terminal_path == r"C:\MT5\terminal64.exe"
    assert cfg.use_existing_session is True


def test_normalize_volume_rounds_to_step():
    info = SimpleNamespace(volume_step=0.01, volume_min=0.01, volume_max=10.0)
    mock_mt5 = MagicMock()
    mock_mt5.symbol_info.return_value = info
    with patch.object(m, "mt5", mock_mt5):
        assert m.normalize_volume("EURUSD", 0.015) == pytest.approx(0.02)


def test_adjust_stops_buy_raises_sl_when_too_tight():
    """SL too close to bid → pushed down by stop level."""
    info = SimpleNamespace(point=0.00001, digits=5, trade_stops_level=30)
    mock_mt5 = MagicMock()
    mock_mt5.symbol_info.return_value = info
    mock_mt5.ORDER_TYPE_BUY = 0
    mock_mt5.ORDER_TYPE_SELL = 1
    with patch.object(m, "mt5", mock_mt5):
        price = 1.10000
        sl, tp, notes = m.adjust_stops("EURUSD", 0, price, 1.09999, 1.10100)
    assert sl is not None
    assert tp is not None
    assert price - sl >= 30 * 0.00001 - 1e-9
    assert notes  # expect at least one adjustment note


def test_get_filling_mode_fallback_when_no_symbol():
    mock_mt5 = MagicMock()
    mock_mt5.symbol_info.return_value = None
    mock_mt5.ORDER_FILLING_IOC = 1
    with patch.object(m, "mt5", mock_mt5):
        assert m.get_filling_mode("XYZ") == 1
