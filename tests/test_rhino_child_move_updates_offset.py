from pathlib import Path

from rhino_flow import run_flow


RHINO_TESTS = Path(__file__).with_name("rhino")


def test_allowed_child_move_updates_tack_offset():
    results = run_flow(
        [
            ("script", RHINO_TESTS / "setup_bbox_circles.py"),
            ("script", RHINO_TESTS / "child_move_updates_offset.py"),
            ("script", RHINO_TESTS / "cleanup.py"),
        ],
        environment={"debug": "true"},
    )
    result = next(
        item for item in results
        if item["name"] == "child_move_updates_offset_when_allowed"
    )
    assert result["offset_after"][0] == result["offset_before"][0] + 10
