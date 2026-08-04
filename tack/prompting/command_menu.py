import Rhino
import rhinoscriptsyntax as rs

import tack.analysis.bbox as bbox_analysis
import tack.analysis.vertex as vertex_analysis
from tack import utils
from tack.prompting import picking


DISABLE_NORMAL_OSNAPS = True


def pick_link(doc):
    if not DISABLE_NORMAL_OSNAPS:
        return _pick_link(doc)

    osnap_was_enabled = Rhino.ApplicationSettings.ModelAidSettings.Osnap
    Rhino.ApplicationSettings.ModelAidSettings.Osnap = False
    try:
        return _pick_link(doc)
    finally:
        Rhino.ApplicationSettings.ModelAidSettings.Osnap = osnap_was_enabled


def _pick_link(doc):
    parent_id = picking.pick_object(doc, "Select parent object")
    if not parent_id:
        return None
    parent = doc.Objects.Find(parent_id)
    if parent is None:
        return None

    parent_anchor = _pick_anchor(parent, "parent")
    if parent_anchor is None:
        return None

    parent_was_locked = rs.IsObjectLocked(parent_id)
    if not parent_was_locked:
        rs.LockObject(parent_id)
    try:
        child_id = picking.pick_object(doc, "Select child object")
    finally:
        if not parent_was_locked:
            rs.UnlockObject(parent_id)

    if not child_id or utils.same_id(child_id, parent_id):
        print("Select a different child object.")
        return None
    child = doc.Objects.Find(child_id)
    if child is None:
        return None

    child_anchor = _pick_anchor(child, "child")
    if child_anchor is None:
        return None
    return parent_id, child_id, parent_anchor, child_anchor


def _supports_vertex_anchors(geometry):
    return vertex_analysis.supports_vertex_anchors(geometry)


def _pick_anchor(obj, role):
    geometry = obj.Geometry
    anchor_type = bbox_analysis.ANCHOR_TYPE
    if _supports_vertex_anchors(geometry):
        anchor_type = _pick_brep_anchor_type(role)
        if anchor_type is None:
            return None

    if anchor_type == vertex_analysis.ANCHOR_TYPE:
        candidate_anchors = vertex_analysis.anchors(obj)
        wire_segments = []
        prompt = "Pick a vertex anchor on the {}".format(role)
    else:
        candidate_anchors = bbox_analysis.anchors(obj)
        wire_segments = bbox_analysis.wire_segments(obj)
        prompt = "Pick a bounding box anchor on the {}".format(role)

    return picking.pick_anchor(
        obj,
        anchor_type,
        candidate_anchors,
        wire_segments,
        prompt,
    )


def _pick_brep_anchor_type(role):
    picker = Rhino.Input.Custom.GetOption()
    picker.SetCommandPrompt(
        "Choose a reference point type on the {}".format(role)
    )
    picker.AddOption("BoundingBox")
    picker.AddOption("Vertex")
    if picker.Get() != Rhino.Input.GetResult.Option:
        return None
    if picker.Option().EnglishName == "Vertex":
        return vertex_analysis.ANCHOR_TYPE
    return bbox_analysis.ANCHOR_TYPE
