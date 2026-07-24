from __future__ import annotations

import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_closed_session_tail_behavioral_suite() -> None:
    subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "backend/tests/test_dow_monitor_data_integrity.py",
            "-q",
        ],
        cwd=ROOT,
        check=True,
    )


def test_monitor_symbol_authority_behavioral_suite() -> None:
    subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "backend/tests/test_dow_monitor_api.py",
            "-q",
        ],
        cwd=ROOT,
        check=True,
    )


def test_dow_mini_chart_window_behavioral_suite() -> None:
    subprocess.run(
        [
            str(ROOT / "frontend" / "node_modules" / ".bin" / "vitest"),
            "run",
            "src/pages/DowMonitor.test.tsx",
            "-t",
            "renders only the latest 80 valid bars",
        ],
        cwd=ROOT / "frontend",
        check=True,
    )
