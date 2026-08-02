"""Run with: uv run pytest -s tests/test_rhino_integration.py"""
from pathlib import Path

from run_in_rhino import start_server


RHINO_TESTS = Path(__file__).with_name("rhino")


def test_child_and_parent_move_integration():
    with start_server() as watcher:
        try:
            watcher.run_file(RHINO_TESTS / "test_bbox_analysis.py")
            watcher.run_file(RHINO_TESTS / "setup_bbox_circles.py")
            watcher.run_file(RHINO_TESTS / "child_move.py")
            watcher.run_file(RHINO_TESTS / "test_parent_move.py")
            watcher.run_file(RHINO_TESTS / "test_multiple_tacks.py")
            results = watcher.take_data(timeout=10)
            if len(results) < 3:
                results.extend(watcher.take_data(timeout=10))
            assert len(results) == 3, "Unexpected Rhino test data: {}".format(results)
            child_result, parent_result, multiple_result = results
            assert child_result["name"] == "child_move_restores_child"
            assert child_result["child_anchors"] == child_result["expected_child_anchors"]
            assert parent_result["name"] == "parent_move_translates_child"
            assert parent_result["child_anchors"] == parent_result["expected_child_anchors"]
            assert multiple_result["name"] == "multiple_tacks_are_independent"
            assert multiple_result["second_child_anchors"] == multiple_result[
                "expected_second_child_anchors"
            ]
            print("PASS master_child_parent_and_multiple_tack_verification")
        finally:
            watcher.run_file(RHINO_TESTS / "cleanup.py")


if __name__ == "__main__":
    test_child_and_parent_move_integration()
