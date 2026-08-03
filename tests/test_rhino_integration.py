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
            child_results = watcher.take_data(timeout=10)
            assert len(child_results) == 1, "Unexpected child test data: {}".format(
                child_results
            )

            watcher.run_file(RHINO_TESTS / "test_parent_move.py")
            parent_results = watcher.take_data(timeout=10)
            assert len(parent_results) == 1, "Unexpected parent test data: {}".format(
                parent_results
            )

            watcher.run_file(RHINO_TESTS / "test_multiple_tacks.py")
            multiple_results = watcher.take_data(timeout=10)
            assert len(multiple_results) == 1, (
                "Unexpected multiple-Tack test data: {}".format(multiple_results)
            )
            child_result = child_results[0]
            parent_result = parent_results[0]
            multiple_result = multiple_results[0]
            assert child_result["name"] == "child_move_restores_child"
            assert child_result["child_anchors"] == child_result["expected_child_anchors"]
            assert parent_result["name"] == "parent_move_translates_child"
            assert parent_result["child_anchors"] == parent_result["expected_child_anchors"]
            assert multiple_result["name"] == (
                "multiple_tacks_survive_simultaneous_move"
            )
            assert multiple_result["first_child_anchors"] == multiple_result[
                "expected_first_child_anchors"
            ]
            assert multiple_result["second_child_anchors"] == multiple_result[
                "expected_second_child_anchors"
            ]
            print("PASS master_child_parent_and_multiple_tack_verification")
        finally:
            watcher.run_file(RHINO_TESTS / "cleanup.py")


if __name__ == "__main__":
    test_child_and_parent_move_integration()
