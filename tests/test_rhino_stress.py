"""Run with: uv run --with pytest pytest -s tests/test_rhino_stress.py"""
from pathlib import Path

from run_in_rhino import start_server


RHINO_STRESS_TEST = Path(__file__).with_name("rhino") / "stress_100_relationships.py"


def test_100_tack_relationships_update_200_objects():
    with start_server(environment={"debug": "true"}) as watcher:
        watcher.run_file(RHINO_STRESS_TEST)
        results = watcher.take_data(timeout=120)

    assert len(results) == 1, "Unexpected stress-test data: {}".format(results)
    result = results[0]
    assert result["name"] == "stress_100_relationships_200_objects"
    assert result["relationship_count"] == 100
    assert result["object_count"] == 200
    assert result["updated_child_count"] == 100
    assert result["update_seconds"] > 0
    assert result["milliseconds_per_relationship"] > 0
    print(
        "PASS 100 relationships / 200 objects: "
        "{:.3f}s total, {:.3f}ms per relationship; setup {:.3f}s".format(
            result["update_seconds"],
            result["milliseconds_per_relationship"],
            result["setup_seconds"],
        )
    )
