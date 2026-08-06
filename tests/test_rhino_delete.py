from pathlib import Path

from run_in_rhino import start_server


RHINO_TESTS = Path(__file__).with_name("rhino")
SETUP = RHINO_TESTS / "setup_bbox_circles.py"
DELETE_CHILD = RHINO_TESTS / "delete_child_breaks_tack.py"
CLEANUP = RHINO_TESTS / "cleanup.py"


def test_deleting_a_tack_child_breaks_its_relationship():
    with start_server(environment={"debug": "true"}) as watcher:
        watcher.run_file(SETUP)
        try:
            watcher.run_file(DELETE_CHILD)
            results = watcher.take_data(timeout=30)
        finally:
            watcher.run_file(CLEANUP)

    assert len(results) == 1, "Unexpected delete-test data: {}".format(results)
    assert results[0]["name"] == "delete_child_breaks_tack"
    assert "could not be recovered" in results[0]["reason"]
