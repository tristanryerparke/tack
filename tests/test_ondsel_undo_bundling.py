from pathlib import Path

from rhino_flow import run_flow


RHINO_TESTS = Path(__file__).with_name("rhino")

TOLERANCE = 1e-2


def _close(actual, expected):
    return (
        actual is not None
        and abs(actual[0] - expected[0]) <= TOLERANCE
        and abs(actual[1] - expected[1]) <= TOLERANCE
        and abs(actual[2] - expected[2]) <= TOLERANCE
    )


def test_child_correction_is_bundled_into_the_move_undo(rhino_instance):
    results = run_flow(
        [
            ("script", RHINO_TESTS / "ondsel_undo_setup.py"),
            ("command", "_Move 0,0,0 5,0,0"),
            ("script", RHINO_TESTS / "ondsel_undo_after_move.py"),
            ("command", "_Undo _Enter"),
            ("script", RHINO_TESTS / "ondsel_undo_after_undo.py"),
        ],
        rhino_instance,
    )
    setup, after_move, after_undo = results

    # 1. The solve must have run inside the Move command's EndCommand:
    #    the child (dragged away by the user) is already snapped back to
    #    its settled pose BEFORE any pump.
    assert _close(
        after_move["child_center_before_pump"],
        after_move["original_child"],
    ), (
        "Child was not solved inside the Move command; "
        "solve did not run inside EndCommand"
    )

    # 2. The anchored base must never move.
    assert _close(
        after_move["base_center_after_move"],
        after_move["original_base"],
    ), "Anchored base moved during the child drag"

    # 3. A single Undo must restore BOTH objects to the pre-move state.
    assert _close(
        after_undo["base_center_after_undo"],
        after_undo["original_base"],
    ), "Single undo did not restore the base"
    assert _close(
        after_undo["child_center_after_undo"],
        after_undo["original_child"],
    ), (
        "Single undo did not restore the child; "
        "the solve is not bundled into the Move undo record"
    )
