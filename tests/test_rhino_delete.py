from pathlib import Path

from rhino_flow import run_flow


RHINO_TESTS = Path(__file__).with_name("rhino")


def test_deleting_a_tack_child_breaks_its_relationship(rhino_instance):
    results = run_flow(
        [
            ("script", RHINO_TESTS / "setup_bbox_circles.py"),
            ("script", RHINO_TESTS / "delete_child_breaks_tack.py"),
            ("script", RHINO_TESTS / "cleanup.py"),
        ],
        rhino_instance,
        environment={"debug": "true"},
    )
    result = next(item for item in results if item["name"] == "delete_child_breaks_tack")
    assert "could not be recovered" in result["reason"]
