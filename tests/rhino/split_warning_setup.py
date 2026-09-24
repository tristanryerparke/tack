"""Prepare one fixture endpoint for a native Split warning check."""

import sys

import rhinoscriptsyntax as rs
import scriptcontext as sc

sys.modules.pop("common", None)
from common import run_flow_step

STICKY_KEY = "Tack.SplitWarning"
PARENT_ID = "6c5535cc-1388-403d-857f-7692d27a3c26"
CHILD_ID = "a8a6d29f-e49c-4997-96f0-4bf5a2dc0827"
PARENT_CIRCLE_CUTTER_ID = "a47d77c2-0273-4637-ade2-27b063f9a469"
CIRCLE_CUTTER_ID = "b6c49b60-6cb1-485a-aa9a-b5562d03920a"


def setup_split_warning():
    from tack.links import repository, runtime, solver, state

    doc = sc.doc
    role = sc.sticky.get(STICKY_KEY, {}).get("next_role", "parent")
    endpoint_id = PARENT_ID if role == "parent" else CHILD_ID
    cutter_id = PARENT_CIRCLE_CUTTER_ID if role == "parent" else CIRCLE_CUTTER_ID

    assert runtime.restore_document(doc) == 1, "Fixture Tack did not restore"
    links = repository.all_links(doc, include_invalid=True)
    assert len(links) == 1, "Expected one fixture Tack"

    warning = {"count": 0}

    def record_warning():
        warning["count"] += 1

    solver._show_invalid_alert = record_warning  # ty: ignore[invalid-assignment]
    sc.sticky[STICKY_KEY] = {
        "role": role,
        "next_role": "child",
        "endpoint_id": endpoint_id,
        "cutter_id": cutter_id,
        "link_id": links[0].link_id,
        "warning": warning,
    }

    rs.UnselectAllObjects()
    assert rs.SelectObject(endpoint_id), f"Could not select {role}"
    assert len(state.states(doc, create=False)) == 1, "Fixture Tack is not active"
    return {"role": role, "cutter_id": cutter_id}


run_flow_step("split_warning_setup", setup_split_warning)
