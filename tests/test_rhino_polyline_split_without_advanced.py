"""Run with: uv run --with pytest pytest -s tests/test_rhino_polyline_split_without_advanced.py"""
from pathlib import Path

from run_in_rhino import start_server


RHINO_TESTS = Path(__file__).with_name("rhino")
SETUP = RHINO_TESTS / "polyline_split_setup.py"
SPLIT = RHINO_TESTS / "polyline_split_without_advanced.py"
CLEANUP = RHINO_TESTS / "polyline_split_cleanup.py"


def test_polyline_split_breaks_when_advanced_reconciliation_is_disabled():
    with start_server(environment={"debug": "true"}) as watcher:
        watcher.run_file(SETUP)
        setup_results = watcher.take_data(timeout=10)
        assert len(setup_results) == 1
        try:
            watcher.run_file(SPLIT)
        finally:
            watcher.run_file(CLEANUP)
        results = watcher.take_data(timeout=120)

    assert [result["name"] for result in results] == [
        "polyline_split_breaks_without_advanced_reconciliation",
    ]
    assert "linked parent" in results[0]["reason"]
