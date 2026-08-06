"""Run with: uv run --with pytest pytest -s tests/test_rhino_polyline_split.py"""
from pathlib import Path

from run_in_rhino import start_server


RHINO_TESTS = Path(__file__).with_name("rhino")
SETUP = RHINO_TESTS / "polyline_split_setup.py"
COLLECT_SPLIT = RHINO_TESTS / "polyline_split_collect.py"
COLLECT_UNDO = RHINO_TESTS / "polyline_split_undo_collect.py"
CLEANUP = RHINO_TESTS / "polyline_split_cleanup.py"


def test_polyline_split_and_undo_preserve_tack():
    with start_server(environment={"debug": "true"}) as watcher:
        watcher.run_file(SETUP)
        setup_results = watcher.take_data(timeout=10)
        assert len(setup_results) == 1
        setup = setup_results[0]
        try:
            watcher.run_command(
                "_Split _SelID {} _Enter _SelID {} _Enter".format(
                    setup["parent_id"],
                    setup["cutter_id"],
                )
            )
            watcher.run_file(COLLECT_SPLIT)
            watcher.run_command("_Undo")
            watcher.run_file(COLLECT_UNDO)
        finally:
            watcher.run_file(CLEANUP)
        results = watcher.take_data(timeout=120)

    assert [result["name"] for result in results] == [
        "polyline_split_preserves_tack",
        "polyline_split_undo_restores_tack",
    ]
    assert results[0]["old_parent_id"] != results[0]["new_parent_id"]
    assert results[0]["split_candidate_count"] >= 2
    assert results[0]["matching_candidate_count"] == 1
    assert results[1]["restored_parent_id"] == results[0]["old_parent_id"]
    assert results[1]["link_parent_id"] == results[0]["old_parent_id"]
