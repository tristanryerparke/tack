from pathlib import Path

from rhino_flow import run_flow


RHINO_TESTS = Path(__file__).with_name("rhino")


def test_four_command_event_trace(rhino_instance):
    results = run_flow(
        [
            ("script_now", RHINO_TESTS / "event_trace_setup.py"),
            ("script_now", RHINO_TESTS / "event_trace_move_parent.py"),
            ("command", "_Move 0,0,0 0,10,0"),
            ("script", RHINO_TESTS / "event_trace_collect.py"),
            ("script_now", RHINO_TESTS / "event_trace_undo_move.py"),
            ("command", "_Undo _Enter"),
            ("script", RHINO_TESTS / "event_trace_collect.py"),
            ("script_now", RHINO_TESTS / "event_trace_move_face.py"),
            ("command", "_MoveFace 0,0,0 2,0,0"),
            ("script", RHINO_TESTS / "event_trace_collect.py"),
            ("script_now", RHINO_TESTS / "event_trace_boolean_difference.py"),
            (
                "command",
                "_BooleanDifference _SelID {parent_id} _Enter "
                "_SelID {cutter_id} _Enter",
            ),
            ("script", RHINO_TESTS / "event_trace_collect.py"),
            ("script", RHINO_TESTS / "event_trace_finish.py"),
        ],
        rhino_instance,
        environment={"debug": "true"},
    )
    result = results[-1]
    assert result["name"] == "four_command_event_trace"
    assert [scenario["name"] for scenario in result["scenarios"]] == [
        "move_parent", "undo_move", "move_parent_face", "boolean_difference_parent",
    ]
