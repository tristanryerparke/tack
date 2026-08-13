from pathlib import Path

from rhino_flow import run_flow


RHINO_TESTS = Path(__file__).with_name("rhino")


def test_allowed_child_move_updates_tack_offset(rhino_instance):
    run_flow(
        [
            ("script", RHINO_TESTS / "setup_bbox_circles.py"),
            ("script", RHINO_TESTS / "child_move_updates_offset.py"),
            ("command", "_Move 0,0,0 10,0,0"),
            ("script", RHINO_TESTS / "child_move_updates_offset.py"),
            ("script", RHINO_TESTS / "cleanup.py"),
        ],
        rhino_instance,
        environment={"debug": "true"},
    )
