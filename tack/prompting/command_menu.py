import Rhino
import rhinoscriptsyntax as rs

import tack.analysis.bbox as bbox_analysis
import tack.analysis.polyline_vertex as polyline_vertex_analysis
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


def _vertex_analyzer(geometry):
    for analyzer in (vertex_analysis, polyline_vertex_analysis):
        if analyzer.supports_vertex_anchors(geometry):
            return analyzer
    return None


def _pick_anchor(obj, role):
    doc = Rhino.RhinoDoc.ActiveDoc
    locked_ids = picking.lock_other_objects(doc, obj.Id)
    try:
        analyzer = bbox_analysis
        vertex_analyzer = _vertex_analyzer(obj.Geometry)
        if vertex_analyzer is not None:
            anchor_type = _pick_anchor_type(role, vertex_analyzer.ANCHOR_TYPE)
            if anchor_type is None:
                return None
            if anchor_type == vertex_analyzer.ANCHOR_TYPE:
                analyzer = vertex_analyzer

        candidate_anchors = analyzer.anchors(obj)
        if analyzer is bbox_analysis:
            wire_segments = analyzer.wire_segments(obj)
            prompt = "Pick a bounding box anchor on the {}".format(role)
        else:
            wire_segments = []
            prompt = "Pick a vertex anchor on the {}".format(role)

        return picking.pick_anchor(
            obj,
            analyzer.ANCHOR_TYPE,
            candidate_anchors,
            wire_segments,
            prompt,
        )
    finally:
        picking.unlock_objects(locked_ids)
        doc.Views.Redraw()


def _pick_anchor_type(role, vertex_anchor_type):
    picker = Rhino.Input.Custom.GetOption()
    picker.SetCommandPrompt(
        "Choose a reference point type on the {}".format(role)
    )
    picker.AddOption("BoundingBox")
    picker.AddOption("Vertex")
    if picker.Get() != Rhino.Input.GetResult.Option:
        return None
    if picker.Option().EnglishName == "Vertex":
        return vertex_anchor_type
    return bbox_analysis.ANCHOR_TYPE
