import math
import os
import sys

import Rhino
import System
import rhinoscriptsyntax as rs

from ondsel.assembly import ondsel_module

TACK_ROOT = "/Users/tristanryerparke/projects-local/tack"
MODULES_DIR = os.path.join(TACK_ROOT, "ondsel", "rhino_modules")
if MODULES_DIR not in sys.path:
    sys.path.insert(0, MODULES_DIR)

BREP_EDGE_COMPONENT_TYPE = Rhino.Geometry.ComponentIndexType.BrepEdge
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
