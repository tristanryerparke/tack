"""Automated Rhino coverage for Tack's analytic-plane model."""

import json
from pathlib import Path

import pytest

RHINO_DIR = Path(__file__).with_name("rhino")
FIXTURES = Path(__file__).with_name("fixtures")


def _run_script(rhino_instance, name, environment=None):
    from run_in_rhino.orchestration import run_rhino_python_til_done
    from run_in_rhino.server import RunContext

    reason, data = run_rhino_python_til_done(
        script_path=RHINO_DIR / name,
        context=RunContext(env=environment or {}),
        pipe_path=rhino_instance.pipe_path,
    )
    assert reason == "done"
    assert len(data) == 1
    return json.loads(data[0])


@pytest.mark.rhino
def test_blank_document_behaviors(rhino_instance):
    result = _run_script(rhino_instance, "blank_document.py")

    anchor = result["anchor_definitions"]
    assert anchor["candidate_counts"]
    assert all(count > 0 for count in anchor["candidate_counts"].values())
    assert result["duplicate_link"] == {
        "link_count": 1,
        "replacement_allows_child_movement": True,
    }
    assert result["metadata_index"] == {
        "link_count": 2,
        "index_entries": 2,
    }
    lifecycle = result["relationship_lifecycle"]
    assert lifecycle["link_id"]
    assert lifecycle["child_after_parent_move"] == lifecycle["child_after_correction"]


@pytest.mark.rhino
def test_object_metadata_restores_removed_tack_with_native_undo(
    rhino_instance,
):
    from rhino_flow import run_flow

    setup, restored = run_flow(
        [
            ("script", RHINO_DIR / "object_metadata_undo_setup.py"),
            ("command", "_Undo _Enter"),
            ("script", RHINO_DIR / "object_metadata_undo_collect.py"),
        ],
        rhino_instance,
    )

    assert setup["removed"]
    assert restored == {
        "name": "object_metadata_undo_collect",
        "link_id": setup["link_id"],
        "restored": True,
        "runtime": 1,
    }


@pytest.mark.rhino
def test_undo_and_redo_restore_analytic_plane_relationship(
    _rhino_instance_for_document,
):
    rhino_instance = _rhino_instance_for_document(
        FIXTURES / "analytic_plane_restore.3dm"
    )
    from rhino_flow import run_flow

    setup, after_move, after_undo, after_redo = run_flow(
        [
            ("script", RHINO_DIR / "undo_flow_setup.py"),
            ("command", "_Move 0,0,0 7,-3,0 _Enter"),
            ("script", RHINO_DIR / "undo_flow_collect.py"),
            ("command", "_Undo _Enter"),
            ("script", RHINO_DIR / "undo_flow_collect.py"),
            ("command", "_Redo _Enter"),
            ("script", RHINO_DIR / "undo_flow_collect.py"),
        ],
        rhino_instance,
    )

    assert setup["name"] == "undo_flow_setup"
    assert after_move["parent"] == after_move["child"]
    assert after_undo["parent"] == setup["parent_before"]
    assert after_undo["child"] == setup["child_before"]
    assert after_redo == after_move


@pytest.mark.rhino
def test_saved_analytic_links_restore_after_reopen(
    _rhino_instance_for_document,
):
    reopened = _rhino_instance_for_document(FIXTURES / "analytic_plane_restore.3dm")
    restored = _run_script(reopened, "verify_restore.py")
    assert restored["name"] == "verify_restore"
    assert restored["link_id"]
    assert restored["restored_count"] == 1


@pytest.mark.rhino
def test_nested_parent_chain_settles_in_one_command(
    _rhino_instance_for_document,
):
    rhino_instance = _rhino_instance_for_document(
        FIXTURES / "nested_analytic_planes.3dm"
    )
    result = _run_script(rhino_instance, "nested_relationship.py")

    assert result["name"] == "nested_relationship"
    assert result["middle"] == result["child"]


@pytest.mark.rhino
def test_deleting_tacked_object_removes_and_undo_reinstates(
    _rhino_instance_for_document,
):
    rhino_instance = _rhino_instance_for_document(
        FIXTURES / "nested_analytic_planes.3dm"
    )
    from rhino_flow import run_flow

    results = run_flow(
        [
            ("script", RHINO_DIR / "delete_cascade_setup.py"),
            ("command", "_Delete _Enter"),
            ("script", RHINO_DIR / "delete_cascade_check.py"),
            ("command", "_Undo _Enter"),
            ("script", RHINO_DIR / "delete_cascade_final.py"),
            ("command", "_Delete _Enter"),
            ("script", RHINO_DIR / "delete_cascade_check.py"),
            ("command", "_Undo _Enter"),
            ("script", RHINO_DIR / "delete_cascade_final.py"),
        ],
        rhino_instance,
    )

    setup, delete_child, final_child, delete_parent, final_parent = results

    assert setup["link_id"]
    assert delete_child["victim"] == "child"
    assert not delete_child["link_present"]
    assert final_child["link_present"]
    assert final_child["runtime"] == 1
    assert delete_parent["victim"] == "parent"
    assert not delete_parent["link_present"]
    assert final_parent["link_present"]
    assert final_parent["runtime"] == 1


@pytest.mark.rhino
def test_splitting_either_tack_endpoint_requests_invalid_warning(
    _rhino_instance_for_document,
):
    rhino_instance = _rhino_instance_for_document(FIXTURES / "split_tack_warning.3dm")
    from rhino_flow import run_flow

    results = run_flow(
        [
            ("script", RHINO_DIR / "split_warning_setup.py"),
            ("command", "_Split _SelID {cutter_id} _Enter _Enter"),
            ("script", RHINO_DIR / "split_warning_collect.py"),
            ("command", "_Undo _Enter"),
            ("script", RHINO_DIR / "split_warning_setup.py"),
            ("command", "_Split _SelID {cutter_id} _Enter _Enter"),
            ("script", RHINO_DIR / "split_warning_collect.py"),
        ],
        rhino_instance,
    )

    parent_setup, parent_result, child_setup, child_result = results
    assert parent_setup["role"] == "parent"
    assert child_setup["role"] == "child"
    expected = {
        "warning_count": 1,
        "endpoint_present": False,
        "link_present": False,
        "runtime_count": 0,
    }
    assert {key: parent_result[key] for key in expected} == expected
    assert {key: child_result[key] for key in expected} == expected


@pytest.mark.rhino
def test_one_hundred_holes_drive_one_hundred_centered_cylinders(
    _rhino_instance_for_document,
):
    rhino_instance = _rhino_instance_for_document(FIXTURES / "perforated_100_holes.3dm")
    result = _run_script(rhino_instance, "stress_100_holes.py")

    assert result["name"] == "stress_100_holes"
    assert result["relationship_count"] == 100
    assert result["moved_child_count"] == 100
