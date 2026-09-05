"""Assert the object and its Tack are fully reinstated after undo."""

import sys
import types

import scriptcontext as sc

sys.modules.pop("common", None)
from common import run_flow_step

STICKY_KEY = "Tack.DeleteCascade"


def final_delete_cascade():
    from tack import plane_link
    from tack import plane_link_metadata
    from tack import utils

    doc = sc.doc
    info = sc.sticky[STICKY_KEY]
    plane_link.subscribe()
    plane_link.EndCommandHandler(
        None,
        types.SimpleNamespace(CommandEnglishName="Undo"),
    )
    assert (
        plane_link_metadata.read_link(doc, info["link_id"]) is not None
    ), "Undo did not reinstate the Tack"
    assert utils.find_object(doc, info["parent_id"]) is not None, "No parent"
    assert utils.find_object(doc, info["child_id"]) is not None, "No child"
    runtime = len(plane_link.states(doc, create=False))
    assert runtime == 1, "Runtime Tack not restored: {}".format(runtime)
    return {"link_present": True, "parent": True, "child": True, "runtime": runtime}


run_flow_step("delete_cascade_final", final_delete_cascade)
