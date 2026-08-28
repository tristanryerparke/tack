import math
import os
import sys

import Rhino
import System
import System.Drawing
import rhinoscriptsyntax as rs
import scriptcontext as sc

from ondsel.assembly import ondsel_module

TACK_ROOT = "/Users/tristanryerparke/projects-local/tack"
MODULES_DIR = os.path.join(TACK_ROOT, "ondsel", "rhino_modules")
if MODULES_DIR not in sys.path:
    sys.path.insert(0, MODULES_DIR)

BREP_EDGE_COMPONENT_TYPE = Rhino.Geometry.ComponentIndexType.BrepEdge
BREP_FACE_COMPONENT_TYPE = Rhino.Geometry.ComponentIndexType.BrepFace
BREP_TRIM_COMPONENT_TYPE = Rhino.Geometry.ComponentIndexType.BrepTrim


def load_ondsel_module():
    return ondsel_module.load()


def point_tuple(point):
    return (float(point.X), float(point.Y), float(point.Z))


def vector_tuple(vector):
    return (float(vector.X), float(vector.Y), float(vector.Z))


def _brep_from_rhino_object(rhino_object):
    if rhino_object is None:
        return None
    geometry = rhino_object.Geometry
    if isinstance(geometry, Rhino.Geometry.Brep):
        return geometry
    if hasattr(geometry, "ToBrep"):
        return geometry.ToBrep()
    return None


def _brep_edge_only_filter(rhino_object, geometry, component_index):
    component_type = component_index.ComponentIndexType
    if component_type == BREP_EDGE_COMPONENT_TYPE:
        return True
    if isinstance(geometry, Rhino.Geometry.BrepEdge):
        return True
    if component_type != BREP_TRIM_COMPONENT_TYPE:
        return False

    brep = _brep_from_rhino_object(rhino_object)
    trim_index = component_index.Index
    if brep is None or trim_index < 0 or trim_index >= brep.Trims.Count:
        return False

    trim = brep.Trims[trim_index]
    edge = trim.Edge
    if edge is None:
        return False

    trim_indices = list(edge.TrimIndices())
    return bool(trim_indices) and trim.TrimIndex == trim_indices[0]


def prompt_for_one_brep_edge(prompt):
    getter = Rhino.Input.Custom.GetObject()
    getter.SetCommandPrompt(prompt)
    getter.SetPressEnterWhenDonePrompt("Press Enter when done")
    getter.GeometryFilter = Rhino.DocObjects.ObjectType.EdgeFilter
    getter.SetCustomGeometryFilter(_brep_edge_only_filter)
    getter.SubObjectSelect = True
    getter.ChooseOneQuestion = False
    getter.AlreadySelectedObjectSelect = True
    getter.EnablePreSelect(True, True)
    getter.EnablePostSelect(True)

    result = getter.GetMultiple(1, 0)
    if result != Rhino.Input.GetResult.Object:
        return None

    edge_data = []
    seen = set()
    for index in range(getter.ObjectCount):
        obj_ref = getter.Object(index)
        edge = obj_ref.Edge()
        brep = obj_ref.Brep()
        rhino_object = obj_ref.Object()
        if edge is None or brep is None or rhino_object is None:
            continue
        key = (obj_ref.ObjectId, edge.EdgeIndex)
        if key in seen:
            continue
        seen.add(key)
        edge_data.append(
            {
                "object_id": obj_ref.ObjectId,
                "edge_index": edge.EdgeIndex,
                "edge": edge,
                "brep": brep,
                "object": rhino_object,
            }
        )

    if len(edge_data) != 1:
        print("Select exactly one Brep edge; got {}.".format(len(edge_data)))
        return None
    return edge_data[0]


def _brep_face_only_filter(_rhino_object, geometry, component_index):
    return (
        component_index.ComponentIndexType == BREP_FACE_COMPONENT_TYPE
        or isinstance(geometry, Rhino.Geometry.BrepFace)
    )


class _PlanarFaceConduit(Rhino.Display.DisplayConduit):
    def __init__(self, candidates, state):
        super(_PlanarFaceConduit, self).__init__()
        self.candidates = candidates
        self.state = state
        self.material = Rhino.Display.DisplayMaterial(
            System.Drawing.Color.FromArgb(255, 255, 215, 0)
        )
        self.material.Transparency = 0.45

    def DrawForeground(self, event):
        index = self.state["hover"]
        if index < 0:
            return
        face_brep = self.candidates[index]["face_brep"]
        event.Display.DrawBrepShaded(face_brep, self.material)
        event.Display.DrawBrepWires(face_brep, System.Drawing.Color.Black, 6)


