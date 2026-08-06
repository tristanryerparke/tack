"""Run with: uv run --with pytest pytest -s tests/test_rhino_event_traces.py"""
from pathlib import Path

from run_in_rhino import start_server


RHINO_TESTS = Path(__file__).with_name("rhino")
SETUP = RHINO_TESTS / "event_trace_setup.py"
ARM_MOVE = RHINO_TESTS / "event_trace_move_parent.py"
ARM_UNDO = RHINO_TESTS / "event_trace_undo_move.py"
ARM_MOVE_FACE = RHINO_TESTS / "event_trace_move_face.py"
ARM_BOOLEAN_DIFFERENCE = RHINO_TESTS / "event_trace_boolean_difference.py"
COLLECT = RHINO_TESTS / "event_trace_collect.py"
FINISH = RHINO_TESTS / "event_trace_finish.py"


def _run_top_level_command(watcher, arm_script, command):
    watcher.run_file(arm_script)
    watcher.run_command(command)
    watcher.run_file(COLLECT)


def test_four_command_event_trace():
    with start_server(environment={"debug": "true"}) as watcher:
        watcher.run_file(SETUP)
        try:
            _run_top_level_command(
                watcher,
                ARM_MOVE,
                "_Move 0,0,0 0,10,0",
            )
            _run_top_level_command(watcher, ARM_UNDO, "_Undo")
            _run_top_level_command(
                watcher,
                ARM_MOVE_FACE,
                "_MoveFace 0,0,0 2,0,0",
            )
            _run_top_level_command(
                watcher,
                ARM_BOOLEAN_DIFFERENCE,
                "_BooleanDifference _Enter _SelLast _Enter",
            )
        finally:
            watcher.run_file(FINISH)
        results = watcher.take_data(timeout=120)

    assert len(results) == 1, "Unexpected event-trace data: {}".format(results)
    result = results[0]
    assert result["name"] == "four_command_event_trace"
    assert [scenario["name"] for scenario in result["scenarios"]] == [
        "move_parent",
        "undo_move",
        "move_parent_face",
        "boolean_difference_parent",
    ]
    for scenario in result["scenarios"]:
        assert scenario["command_result"], scenario
        maintenance_events = {
            entry["event"]
            for entry in scenario["entries"]
            if entry["kind"] == "maintain"
        }
        assert "ReplaceRhinoObject" not in maintenance_events, scenario
        assert "DeleteRhinoObject" not in maintenance_events, scenario
        print(
            "TRACE {}: events={} child_updates={} broken={}".format(
                scenario["name"],
                scenario["event_counts"],
                scenario["child_update_events"],
                scenario["broken_after"],
            )
        )

    scenarios = {scenario["name"]: scenario for scenario in result["scenarios"]}

    def _offset_preserved(scenario, expected=(20.0, 0.0, 0.0), tol=1e-6):
        parent = scenario["parent_center_after"]
        child = scenario["child_center_after"]
        if parent is None or child is None:
            return False
        return all(
            abs(child[i] - parent[i] - expected[i]) <= tol for i in range(3)
        )

    # Under the deferred solver, maintain runs on RhinoApp.Idle and re-solves
    # from current document state, so the contract is outcome-based: the
    # parent->child offset is preserved across move, undo, face-move, and the
    # boolean-difference no-op.
    for name in (
        "move_parent",
        "undo_move",
        "move_parent_face",
        "boolean_difference_parent",
    ):
        assert _offset_preserved(scenarios[name]), name

    # Moves drive exactly one tack child update on idle; undo re-solves to a
    # zero correction once the parent is restored, and the boolean command is a
    # no-op on the parent, so neither moves the child.
    assert len(scenarios["move_parent"]["child_update_events"]) == 1
    assert len(scenarios["move_parent_face"]["child_update_events"]) == 1
