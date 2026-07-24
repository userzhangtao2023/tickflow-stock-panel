from __future__ import annotations

import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_dow_watch_overview_load_behavioral_suite() -> None:
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


def test_dow_watch_url_market_behavioral_suite() -> None:
    subprocess.run(
        [
            str(ROOT / "frontend" / "node_modules" / ".bin" / "vitest"),
            "run",
            "src/pages/DowMonitor.test.tsx",
            "-t",
            "uses the URL market",
        ],
        cwd=ROOT / "frontend",
        check=True,
    )