class _PlanarFaceGetPoint(Rhino.Input.Custom.GetPoint):
    def __init__(self, candidates, state):
        super(_PlanarFaceGetPoint, self).__init__()
        self.candidates = candidates
        self.state = state

    def _hit_test(self, event):
        picker = Rhino.Input.Custom.PickContext()
        picker.View = event.Viewport.ParentView
        picker.PickStyle = Rhino.Input.Custom.PickStyle.PointPick
        picker.SetPickTransform(event.Viewport.GetPickTransform(event.WindowPoint))
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
                    candidate_rank = (result[-3], -result[-4], index)
                    if best is None or candidate_rank < best:
                        best = candidate_rank
        finally:
            picker.Dispose()
        return None if best is None else best[2]

    def OnMouseMove(self, event):
        index = self._hit_test(event)
        self.state["hover"] = -1 if index is None else index
        Rhino.RhinoDoc.ActiveDoc.Views.Redraw()
        super(_PlanarFaceGetPoint, self).OnMouseMove(event)

    def OnMouseDown(self, event):
        if event.RightButtonDown:
            super(_PlanarFaceGetPoint, self).OnMouseDown(event)
            return
        if not event.LeftButtonDown:
            return
        index = self._hit_test(event)
        if index is None:
            self.state["reject_mouse_up"] = True
            return
        self.state["result"] = index
        super(_PlanarFaceGetPoint, self).OnMouseDown(event)

    def OnMouseUp(self, event):
        if self.state["reject_mouse_up"]:
            self.state["reject_mouse_up"] = False
            return
        super(_PlanarFaceGetPoint, self).OnMouseUp(event)


def _planar_face_candidates(doc):
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
        if isinstance(geometry, Rhino.Geometry.Brep):
            brep = geometry
        elif isinstance(geometry, Rhino.Geometry.Extrusion):
            brep = geometry.ToBrep()
        else:
            continue
        if brep is None:
            continue
        for face in brep.Faces:
            plane = plane_from_brep_face(face, doc.ModelAbsoluteTolerance)
            if plane is None:
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
                    "face_index": int(face.FaceIndex),
                    "face": face,
                    "plane": plane,
                    "brep": brep,
                    "object": rhino_object,
                    "face_brep": face_brep,
                    "meshes": meshes,
                }
            )
    return candidates


def prompt_for_one_planar_brep_face(prompt):
    candidates = _planar_face_candidates(sc.doc)
    if not candidates:
        print("No visible, unlocked planar Brep or extrusion faces are available to select.")
        return None

    state = {"hover": -1, "result": None, "reject_mouse_up": False}
    conduit = _PlanarFaceConduit(candidates, state)
    conduit.Enabled = True
    sc.doc.Views.Redraw()

    picker = _PlanarFaceGetPoint(candidates, state)
    picker.SetCommandPrompt(prompt)
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
        sc.doc.Views.Redraw()


def prompt_for_one_object(prompt):
    getter = Rhino.Input.Custom.GetObject()
    getter.SetCommandPrompt(prompt)
    getter.SubObjectSelect = False
    getter.GeometryFilter = Rhino.DocObjects.ObjectType.Brep | Rhino.DocObjects.ObjectType.Extrusion | Rhino.DocObjects.ObjectType.Surface
    result = getter.Get()
    if result != Rhino.Input.GetResult.Object:
        return None
    obj_ref = getter.Object(0)
    rhino_object = obj_ref.Object()
    if rhino_object is None:
        return None
    return rhino_object


def prompt_for_axis(prompt_a, prompt_b):
    first = Rhino.Input.RhinoGet.GetPoint(prompt_a, False)
    if first[0] != Rhino.Commands.Result.Success:
        return None
    second = Rhino.Input.RhinoGet.GetPoint(prompt_b, False)
    if second[0] != Rhino.Commands.Result.Success:
        return None
    point_a = first[1]
    point_b = second[1]
    direction = point_b - point_a
    if not direction.Unitize() or direction.IsTiny():
        print("Axis points must be distinct.")
        return None
    return point_a, direction


def circle_from_edge(edge, tolerance):
    curve = edge.EdgeCurve
    if curve is None:
        return None
    for candidate in (curve, edge):
        for args in ((), (tolerance,)):
            try:
                result = candidate.TryGetCircle(*args)
            except TypeError:
                continue
            if isinstance(result, tuple) and len(result) == 2 and result[0]:
                return result[1]
        for args in ((), (tolerance,)):
            try:
                result = candidate.TryGetArc(*args)
            except TypeError:
                continue
            if isinstance(result, tuple) and len(result) == 2 and result[0]:
                arc = result[1]
                return Rhino.Geometry.Circle(arc.Plane, arc.Radius)
    return None


