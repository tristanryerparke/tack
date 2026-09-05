"""Verify the native Delete pruned the Tack and select the next victim."""

import sys

import scriptcontext as sc
import rhinoscriptsyntax as rs

sys.modules.pop("common", None)
from common import run_flow_step

STICKY_KEY = "Tack.DeleteCascade"


def check_delete_cascade():
    from tack import plane_link
    from tack import plane_link_metadata
    from tack import utils

    doc = sc.doc
    info = sc.sticky[STICKY_KEY]
    plane_link.subscribe()
    parent = utils.find_object(doc, info["parent_id"]) is not None
    child = utils.find_object(doc, info["child_id"]) is not None
    victim = "child" if not child else ("parent" if not parent else None)
    assert victim, "No Tacked object was deleted"
    assert (
        plane_link_metadata.read_link(doc, info["link_id"]) is None
    ), "Tack survived {} deletion".format(victim)
    assert (
        not plane_link.states(doc, create=False)
    ), "Runtime Tack survived {} deletion".format(victim)

    if victim == "child" and parent:
        rs.UnselectAllObjects()
        assert rs.SelectObject(info["parent_id"]), "Could not select parent"
    return {"victim": victim, "link_present": False}


run_flow_step("delete_cascade_check", check_delete_cascade)
