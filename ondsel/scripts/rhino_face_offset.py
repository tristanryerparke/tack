"""Constrain two selected planar Brep faces with an OndselSolver planar joint.

Run from the Tack repository root:

    uv run rhino-watch ondsel/scripts/rhino_face_offset.py --debug

Select a planar face on a fixed parent Brep, then one on a child Brep. The
command captures the child face's current in-plane location and spin, prompts
for a signed normal offset, and moves the child to a valid planar-joint pose.
The joint leaves in-plane sliding and rotation about the face normal free.
"""
import json
import math
import os
import sys

import Rhino
import scriptcontext as sc

from run_in_rhino.rhino_env.client import SocketConnection
from run_in_rhino.rhino_env.env import install_sticky_environment
from run_in_rhino.rhino_env.parasite import OutputParasite

TACK_ROOT = "/Users/tristanryerparke/projects-local/tack"
if TACK_ROOT not in sys.path:
    sys.path.insert(0, TACK_ROOT)

from ondsel.assembly import ondsel_module


BREP_FACE_COMPONENT_TYPE = Rhino.Geometry.ComponentIndexType.BrepFace


def _plane_from_face(face, tolerance):
    """Return the outward-facing plane of a planar BrepFace, else None."""
    for arguments in ((tolerance,), ()):
        try:
            result = face.TryGetPlane(*arguments)
        except TypeError:
            continue
        if isinstance(result, tuple) and len(result) == 2 and result[0]:
            plane = Rhino.Geometry.Plane(result[1])
            if face.OrientationIsReversed:
                plane.Flip()
            return plane
    return None


def _face_only_filter(_rhino_object, geometry, component_index):
    return (
        component_index.ComponentIndexType == BREP_FACE_COMPONENT_TYPE
        or isinstance(geometry, Rhino.Geometry.BrepFace)
    )


def prompt_for_one_planar_face(prompt):
    """Select exactly one planar Brep face and retain its owning object."""
    getter = Rhino.Input.Custom.GetObject()
    getter.SetCommandPrompt(prompt)
    getter.GeometryFilter = Rhino.DocObjects.ObjectType.Surface
    getter.SetCustomGeometryFilter(_face_only_filter)
    getter.SubObjectSelect = True
    getter.ChooseOneQuestion = False
    getter.AlreadySelectedObjectSelect = True
    getter.EnablePreSelect(True, True)
    getter.EnablePostSelect(True)

    if getter.Get() != Rhino.Input.GetResult.Object:
        return None

    object_ref = getter.Object(0)
    face = object_ref.Face()
    rhino_object = object_ref.Object()
    if face is None or rhino_object is None:
        print("Select a Brep face subobject.")
        return None

    plane = _plane_from_face(face, sc.doc.ModelAbsoluteTolerance)
    if plane is None:
        print("Selected face is not planar.")
        return None

    return {
        "object_id": object_ref.ObjectId,
        "face_index": int(face.FaceIndex),
        "plane": plane,
    }


def _point_tuple(point):
    return (float(point.X), float(point.Y), float(point.Z))


def _quaternion_from_axes(x_axis, y_axis, z_axis):
    """Frame axes -> Ondsel's Hamilton quaternion (w, x, y, z)."""
    m00, m01, m02 = x_axis.X, y_axis.X, z_axis.X
    m10, m11, m12 = x_axis.Y, y_axis.Y, z_axis.Y
    m20, m21, m22 = x_axis.Z, y_axis.Z, z_axis.Z
    trace = m00 + m11 + m22
    if trace > 0.0:
        scale = math.sqrt(trace + 1.0) * 2.0
        return (
            0.25 * scale,
            (m21 - m12) / scale,
            (m02 - m20) / scale,
            (m10 - m01) / scale,
        )
    if m00 > m11 and m00 > m22:
        scale = math.sqrt(1.0 + m00 - m11 - m22) * 2.0
        return (
            (m21 - m12) / scale,
            0.25 * scale,
            (m01 + m10) / scale,
            (m02 + m20) / scale,
        )
    if m11 > m22:
        scale = math.sqrt(1.0 + m11 - m00 - m22) * 2.0
        return (
            (m02 - m20) / scale,
            (m01 + m10) / scale,
            0.25 * scale,
            (m12 + m21) / scale,
        )
    scale = math.sqrt(1.0 + m22 - m00 - m11) * 2.0
    return (
        (m10 - m01) / scale,
        (m02 + m20) / scale,
        (m12 + m21) / scale,
        0.25 * scale,
    )


def _pose_from_plane(plane):
    return (
        _point_tuple(plane.Origin),
        _quaternion_from_axes(plane.XAxis, plane.YAxis, plane.ZAxis),
    )


