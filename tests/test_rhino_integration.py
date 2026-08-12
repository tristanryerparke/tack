from pathlib import Path

from rhino_flow import run_flow


RHINO_TESTS = Path(__file__).with_name("rhino")


def test_child_and_parent_move_integration():
    results = run_flow(
        [
            ("script_now", RHINO_TESTS / "rhino_bbox_analysis.py"),
            ("script_now", RHINO_TESTS / "rhino_document_runtime.py"),
            ("script", RHINO_TESTS / "setup_bbox_circles.py"),
            ("script", RHINO_TESTS / "child_move.py"),
            ("script", RHINO_TESTS / "rhino_parent_move.py"),
            ("script", RHINO_TESTS / "rhino_multiple_tacks.py"),
            ("script", RHINO_TESTS / "cleanup.py"),
        ],
        environment={"debug": "true"},
    )
    by_name = {result["name"]: result for result in results}
    assert by_name["child_move_restores_child"]["child_anchors"] == by_name[
        "child_move_restores_child"
    ]["expected_child_anchors"]
    assert by_name["parent_move_translates_child"]["child_anchors"] == by_name[
        "parent_move_translates_child"
    ]["expected_child_anchors"]
    multiple = by_name["multiple_tacks_survive_simultaneous_move"]
    assert multiple["first_child_anchors"] == multiple["expected_first_child_anchors"]
    assert multiple["second_child_anchors"] == multiple["expected_second_child_anchors"]
