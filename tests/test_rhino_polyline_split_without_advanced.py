from pathlib import Path

from rhino_flow import run_flow


RHINO_TESTS = Path(__file__).with_name("rhino")


def test_polyline_split_breaks_when_advanced_reconciliation_is_disabled():
    results = run_flow(
        [
            ("script", RHINO_TESTS / "polyline_split_setup.py"),
            ("script", RHINO_TESTS / "polyline_split_without_advanced.py"),
            ("script", RHINO_TESTS / "polyline_split_cleanup.py"),
        ],
        environment={"debug": "true"},
    )
    result = next(
        item for item in results
        if item.get("name") == "polyline_split_breaks_without_advanced_reconciliation"
    )
    assert "linked parent" in result["reason"]
