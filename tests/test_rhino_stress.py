"""Run with: uv run --with pytest pytest -s tests/test_rhino_stress.py"""
from pathlib import Path

from run_in_rhino.orchestration import run_rhino_python_til_done
from run_in_rhino.server import RunContext


RHINO_STRESS_TEST = Path(__file__).with_name("rhino") / "stress_100_relationships.py"


def test_100_tack_relationships_update_200_objects(rhino_instance):
    reason, results = run_rhino_python_til_done(
        script_path=RHINO_STRESS_TEST,
        context=RunContext(env={"debug": "true"}),
        pipe_path=rhino_instance.pipe_path,
    )
    assert reason == "done"

    assert len(results) == 1, "Unexpected stress-test data: {}".format(results)
    result = results[0]
    assert result["name"] == "stress_100_relationships_200_objects"
    assert result["relationship_count"] == 100
    assert result["object_count"] == 200
    assert result["updated_child_count"] == 100
    assert result["update_seconds"] > 0
    assert result["milliseconds_per_relationship"] > 0
    assert result["ten_redraw_seconds"] > 0
    assert result["milliseconds_per_redraw"] > 0
    print(
        "PASS 100 relationships / 200 objects: "
        "{:.3f}s total, {:.3f}ms per relationship; setup {:.3f}s; "
        "cached redraw {:.3f}ms".format(
            result["update_seconds"],
            result["milliseconds_per_relationship"],
            result["setup_seconds"],
            result["milliseconds_per_redraw"],
        )
    )
