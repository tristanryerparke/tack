from pathlib import Path

from rhino_flow import run_flow


RHINO_TESTS = Path(__file__).with_name("rhino")


def test_child_and_parent_move_integration(rhino_instance):
    run_flow(
        [
            ("script", RHINO_TESTS / "rhino_bbox_analysis.py"),
            ("script", RHINO_TESTS / "rhino_document_runtime.py"),
            ("script", RHINO_TESTS / "setup_bbox_circles.py"),
            ("script", RHINO_TESTS / "child_move.py"),
            ("command", "_Move 0,0,0 10,0,0"),
            ("script", RHINO_TESTS / "child_move.py"),
            ("script", RHINO_TESTS / "rhino_parent_move.py"),
            ("command", "_Move 0,0,0 10,0,0"),
            ("script", RHINO_TESTS / "rhino_parent_move.py"),
            ("script", RHINO_TESTS / "rhino_multiple_tacks.py"),
            ("command", "_Move 0,0,0 0,10,0"),
            ("script", RHINO_TESTS / "rhino_multiple_tacks.py"),
            ("script", RHINO_TESTS / "cleanup.py"),
        ],
        rhino_instance,
        environment={"debug": "true"},
    )
