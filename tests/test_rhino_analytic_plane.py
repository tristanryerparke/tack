"""Automated Rhino coverage for Tack's analytic-plane model."""

import json
from pathlib import Path

import pytest


RHINO_DIR = Path(__file__).with_name("rhino")


def _run_script(rhino_instance, name):
    from run_in_rhino.orchestration import run_rhino_python_til_done

    reason, data = run_rhino_python_til_done(
        script_path=RHINO_DIR / name,
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
def test_parent_move_maintains_child_and_deleted_child_breaks_link(rhino_instance):
    result = _run_script(rhino_instance, "relationship_lifecycle.py")

    assert result["name"] == "relationship_lifecycle"
    assert result["link_id"]
    assert result["child_after_parent_move"] == result["child_after_correction"]
