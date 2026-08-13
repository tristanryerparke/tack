from pathlib import Path

from rhino_flow import run_flow


RHINO_TESTS = Path(__file__).with_name("rhino")


def test_polyline_split_breaks_when_advanced_reconciliation_is_disabled(
    rhino_instance,
):
    run_flow(
        [
            ("script", RHINO_TESTS / "polyline_split_setup.py"),
            ("script", RHINO_TESTS / "polyline_split_without_advanced.py"),
            ("command", "_Split _SelID {parent_id} _Enter _SelID {cutter_id} _Enter"),
            ("script", RHINO_TESTS / "polyline_split_without_advanced.py"),
            ("script", RHINO_TESTS / "polyline_split_cleanup.py"),
        ],
        rhino_instance,
        environment={"debug": "true"},
    )
