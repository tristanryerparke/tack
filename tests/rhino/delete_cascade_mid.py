"""Report state between native undo command steps and stage the next delete."""

import sys

import rhinoscriptsyntax as rs
import scriptcontext as sc

sys.modules.pop("common", None)
from common import run_flow_step

STICKY_KEY = "Tack.DeleteCascade"


def mid_delete_cascade():
    from tack.core import objects

    doc = sc.doc
    info = sc.sticky[STICKY_KEY]
    parent = objects.find_object(doc, info["parent_id"])
    if parent is not None:
        rs.UnselectAllObjects()
        rs.SelectObject(info["parent_id"])
    return {
        "link": _link_present(doc, info),
        "parent": parent is not None,
        "child": objects.find_object(doc, info["child_id"]) is not None,
    }


def _link_present(doc, info):
    from tack.links import repository

    return repository.read_link(doc, info["link_id"]) is not None


run_flow_step("delete_cascade_mid", mid_delete_cascade)
