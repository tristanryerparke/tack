from pathlib import Path

from rhino_flow import run_flow


RHINO_TESTS = Path(__file__).with_name("rhino")


def test_polyline_split_and_undo_preserve_tack():
    results = run_flow(
        [
            ("script", RHINO_TESTS / "polyline_split_setup.py"),
            ("command", "_Split _SelID {parent_id} _Enter _SelID {cutter_id} _Enter"),
            ("script", RHINO_TESTS / "polyline_split_collect.py"),
            ("command", "_Undo _Enter"),
            ("script", RHINO_TESTS / "polyline_split_undo_collect.py"),
            ("script", RHINO_TESTS / "polyline_split_cleanup.py"),
        ],
        environment={"debug": "true"},
    )
    setup, split, undo = results
    assert split["old_parent_id"] != split["new_parent_id"]
    assert split["split_candidate_count"] >= 2
    assert split["matching_candidate_count"] == 1
    assert undo["restored_parent_id"] == setup["parent_id"]
    assert undo["link_parent_id"] == setup["parent_id"]