def _plane_from_pose(position, quaternion):
    w, x, y, z = quaternion
    xx, yy, zz = x * x, y * y, z * z
    xy, xz, yz = x * y, x * z, y * z
    wx, wy, wz = w * x, w * y, w * z
    x_axis = Rhino.Geometry.Vector3d(
        1 - 2 * (yy + zz), 2 * (xy + wz), 2 * (xz - wy)
    )
    y_axis = Rhino.Geometry.Vector3d(
        2 * (xy - wz), 1 - 2 * (xx + zz), 2 * (yz + wx)
    )
    return Rhino.Geometry.Plane(Rhino.Geometry.Point3d(*position), x_axis, y_axis)


def prompt_for_offset(initial_offset):
    """Get an offset in model units; Enter accepts the selected faces' gap."""
    getter = Rhino.Input.Custom.GetOption()
    getter.SetCommandPrompt(
        "Set signed face offset ({:.4f}); press Enter to accept".format(
            initial_offset
        )
    )
    getter.AcceptNothing(True)
    offset = Rhino.Input.Custom.OptionDouble(initial_offset)
    getter.AddOptionDouble("Offset", offset)

    while True:
        result = getter.Get()
        if result == Rhino.Input.GetResult.Cancel:
            return None
        if result == Rhino.Input.GetResult.Nothing:
            return float(offset.CurrentValue)


def _live_face_plane(object_id, face_index):
    rhino_object = sc.doc.Objects.FindId(object_id)
    if rhino_object is None:
        return None
    geometry = rhino_object.Geometry
    brep = geometry if isinstance(geometry, Rhino.Geometry.Brep) else geometry.ToBrep()
    if brep is None or face_index < 0 or face_index >= brep.Faces.Count:
        return None
    return _plane_from_face(brep.Faces[face_index], sc.doc.ModelAbsoluteTolerance)


def main():
    parent = prompt_for_one_planar_face("Select planar face on FIXED parent Brep")
    if parent is None:
        return None

    child = prompt_for_one_planar_face("Select planar face on child Brep to MOVE")
    if child is None:
        return None
    if parent["object_id"] == child["object_id"]:
        print("Select faces on two different objects.")
        return None

    initial_offset = (child["plane"].Origin - parent["plane"].Origin) * parent[
        "plane"
    ].ZAxis
    offset = prompt_for_offset(initial_offset)
    if offset is None:
        return None

    module = ondsel_module.load()
    assembly = module.Assembly("PlanarFaceOffset")
    identity_position = (0.0, 0.0, 0.0)
    identity_quaternion = (1.0, 0.0, 0.0, 0.0)
    assembly.add_part("parent", identity_position, identity_quaternion)
    assembly.add_part("child", identity_position, identity_quaternion)
    assembly.set_fixed("parent", True)

    parent_position, parent_quaternion = _pose_from_plane(parent["plane"])
    child_position, child_quaternion = _pose_from_plane(child["plane"])
    assembly.add_marker("parent", "face", parent_position, parent_quaternion)
    assembly.add_marker("child", "face", child_position, child_quaternion)
    assembly.add_planar_joint(
        "face_offset", "parent", "face", "child", "face", offset
    )
    assembly.solve()

    solved_position, solved_quaternion = assembly.get_pose("child")
    solved_plane = _plane_from_pose(solved_position, solved_quaternion)
    transform = Rhino.Geometry.Transform.PlaneToPlane(
        Rhino.Geometry.Plane.WorldXY, solved_plane
    )
    transformed_id = sc.doc.Objects.Transform(child["object_id"], transform, True)
    if transformed_id is None:
        print("Could not transform child Brep.")
        return None
    sc.doc.Views.Redraw()

    parent_plane = _live_face_plane(parent["object_id"], parent["face_index"])
    child_plane = _live_face_plane(transformed_id, child["face_index"])
    if parent_plane is None or child_plane is None:
        print("Solved, but could not re-read one of the selected faces.")
        return None

    solved_offset = (child_plane.Origin - parent_plane.Origin) * parent_plane.ZAxis
    normal_alignment = abs(parent_plane.ZAxis * child_plane.ZAxis)
    result = {
        "parent_id": str(parent["object_id"]),
        "parent_face_index": parent["face_index"],
        "child_id": str(transformed_id),
        "child_face_index": child["face_index"],
        "requested_offset": offset,
        "solved_offset": solved_offset,
        "normal_alignment": normal_alignment,
    }
    print(
        "Planar face offset solved: requested={:.6f}, solved={:.6f}, "
        "normal alignment={:.9f}".format(
            offset, solved_offset, normal_alignment
        )
    )
    return result


connection = SocketConnection()
install_sticky_environment(connection)

with OutputParasite(connection, done_msg=True):
    payload = main()
    if payload is not None:
        connection.send_data(json.dumps(payload))
