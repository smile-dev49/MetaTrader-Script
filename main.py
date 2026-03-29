"""
Convenience entry point for the client demo.

Runs the same flow as `demo_smoke_test.py`: connect → market order → optional SL/TP modify → close.

Usage (from the project root, with MT5 running and `.env` configured):

    python main.py
"""

from __future__ import annotations

import sys

from demo_smoke_test import main


if __name__ == "__main__":
    raise SystemExit(main())
