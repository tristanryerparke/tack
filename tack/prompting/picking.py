import Rhino
import rhinoscriptsyntax as rs

from tack import utils
from tack.prompting import command_menu
from tack.prompting.vertex_pick_conduit import VertexPickConduit


def pick_link(doc):
    parent_id = _pick_brep("Select parent polysurface")
    if not parent_id:
        return None
    parent = doc.Objects.Find(parent_id)
    if parent is None:
        return None

    parent_vertex = _pick_vertex(parent, "Pick a vertex on the parent polysurface")
    if parent_vertex is None:
        return None

    child_id = _pick_child(parent_id)
    if child_id is None:
        return None
    child = doc.Objects.Find(child_id)
    if child is None:
        return None

    coincident_vertices = utils.coincident_vertices(
        parent, child, max(doc.ModelAbsoluteTolerance, 1e-7)
    )
    if coincident_vertices:
        mode = _pick_child_vertex_mode(doc, child_id)
        if mode is None:
            return None
        if mode == "Coincident":
            child_vertex = _find_coincident_vertex(parent_vertex, coincident_vertices)
        else:
            child_vertex = _pick_vertex(
                child, "Pick a vertex on the child polysurface"
            )
    else:
        child_vertex = _pick_vertex(child, "Pick a vertex on the child polysurface")
    if child_vertex is None:
        return None

    return (
        parent_id,
        child_id,
        parent_vertex[0],
        parent_vertex[1],
        child_vertex[0],
        child_vertex[1],
        parent_vertex[2],
        child_vertex[2],
    )


def _pick_brep(prompt):
    return rs.GetObject(
        prompt,
        filter=rs.filter.polysurface,
        preselect=False,
        select=False,
    )


def _pick_child_vertex_mode(doc, child_id):
    locked_ids = _lock_other_objects(doc, child_id)
    try:
        return command_menu.pick_child_vertex_mode()
    finally:
        _unlock_objects(locked_ids)
        doc.Views.Redraw()


def _pick_child(parent_id):
    parent_was_locked = rs.IsObjectLocked(parent_id)
    if not parent_was_locked:
        rs.LockObject(parent_id)
    try:
        child_id = _pick_brep("Select child polysurface")
    finally:
        if not parent_was_locked:
            rs.UnlockObject(parent_id)

    if not child_id or utils.same_id(child_id, parent_id):
        print("Select a different child object.")
        return None
    return child_id


def _lock_other_objects(doc, target_id):
    locked_ids = []
    for candidate in doc.Objects:
        if candidate is None or utils.same_id(candidate.Id, target_id):
            continue
        try:
            if not rs.IsObjectLocked(candidate.Id) and rs.LockObject(candidate.Id):
                locked_ids.append(candidate.Id)
        except Exception:
            pass
    return locked_ids


def _unlock_objects(object_ids):
    for object_id in object_ids:
        try:
            rs.UnlockObject(object_id)
        except Exception:
            pass


class VertexGetPoint(Rhino.Input.Custom.GetPoint):
    def __init__(self, points, state):
        super(VertexGetPoint, self).__init__()
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
        super(VertexGetPoint, self).OnMouseMove(event)

    def OnMouseDown(self, event):
        if event.RightButtonDown:
            super(VertexGetPoint, self).OnMouseDown(event)
            return
        if not event.LeftButtonDown:
            return

        index = self._hit_test(event)
        if index is None:
            self.state["reject_mouse_up"] = True
            return

        self.state["result"] = index
        super(VertexGetPoint, self).OnMouseDown(event)

    def OnMouseUp(self, event):
        if self.state["reject_mouse_up"]:
            self.state["reject_mouse_up"] = False
            return
        super(VertexGetPoint, self).OnMouseUp(event)


def _pick_vertex(obj, prompt):
    points = utils.vertices_as_points(obj)
    if not points:
        print("The selected polysurface has no vertices.")
        return None

    state = {"hover": -1, "result": None, "reject_mouse_up": False}
    conduit = VertexPickConduit(points, state)
    doc = Rhino.RhinoDoc.ActiveDoc
    locked_ids = _lock_other_objects(doc, obj.Id)
    conduit.Enabled = True
    doc.Views.Redraw()

    try:
        while True:
            state["hover"] = -1
            state["result"] = None
            state["reject_mouse_up"] = False
            picker = VertexGetPoint(points, state)
            picker.SetCommandPrompt(prompt)
            picker.AcceptNothing(False)
            picker.AddConstructionPoints(points)
            picker.AddSnapPoints(points)
            picker.FullFrameRedrawDuringGet = True

            result = picker.Get()
            if result != Rhino.Input.GetResult.Point:
                return None
            index = state["result"]
            if index is None and state["hover"] >= 0:
                index = state["hover"]
            if index is not None:
                return "BrepVertex", index, points[index]
            # A point result without an accepted parent vertex must not
            # advance the setup command.
    finally:
        conduit.Enabled = False
        _unlock_objects(locked_ids)
        doc.Views.Redraw()


def _find_coincident_vertex(parent_vertex, coincident_vertices):
    matches = [
        match
        for match in coincident_vertices
        if match[1] == parent_vertex[1]
    ]
    if not matches:
        print("The selected parent vertex has no coincident child vertex.")
        return None
    if len(matches) > 1:
        print("The selected parent vertex has multiple coincident child vertices.")
        return None

    _, _, child_vertex_type, child_vertex_index, _, child_point = matches[0]
    return child_vertex_type, child_vertex_index, child_point
