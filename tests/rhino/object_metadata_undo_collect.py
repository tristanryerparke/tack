"""Verify native Undo restored object-owned Tack metadata and runtime state."""

import sys
import types

import scriptcontext as sc

sys.modules.pop("common", None)
from common import run_flow_step

STICKY_KEY = "Tack.ObjectMetadataUndo"


def collect_object_metadata_undo():
    from tack import plane_link
    from tack import plane_link_metadata

    doc = sc.doc
    link_id = sc.sticky[STICKY_KEY]["link_id"]
    plane_link.subscribe()
    plane_link.EndCommandHandler(
        None,
        types.SimpleNamespace(CommandEnglishName="Undo"),
    )
    link = plane_link_metadata.read_link(doc, link_id)
    assert link is not None
    runtime = plane_link.states(doc, create=False)
    assert link_id in runtime
    return {"link_id": link_id, "restored": True, "runtime": len(runtime)}


run_flow_step("object_metadata_undo_collect", collect_object_metadata_undo)
