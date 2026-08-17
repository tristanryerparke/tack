from pathlib import Path

from rhino_flow import run_flow


RHINO_TESTS = Path(__file__).with_name("rhino")

TOLERANCE = 1e-6
MOVE = (10.0, 0.0, 0.0)


def _moved(point, vector):
    return (point[0] + vector[0], point[1] + vector[1], point[2] + vector[2])


def _close(actual, expected):
    return (
        abs(actual[0] - expected[0]) <= TOLERANCE
        and abs(actual[1] - expected[1]) <= TOLERANCE
        and abs(actual[2] - expected[2]) <= TOLERANCE
    )


def test_child_correction_is_bundled_into_the_parent_move_undo(rhino_instance):
    results = run_flow(
        [
            ("script", RHINO_TESTS / "undo_bundling_setup.py"),
            ("command", "_Move 0,0,0 10,0,0"),
            ("script", RHINO_TESTS / "undo_bundling_after_move.py"),
            ("command", "_Undo _Enter"),
            ("script", RHINO_TESTS / "undo_bundling_after_undo.py"),
        ],
        rhino_instance,
    )
    setup, after_move, after_undo = results

    # 1. The solve must have run inside the Move command's EndCommand:
    #    the child is already corrected BEFORE any manual pump.
    assert after_move["child_center_before_pump"] is not None, (
        "Child was not corrected during the Move command; "
        "solve did not run inside EndCommand"
    )
    assert _close(
        after_move["child_center_before_pump"],
        _moved(after_move["original_child"], MOVE),
    ), "Child was not corrected during the Move command"
    assert _close(
        after_move["parent_center_after_move"],
        _moved(after_move["original_parent"], MOVE),
    ), "Parent did not move"

    # 2. A single Undo must restore BOTH parent and child: the Tack
    #    correction shares the Move command's undo record.
    assert not after_undo.get("missing_objects"), (
        "Objects went missing after undo"
    )
    assert _close(
        after_undo["parent_center_after_undo"],
        after_undo["original_parent"],
    ), "Single undo did not restore the parent"
    assert _close(
        after_undo["child_center_after_undo"],
        after_undo["original_child"],
    ), (
        "Single undo restored the parent but not the child; "
        "the Tack correction is not bundled into the Move undo record"
    )
