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
def test_analytic_anchor_definitions_resolve_directly(rhino_instance):
    result = _run_script(rhino_instance, "anchor_definitions.py")

    assert result["name"] == "anchor_definitions"
    assert all(count > 0 for count in result["candidate_counts"].values())


@pytest.mark.rhino
def test_document_index_preserves_complete_links_without_object_scan(rhino_instance):
    result = _run_script(rhino_instance, "metadata_index.py")

    assert result == {
        "name": "metadata_index",
        "link_count": 2,
        "index_entries": 2,
    }


@pytest.mark.rhino
def test_new_tack_replaces_existing_tack_between_the_same_objects(rhino_instance):
    result = _run_script(rhino_instance, "duplicate_link.py")

    assert result == {
        "name": "duplicate_link",
        "link_count": 1,
        "replacement_inverted": True,
    }


@pytest.mark.rhino
def test_parent_move_maintains_child_and_deleted_child_breaks_link(rhino_instance):
    result = _run_script(rhino_instance, "relationship_lifecycle.py")

    assert result["name"] == "relationship_lifecycle"
    assert result["link_id"]
    assert result["child_after_parent_move"] == result["child_after_correction"]


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
def test_saved_analytic_links_restore_after_reopen(
    _rhino_instance_for_document,
):
    reopened = _rhino_instance_for_document(
        FIXTURES / "analytic_plane_restore.3dm"
    )
    restored = _run_script(reopened, "verify_restore.py")
    assert restored["name"] == "verify_restore"
    assert restored["link_id"]
    assert restored["restored_count"] == 1


@pytest.mark.rhino
def test_one_hundred_holes_drive_one_hundred_centered_cylinders(
    _rhino_instance_for_document,
):
    rhino_instance = _rhino_instance_for_document(
        FIXTURES / "perforated_100_holes.3dm"
    )
    result = _run_script(rhino_instance, "stress_100_holes.py")

    assert result["name"] == "stress_100_holes"
    assert result["relationship_count"] == 100
    assert result["moved_child_count"] == 100
