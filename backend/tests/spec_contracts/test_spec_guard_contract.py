import subprocess
import sys
from pathlib import Path


def test_repository_specification_contract_passes() -> None:
    repository = Path(__file__).resolve().parents[3]
    completed = subprocess.run(
        [sys.executable, str(repository / "scripts" / "check_spec_compliance.py")],
        cwd=repository,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr


def test_dow_watch_exception_defers_traceability_promotion_to_task_12() -> None:
    repository = Path(__file__).resolve().parents[3]
    decision = repository / "docs" / "decisions" / "2026-07-23-dow-realtime-watch-panel.md"
    index = repository / "docs" / "spec-index.yaml"

    assert "Task 12" in decision.read_text(encoding="utf-8")
    assert "Task 12" in index.read_text(encoding="utf-8")
    assert "2026-08-06" in index.read_text(encoding="utf-8")
