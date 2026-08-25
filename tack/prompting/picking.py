import Rhino
import rhinoscriptsyntax as rs

import tack.analysis.bbox as bbox_analysis
import tack.analysis.smart as smart_analysis
from tack import utils
from tack.prompting.bbox_center_conduit import BoundingBoxCenterConduit


def pick_object(doc, prompt):
    while True:
        object_id = rs.GetObject(
            prompt,
            filter=rs.filter.allobjects,
            preselect=False,
            select=False,
        )
        if not object_id:
            return None
        obj = doc.Objects.Find(object_id)
        if obj is not None and bbox_analysis.anchors(obj):
            return object_id
        print("Select an object with a valid bounding box.")


def lock_other_objects(doc, target_id):
    locked_ids = []
    for candidate in doc.Objects:
        if candidate is None or str(candidate.Id).lower() == str(target_id).lower():
            continue
        try:
            if not rs.IsObjectLocked(candidate.Id) and rs.LockObject(candidate.Id):
                locked_ids.append(candidate.Id)
        except Exception:
            pass
    return locked_ids


def unlock_objects(object_ids):
    for object_id in object_ids:
        try:
            rs.UnlockObject(object_id)
        except Exception:
            pass


def _debug_anchor(role, anchor):
    utils.debug(
        "[Tack pick] role={} kind={} index={}".format(
            role,
            anchor[1][0],
            anchor[1][1],
        )
    )


def pick_smart_anchor(obj, role):
    bbox_anchor = smart_analysis.bounding_box_center_anchor(obj)
    if bbox_anchor is None:
        print("The selected object has no usable bounding box center.")
        return None

    _, _, bbox_center = bbox_anchor
    doc = Rhino.RhinoDoc.ActiveDoc
    tolerance = max(doc.ModelAbsoluteTolerance, 1e-7)
    conduit = BoundingBoxCenterConduit(bbox_center)
    osnap_was_enabled = Rhino.ApplicationSettings.ModelAidSettings.Osnap
    project_was_enabled = (
        Rhino.ApplicationSettings.ModelAidSettings.ProjectSnapToCPlane
    )
    Rhino.ApplicationSettings.ModelAidSettings.Osnap = True
    Rhino.ApplicationSettings.ModelAidSettings.ProjectSnapToCPlane = False
    conduit.Enabled = True
    doc.Views.Redraw()

    try:
        while True:
            picker = Rhino.Input.Custom.GetPoint()
            picker.SetCommandPrompt(
                "Pick a Tack point on the {}".format(role)
            )
            picker.PermitObjectSnap(True)
            picker.AddConstructionPoint(bbox_center)
            picker.AddSnapPoint(bbox_center)
            picker.FullFrameRedrawDuringGet = True

            if picker.Get() != Rhino.Input.GetResult.Point:
                return None

            point = picker.Point()
            if point.DistanceTo(bbox_center) <= tolerance:
                _debug_anchor(role, bbox_anchor)
                return bbox_anchor

            obj_ref = picker.PointOnObject()
            if obj_ref is None or str(obj_ref.ObjectId).lower() != str(obj.Id).lower():
                print(
                    "Pick an object snap or bounding box center on the {}.".format(
                        role
                    )
                )
                continue

            anchor = smart_analysis.derive(
                obj_ref,
                point,
                picker.OsnapEventType,
                tolerance,
            )
            if anchor is not None:
                _debug_anchor(role, anchor)
                return anchor
            print(
                "That snap cannot be consistently derived from the {}.".format(
                    role
                )
            )
    finally:
        conduit.Enabled = False
        Rhino.ApplicationSettings.ModelAidSettings.Osnap = osnap_was_enabled
        Rhino.ApplicationSettings.ModelAidSettings.ProjectSnapToCPlane = (
            project_was_enabled
        )
        doc.Views.Redraw()
