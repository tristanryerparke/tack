"""Run with: uv run pytest -s tests/test_rhino_integration.py"""
from pathlib import Path

from run_in_rhino import start_server


RHINO_TESTS = Path(__file__).with_name("rhino")


def test_parent_move_integration():
    with start_server() as watcher:
        try:
            watcher.run_file(RHINO_TESTS / "setup_coincident_pair.py")
            watcher.run_file(RHINO_TESTS / "test_parent_move.py")
            results = watcher.take_data(timeout=10)
            assert len(results) == 1, "Unexpected Rhino test data: {}".format(results)
            result = results[0]
            assert result["name"] == "parent_move_translates_child"
            assert result["child_vertices"] == result["expected_child_vertices"]
            print("PASS master_parent_move_verification")
        finally:
            watcher.run_file(RHINO_TESTS / "cleanup.py")


if __name__ == "__main__":
    test_parent_move_integration()
