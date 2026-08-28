"""Select an existing Rhino-document Brep or extrusion face with a hover highlight.

Run with:
    uv run rhino-watch demos/picking_brep_face.py --debug
"""

import Rhino
import System.Drawing
from Rhino.Commands import Result
from run_in_rhino.rhino_env.client import SocketConnection
from run_in_rhino.rhino_env.env import install_os_environment
from run_in_rhino.rhino_env.parasite import OutputParasite


HIGHLIGHT_COLOR = System.Drawing.Color.Black


class BrepFaceConduit(Rhino.Display.DisplayConduit):
    def __init__(self, candidates, state):
        super(BrepFaceConduit, self).__init__()
        self.candidates = candidates
        self.state = state

    def DrawOverlay(self, event):
        index = self.state["hover"]
        if index < 0:
            return

        for curve in self.candidates[index]["border_curves"]:
            event.Display.DrawCurve(curve, HIGHLIGHT_COLOR, 8)


class BrepFaceGetPoint(Rhino.Input.Custom.GetPoint):
    def __init__(self, candidates, state):
        super(BrepFaceGetPoint, self).__init__()
        self.candidates = candidates
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
            for index, candidate in enumerate(self.candidates):
                for mesh in candidate["meshes"]:
                    result = picker.PickFrustumTest(
                        mesh,
                        Rhino.Input.Custom.PickContext.MeshPickStyle.ShadedModePicking,
                    )
                    if not result[0]:
                        continue

                    # Both mesh overloads put depth and distance fourth and
                    # third from the end of their Python result tuples.
                    depth = result[-4]
                    distance = result[-3]
                    candidate_rank = (distance, -depth, index)
                    if best is None or candidate_rank < best:
                        best = candidate_rank
        finally:
            picker.Dispose()

        return None if best is None else best[2]

    def OnMouseMove(self, event):
        index = self._hit_test(event)
        self.state["hover"] = -1 if index is None else index
        Rhino.RhinoDoc.ActiveDoc.Views.Redraw()
        super(BrepFaceGetPoint, self).OnMouseMove(event)

    def OnMouseDown(self, event):
        if event.RightButtonDown:
            super(BrepFaceGetPoint, self).OnMouseDown(event)
            return
        if not event.LeftButtonDown:
            return

        index = self._hit_test(event)
        if index is None:
            self.state["reject_mouse_up"] = True
            return

        self.state["result"] = index
        super(BrepFaceGetPoint, self).OnMouseDown(event)

    def OnMouseUp(self, event):
        if self.state["reject_mouse_up"]:
            self.state["reject_mouse_up"] = False
            return
        super(BrepFaceGetPoint, self).OnMouseUp(event)


def _brep_from_rhino_object(rhino_object):
    geometry = rhino_object.Geometry
    if isinstance(geometry, Rhino.Geometry.Brep):
        return geometry
    if isinstance(geometry, Rhino.Geometry.Extrusion):
        # Split kinks so each visible planar side can be highlighted alone.
        return geometry.ToBrep(True)
    return None


def _component_index_for_face(geometry, face_index, face_count):
    if isinstance(geometry, Rhino.Geometry.Brep):
        return Rhino.Geometry.ComponentIndex(
            Rhino.Geometry.ComponentIndexType.BrepFace,
            face_index,
        )
    if not isinstance(geometry, Rhino.Geometry.Extrusion):
        return None

    cap_start = face_count - geometry.CapCount
    if face_index >= cap_start:
        cap_index = face_index - cap_start
        return Rhino.Geometry.ComponentIndex(
            Rhino.Geometry.ComponentIndexType.ExtrusionCapSurface,
            cap_index,
        )

    # A kinky profile becomes several Brep faces, but remains one native
    # extrusion wall surface. Keep the native component for final selection;
    # the split Brep face is used for the live hover highlight.
    if geometry.ProfileCount > 0:
        return Rhino.Geometry.ComponentIndex(
            Rhino.Geometry.ComponentIndexType.ExtrusionWallSurface,
            0,
        )
    return None


def _face_candidates(doc):
    candidates = []
    for rhino_object in doc.Objects:
        if (
            rhino_object is None
            or rhino_object.IsDeleted
            or rhino_object.IsHidden
            or rhino_object.IsLocked
        ):
            continue

        geometry = rhino_object.Geometry
        brep = _brep_from_rhino_object(rhino_object)
        if brep is None:
            continue

        for face in brep.Faces:
            component_index = _component_index_for_face(
                geometry,
                face.FaceIndex,
                brep.Faces.Count,
            )
            if component_index is None:
                continue

            face_brep = face.DuplicateFace(False)
            if face_brep is None:
                continue

            meshes = Rhino.Geometry.Mesh.CreateFromBrep(face_brep)
            if meshes is None:
                continue
            meshes = list(meshes)
            if not meshes:
                continue
            candidates.append(
                {
                    "object_id": rhino_object.Id,
                    "face_index": face.FaceIndex,
                    "component_index": component_index,
                    "face_brep": face_brep,
                    "border_curves": list(face_brep.DuplicateEdgeCurves()),
                    "meshes": meshes,
                }
            )
    return candidates


def _select_face(doc, candidate):
    rhino_object = doc.Objects.Find(candidate["object_id"])
    if rhino_object is None:
        return False

    selected = rhino_object.SelectSubObject(
        candidate["component_index"],
        True,
        True,
        True,
    )
    if selected > 0:
        doc.Views.Redraw()
    return selected > 0


def pick_brep_face(doc):
    candidates = _face_candidates(doc)
    if not candidates:
        print("No visible, unlocked Breps or extrusions are available to select.")
        return None

    state = {"hover": -1, "result": None, "reject_mouse_up": False}
    conduit = BrepFaceConduit(candidates, state)
    conduit.Enabled = True
    doc.Views.Redraw()

    picker = BrepFaceGetPoint(candidates, state)
    picker.SetCommandPrompt("Select a Brep or extrusion face")
    picker.AcceptNothing(False)
    picker.PermitObjectSnap(False)
    picker.FullFrameRedrawDuringGet = True
    try:
        if picker.Get() != Rhino.Input.GetResult.Point:
            return None

        index = state["result"]
        if index is None and state["hover"] >= 0:
            index = state["hover"]
        return None if index is None else candidates[index]
    finally:
        conduit.Enabled = False
        doc.Views.Redraw()


def RunCommand(is_interactive):
    doc = Rhino.RhinoDoc.ActiveDoc
    if doc is None:
        return Result.Cancel

    candidate = pick_brep_face(doc)
    if candidate is None:
        return Result.Cancel

    if not _select_face(doc, candidate):
        print("Could not select the picked Brep or extrusion face.")
        return Result.Failure

    print(
        "Picked Brep or extrusion face: object_id={} face_index={}".format(
            candidate["object_id"],
            candidate["face_index"],
        )
    )
    return Result.Success


if __name__ == "__main__":
    connection = SocketConnection()
    install_os_environment(connection)
    with OutputParasite(connection, done_msg=True):
        RunCommand(True)