def plane_from_brep_face(face, tolerance):
    """Return a planar BrepFace frame with its Brep orientation, else None."""
    if face is None:
        return None
    for args in ((tolerance,), ()):
        try:
            result = face.TryGetPlane(*args)
        except TypeError:
            continue
        if isinstance(result, tuple) and len(result) == 2 and result[0]:
            plane = Rhino.Geometry.Plane(result[1])
            if face.OrientationIsReversed:
                plane.Flip()
            return plane
    return None


def quaternion_from_axes(x_axis, y_axis, z_axis):
    m00, m01, m02 = x_axis.X, y_axis.X, z_axis.X
    m10, m11, m12 = x_axis.Y, y_axis.Y, z_axis.Y
    m20, m21, m22 = x_axis.Z, y_axis.Z, z_axis.Z
    trace = m00 + m11 + m22
    if trace > 0.0:
        s = math.sqrt(trace + 1.0) * 2.0
        w = 0.25 * s
        x = (m21 - m12) / s
        y = (m02 - m20) / s
        z = (m10 - m01) / s
    elif m00 > m11 and m00 > m22:
        s = math.sqrt(1.0 + m00 - m11 - m22) * 2.0
        w = (m21 - m12) / s
        x = 0.25 * s
        y = (m01 + m10) / s
        z = (m02 + m20) / s
    elif m11 > m22:
        s = math.sqrt(1.0 + m11 - m00 - m22) * 2.0
        w = (m02 - m20) / s
        x = (m01 + m10) / s
        y = 0.25 * s
        z = (m12 + m21) / s
    else:
        s = math.sqrt(1.0 + m22 - m00 - m11) * 2.0
        w = (m10 - m01) / s
        x = (m02 + m20) / s
        y = (m12 + m21) / s
        z = 0.25 * s
    return (w, x, y, z)


def plane_from_pose(position, quaternion):
    w, x, y, z = quaternion
    xx, yy, zz = x * x, y * y, z * z
    xy, xz, yz = x * y, x * z, y * z
    wx, wy, wz = w * x, w * y, w * z
    x_axis = Rhino.Geometry.Vector3d(1 - 2 * (yy + zz), 2 * (xy + wz), 2 * (xz - wy))
    y_axis = Rhino.Geometry.Vector3d(2 * (xy - wz), 1 - 2 * (xx + zz), 2 * (yz + wx))
    return Rhino.Geometry.Plane(Rhino.Geometry.Point3d(*position), x_axis, y_axis)


def pose_from_plane(plane):
    return point_tuple(plane.Origin), quaternion_from_axes(plane.XAxis, plane.YAxis, plane.ZAxis)


def plane_from_axis(origin, direction):
    z_axis = Rhino.Geometry.Vector3d(direction)
    z_axis.Unitize()
    x_axis = Rhino.Geometry.Vector3d.XAxis
    if abs(z_axis * x_axis) > 0.999:
        x_axis = Rhino.Geometry.Vector3d.YAxis
    y_axis = Rhino.Geometry.Vector3d.CrossProduct(z_axis, x_axis)
    y_axis.Unitize()
    x_axis = Rhino.Geometry.Vector3d.CrossProduct(y_axis, z_axis)
    x_axis.Unitize()
    return Rhino.Geometry.Plane(origin, x_axis, y_axis)


def plane_from_x_axis(origin, direction):
    x_axis = Rhino.Geometry.Vector3d(direction)
    x_axis.Unitize()
    y_axis = Rhino.Geometry.Vector3d.YAxis
    if abs(x_axis * y_axis) > 0.999:
        y_axis = Rhino.Geometry.Vector3d.ZAxis
    z_axis = Rhino.Geometry.Vector3d.CrossProduct(x_axis, y_axis)
    z_axis.Unitize()
    y_axis = Rhino.Geometry.Vector3d.CrossProduct(z_axis, x_axis)
    y_axis.Unitize()
    return Rhino.Geometry.Plane(origin, x_axis, y_axis)


def transform_between_planes(from_plane, to_plane):
    return Rhino.Geometry.Transform.PlaneToPlane(from_plane, to_plane)


def transformed_plane(plane, transform):
    copy = Rhino.Geometry.Plane(plane)
    copy.Transform(transform)
    return copy


def object_runtime_serial(rhino_object):
    if rhino_object is None:
        return None
    return int(rhino_object.RuntimeSerialNumber)


def guid_string(value):
    return str(value)


def parse_guid(value):
    if isinstance(value, System.Guid):
        return value
    return rs.coerceguid(value)
