"""Verify native Undo restored object-owned Tack metadata and runtime state."""

import sys
import types

import scriptcontext as sc

sys.modules.pop("common", None)
from common import run_flow_step

STICKY_KEY = "Tack.ObjectMetadataUndo"


def collect_object_metadata_undo():
    from tack.links import lifecycle, repository, state

    doc = sc.doc
    link_id = sc.sticky[STICKY_KEY]["link_id"]
    lifecycle.subscribe()
    lifecycle.end_command_handler(
        None,
        types.SimpleNamespace(CommandEnglishName="Undo"),
    )
    link = repository.read_link(doc, link_id)
    assert link is not None
    runtime_states = state.states(doc, create=False)
    assert link_id in runtime_states
    return {"link_id": link_id, "restored": True, "runtime": len(runtime_states)}


run_flow_step("object_metadata_undo_collect", collect_object_metadata_undo)
