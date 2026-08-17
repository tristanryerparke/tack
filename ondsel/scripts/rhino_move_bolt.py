"""Rhino-side proof of concept: drive Rhino objects with OndselSolver.

Run from the tack repo root with the watcher in the agent terminal:

    uv run rhino-watch ondsel/scripts/rhino_move_bolt.py --debug

What it does inside Rhino:
1. Adds a fixed base box and a bolt cylinder far from its target.
2. Builds an OndselSolver assembly: base fixed, revolute joint between the
   base's hole marker and the bolt's axis marker.
3. Solves and transforms the bolt Rhino object to the solved pose.
4. Sends before/after positions back to the watcher.
"""
import json
import os
import sys

import Rhino
import scriptcontext as sc

from run_in_rhino.rhino_env.client import SocketConnection
from run_in_rhino.rhino_env.env import install_sticky_environment
from run_in_rhino.rhino_env.parasite import OutputParasite

# The pipe server may run this script from a temp path, so resolve the
# checkout explicitly rather than via __file__.
TACK_ROOT = "/Users/tristanryerparke/projects-local/tack"
MODULES_DIR = os.path.join(TACK_ROOT, "ondsel", "rhino_modules")
sys.path.insert(0, MODULES_DIR)

import ondselsolver  # noqa: E402

BOLT_START = (100.0, 40.0, 30.0)
HOLE_POSITION = (10.0, 5.0, 0.0)


def plane_from_pose(position, quaternion):
    """Part frame (world pose) -> Rhino plane. Ondsel quaternion convention is
    (w, x, y, z); the rotation matrix is the standard Hamilton matrix."""
    w, x, y, z = quaternion
    xx, yy, zz = x * x, y * y, z * z
    xy, xz, yz = x * y, x * z, y * z
    wx, wy, wz = w * x, w * y, w * z
    x_axis = Rhino.Geometry.Vector3d(1 - 2 * (yy + zz), 2 * (xy + wz), 2 * (xz - wy))
    y_axis = Rhino.Geometry.Vector3d(2 * (xy - wz), 1 - 2 * (xx + zz), 2 * (yz + wx))
    return Rhino.Geometry.Plane(
        Rhino.Geometry.Point3d(*position), x_axis, y_axis
    )


def transform_between_poses(pos_a, quat_a, pos_b, quat_b):
    """Rigid transform moving a body from pose A to pose B."""
    plane_a = plane_from_pose(pos_a, quat_a)
    plane_b = plane_from_pose(pos_b, quat_b)
    a_to_world = Rhino.Geometry.Transform.PlaneToPlane(
        Rhino.Geometry.Plane.WorldXY, plane_a
    )
    world_to_b = Rhino.Geometry.Transform.PlaneToPlane(
        Rhino.Geometry.Plane.WorldXY, plane_b
    )
    return Rhino.Geometry.Transform.Multiply(
        world_to_b,
        Rhino.Geometry.Transform.PlaneToPlane(plane_a, Rhino.Geometry.Plane.WorldXY),
    )


def add_geometry():
    base_box = Rhino.Geometry.Box(
        Rhino.Geometry.BoundingBox(
            Rhino.Geometry.Point3d(-20, -10, -10),
            Rhino.Geometry.Point3d(20, 10, 10),
        )
    )
    base_id = sc.doc.Objects.AddBox(base_box)

    circle = Rhino.Geometry.Circle(
        Rhino.Geometry.Plane(
            Rhino.Geometry.Point3d(*BOLT_START), Rhino.Geometry.Vector3d.ZAxis
        ),
        3.0,
    )
    cylinder = Rhino.Geometry.Cylinder(circle, 40.0)
    bolt_brep = Rhino.Geometry.Brep.CreateFromCylinder(cylinder, True, True)
    bolt_id = sc.doc.Objects.AddBrep(bolt_brep)

    return base_id, bolt_id


def main():
    base_id, bolt_id = add_geometry()
    sc.doc.Views.Redraw()

    print("DEBUG created base_id={!r} bolt_id={!r}".format(base_id, bolt_id))

    assembly = ondselsolver.Assembly("Assembly1")
    assembly.add_part("base", (0.0, 0.0, 0.0), (1.0, 0.0, 0.0, 0.0))
    assembly.add_part("bolt", BOLT_START, (1.0, 0.0, 0.0, 0.0))
    assembly.set_fixed("base", True)
    assembly.add_marker("base", "hole", HOLE_POSITION, (1.0, 0.0, 0.0, 0.0))
    assembly.add_marker("bolt", "axis", (0.0, 0.0, 0.0), (1.0, 0.0, 0.0, 0.0))
    assembly.add_revolute_joint("J1", "base", "hole", "bolt", "axis")

    bolt_object = sc.doc.Objects.FindId(bolt_id)
    bbox_before = bolt_object.Geometry.GetBoundingBox(True)

    assembly.solve()

    position, quaternion = assembly.get_pose("bolt")
    print("DEBUG solved bolt pose position={!r} quaternion={!r}".format(
        position, quaternion
    ))

    delta = transform_between_poses(
        BOLT_START, (1.0, 0.0, 0.0, 0.0), position, quaternion
    )
    sc.doc.Objects.Transform(bolt_id, delta, True)
    sc.doc.Views.Redraw()

    bolt_object = sc.doc.Objects.FindId(bolt_id)
    bbox_after = bolt_object.Geometry.GetBoundingBox(True)

    expected_center = Rhino.Geometry.Point3d(*HOLE_POSITION)
    after_center = Rhino.Geometry.Point3d(
        (bbox_after.Min.X + bbox_after.Max.X) / 2,
        (bbox_after.Min.Y + bbox_after.Max.Y) / 2,
        bbox_after.Min.Z,
    )
    distance = expected_center.DistanceTo(after_center)

    payload = {
        "bbox_before_center": [
            (bbox_before.Min.X + bbox_before.Max.X) / 2,
            (bbox_before.Min.Y + bbox_before.Max.Y) / 2,
            bbox_before.Min.Z,
        ],
        "bbox_after_center": [after_center.X, after_center.Y, after_center.Z],
        "solved_position": list(position),
        "expected_position": list(HOLE_POSITION),
        "distance_error": distance,
        "pass": distance < 1e-6,
        "base_id": str(base_id),
        "bolt_id": str(bolt_id),
    }
    print("DEBUG payload={!r}".format(payload))
    return payload


connection = SocketConnection()
install_sticky_environment(connection)

with OutputParasite(connection, done_msg=True):
    result = main()
    connection.send_data(json.dumps(result))
