"""Run with: uv run --with pytest pytest -s tests/test_rhino_child_move_updates_offset.py"""
from pathlib import Path

from run_in_rhino import start_server


RHINO_TESTS = Path(__file__).with_name("rhino")
SETUP = RHINO_TESTS / "setup_bbox_circles.py"
MOVE = RHINO_TESTS / "child_move_updates_offset.py"
CLEANUP = RHINO_TESTS / "cleanup.py"


def test_allowed_child_move_updates_tack_offset():
    with start_server(environment={"debug": "true"}) as watcher:
        watcher.run_file(SETUP)
        try:
            watcher.run_file(MOVE)
        finally:
            watcher.run_file(CLEANUP)
        results = watcher.take_data(timeout=120)

    assert [result["name"] for result in results] == [
        "child_move_updates_offset_when_allowed",
    ]
    assert results[0]["offset_after"][0] == results[0]["offset_before"][0] + 10
