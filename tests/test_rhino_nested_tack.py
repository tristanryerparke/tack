"""Run with: uv run pytest -s tests/test_rhino_nested_tack.py"""
from pathlib import Path

from run_in_rhino import start_server


SCRIPT = Path(__file__).with_name("rhino") / "nested_tack.py"


def test_nested_tack_cascades_in_one_command():
    with start_server(environment={"debug": "true"}) as watcher:
        watcher.run_file(SCRIPT)
        results = watcher.take_data(timeout=30)

    assert results == [
        {
            "name": "nested_tack_cascades_in_one_command",
            "centers": [[5.0, 7.0, 0.0], [15.0, 7.0, 0.0], [25.0, 7.0, 0.0]],
        }
    ]
