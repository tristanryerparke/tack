import Rhino
import rhinoscriptsyntax as rs

import tack.analysis.bbox as bbox_analysis
from tack.prompting.anchor_pick_conduit import AnchorPickConduit


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


class AnchorGetPoint(Rhino.Input.Custom.GetPoint):
    def __init__(self, points, state):
        super(AnchorGetPoint, self).__init__()
        self.points = points
        self.state = state

    def _hit_test(self, event):
        picker = Rhino.Input.Custom.PickContext()
        picker.View = event.Viewport.ParentView
        picker.PickStyle = Rhino.Input.Custom.PickStyle.PointPick
        picker.SetPickTransform(
            event.Viewport.GetPickTransform(event.WindowPoint)
        )

        best = None
        try:
            for index, point in enumerate(self.points):
                hit, depth, distance = picker.PickFrustumTest(point)
                if not hit:
                    continue
                candidate = (distance, -depth, index)
                if best is None or candidate < best:
                    best = candidate
        finally:
            picker.Dispose()

        return None if best is None else best[2]

    def OnMouseMove(self, event):
        self.state["hover"] = self._hit_test(event)
        if self.state["hover"] is None:
            self.state["hover"] = -1
        Rhino.RhinoDoc.ActiveDoc.Views.Redraw()
        super(AnchorGetPoint, self).OnMouseMove(event)

    def OnMouseDown(self, event):
        if event.RightButtonDown:
            super(AnchorGetPoint, self).OnMouseDown(event)
            return
        if not event.LeftButtonDown:
            return

        index = self._hit_test(event)
        if index is None:
            self.state["reject_mouse_up"] = True
            return

        self.state["result"] = index
        super(AnchorGetPoint, self).OnMouseDown(event)

    def OnMouseUp(self, event):
        if self.state["reject_mouse_up"]:
            self.state["reject_mouse_up"] = False
            return
        super(AnchorGetPoint, self).OnMouseUp(event)


def pick_anchor(obj, anchor_type, candidate_anchors, wire_segments, prompt):
    if not candidate_anchors:
        print("The selected object has no usable anchors.")
        return None

    points = [point for _, point in candidate_anchors]
    state = {"hover": -1, "result": None, "reject_mouse_up": False}
    conduit = AnchorPickConduit(points, state, wire_segments)
    doc = Rhino.RhinoDoc.ActiveDoc
    locked_ids = lock_other_objects(doc, obj.Id)
    conduit.Enabled = True
    doc.Views.Redraw()

    try:
        while True:
            state["hover"] = -1
            state["result"] = None
            state["reject_mouse_up"] = False
            picker = AnchorGetPoint(points, state)
            picker.SetCommandPrompt(prompt)
            picker.AcceptNothing(False)
            picker.AddConstructionPoints(points)
            picker.AddSnapPoints(points)
            picker.FullFrameRedrawDuringGet = True

            result = picker.Get()
            if result != Rhino.Input.GetResult.Point:
                return None
            position = state["result"]
            if position is None and state["hover"] >= 0:
                position = state["hover"]
            if position is not None:
                anchor_index, point = candidate_anchors[position]
                return anchor_type, anchor_index, point
    finally:
        conduit.Enabled = False
        unlock_objects(locked_ids)
        doc.Views.Redraw()
