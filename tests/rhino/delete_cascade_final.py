"""Assert the object and its Tack are fully reinstated after undo."""

import sys
import types

import rhinoscriptsyntax as rs
import scriptcontext as sc

sys.modules.pop("common", None)
from common import run_flow_step

STICKY_KEY = "Tack.DeleteCascade"


def final_delete_cascade():
    from tack.core import objects
    from tack.links import (
        lifecycle,
        repository,
        runtime,
        state,
    )

    doc = sc.doc
    info = sc.sticky[STICKY_KEY]
    lifecycle.subscribe()
    lifecycle.end_command_handler(
        None,
        types.SimpleNamespace(CommandEnglishName="Undo"),
    )
    assert repository.read_link(doc, info["link_id"]) is not None, (
        "Undo did not reinstate the Tack"
    )
    assert objects.find_object(doc, info["parent_id"]) is not None, "No parent"
    assert objects.find_object(doc, info["child_id"]) is not None, "No child"
    runtime_count = len(state.states(doc, create=False))
    assert runtime_count == 1, "Runtime Tack not restored: {}".format(runtime_count)
    rs.UnselectAllObjects()
    assert rs.SelectObject(info["parent_id"])
    return {
        "link_present": True,
        "parent": True,
        "child": True,
        "runtime": runtime_count,
    }


run_flow_step("delete_cascade_final", final_delete_cascade)
