"""Interactive Rhino PoC: align two objects with a revolute joint from edges.

Run from the tack repo root:

    uv run rhino-watch ondsel/scripts/rhino_edge_joint.py --debug

Flow:
1. Pick a circular Brep edge on the fixed parent object (e.g. a hole rim).
2. Pick a circular Brep edge on the child object to move (e.g. a bolt rim).
3. Circle centers/axes become solver markers; OndselSolver solves a revolute
   joint and the child object is transformed onto the parent's circle.
4. A dialog offers "Invert child plane" which flips the child's marker Z
   axis 180 degrees and re-solves, flipping the approach direction.
"""
import json
import math
import os
import sys

import Rhino
import scriptcontext as sc

import Eto.Forms as forms

from run_in_rhino.rhino_env.client import SocketConnection
from run_in_rhino.rhino_env.env import install_sticky_environment
from run_in_rhino.rhino_env.parasite import OutputParasite

TACK_ROOT = "/Users/tristanryerparke/projects-local/tack"
MODULES_DIR = os.path.join(TACK_ROOT, "ondsel", "rhino_modules")
sys.path.insert(0, MODULES_DIR)

import ondselsolver  # noqa: E402

BREP_EDGE_COMPONENT_TYPE = Rhino.Geometry.ComponentIndexType.BrepEdge
BREP_TRIM_COMPONENT_TYPE = Rhino.Geometry.ComponentIndexType.BrepTrim


# ---------------------------------------------------------------------------
# Edge picking (adapted from example_select_brep_edge.py)
# ---------------------------------------------------------------------------

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
    """Accept one selectable trim for each topological BrepEdge."""
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
    """Select one Brep edge and keep it highlighted until Done/Enter."""
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
        if edge is None or brep is None:
            continue
        key = (obj_ref.ObjectId, edge.EdgeIndex)
        if key in seen:
            continue
        seen.add(key)
        edge_data.append(
            {
                "object_id": obj_ref.ObjectId,
                "edge": edge,
            }
        )

    if len(edge_data) != 1:
        print("Select exactly one Brep edge; got {}.".format(len(edge_data)))
        return None

    return edge_data[0]


# ---------------------------------------------------------------------------
# Geometry helpers
# ---------------------------------------------------------------------------

def circle_from_edge(edge):
    """Return a Rhino.Geometry.Circle for a circular edge, else None."""
    curve = edge.EdgeCurve
    if curve is None:
        return None
    print("DEBUG edge curve type: {}".format(type(curve).__name__))
    for tolerance in (None, sc.doc.ModelAbsoluteTolerance):
        try:
            if tolerance is None:
                result = curve.TryGetCircle()
            else:
                result = curve.TryGetCircle(tolerance)
        except TypeError:
            continue
        if isinstance(result, tuple) and len(result) == 2 and result[0]:
            return result[1]
    # Circular edges are frequently stored as arcs (including full-circle
    # arcs); try the arc path before giving up.
    for tolerance in (None, sc.doc.ModelAbsoluteTolerance):
        try:
            if tolerance is None:
                arc_result = curve.TryGetArc()
            else:
                arc_result = curve.TryGetArc(tolerance)
        except TypeError:
            continue
        if isinstance(arc_result, tuple) and len(arc_result) == 2 and arc_result[0]:
            arc = arc_result[1]
            circle = Rhino.Geometry.Circle(arc.Plane, arc.Radius)
            return circle
    return None


def point_tuple(point):
    return (point.X, point.Y, point.Z)


def quaternion_from_axes(x_axis, y_axis, z_axis):
    """Frame axes -> Hamilton quaternion (w, x, y, z), columns = basis."""
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


def flipped_plane(plane):
    """Rotate a plane 180 degrees about its own X axis."""
    return Rhino.Geometry.Plane(
        plane.Origin,
        plane.XAxis,
        -plane.YAxis,
    )


def plane_from_pose(position, quaternion):
    """Ondsel (w, x, y, z) quaternion + position -> Rhino plane."""
    w, x, y, z = quaternion
    xx, yy, zz = x * x, y * y, z * z
    xy, xz, yz = x * y, x * z, y * z
    wx, wy, wz = w * x, w * y, w * z
    x_axis = Rhino.Geometry.Vector3d(1 - 2 * (yy + zz), 2 * (xy + wz), 2 * (xz - wy))
    y_axis = Rhino.Geometry.Vector3d(2 * (xy - wz), 1 - 2 * (xx + zz), 2 * (yz + wx))
    return Rhino.Geometry.Plane(Rhino.Geometry.Point3d(*position), x_axis, y_axis)


# ---------------------------------------------------------------------------
# Solver flow
# ---------------------------------------------------------------------------

def solve_child_transform(parent_circle, child_circle, invert):
    """Solve revolute joint; return the world transform for the child.

    Both parts start at the identity pose (part frame == world frame), with
    markers at their world-space circle centers, so the solved child pose is
    exactly the rigid motion to apply to the Rhino object.
    """
    assembly = ondselsolver.Assembly("Assembly1")
    assembly.add_part("parent", (0.0, 0.0, 0.0), (1.0, 0.0, 0.0, 0.0))
    assembly.add_part("child", (0.0, 0.0, 0.0), (1.0, 0.0, 0.0, 0.0))
    assembly.set_fixed("parent", True)

    parent_plane = parent_circle.Plane
    child_plane = flipped_plane(child_circle.Plane) if invert else child_circle.Plane

    assembly.add_marker(
        "parent",
        "joint",
        point_tuple(parent_circle.Center),
        quaternion_from_axes(
            parent_plane.XAxis, parent_plane.YAxis, parent_plane.ZAxis
        ),
    )
    assembly.add_marker(
        "child",
        "joint",
        point_tuple(child_circle.Center),
        quaternion_from_axes(
            child_plane.XAxis, child_plane.YAxis, child_plane.ZAxis
        ),
    )
    assembly.add_revolute_joint("J1", "parent", "joint", "child", "joint")

    assembly.solve()
    position, quaternion = assembly.get_pose("child")
    print(
        "DEBUG invert={} solved position={!r} quaternion={!r}".format(
            invert, position, quaternion
        )
    )

    solved_plane = plane_from_pose(position, quaternion)
    return Rhino.Geometry.Transform.PlaneToPlane(
        Rhino.Geometry.Plane.WorldXY, solved_plane
    )


def main():
    parent_data = prompt_for_one_brep_edge(
        "Select circular edge on FIXED object (hole)"
    )
    if parent_data is None:
        return None

    child_data = prompt_for_one_brep_edge(
        "Select circular edge on object to MOVE (bolt)"
    )
    if child_data is None:
        return None

    if parent_data["object_id"] == child_data["object_id"]:
        print("Pick edges on two different objects.")
        return None

    parent_circle = circle_from_edge(parent_data["edge"])
    child_circle = circle_from_edge(child_data["edge"])
    if parent_circle is None or child_circle is None:
        print("Both edges must be circular.")
        return None

    print(
        "DEBUG parent circle center={} radius={:.3f}; child circle center={} "
        "radius={:.3f}".format(
            parent_circle.Center,
            parent_circle.Radius,
            child_circle.Center,
            child_circle.Radius,
        )
    )

    child_id = child_data["object_id"]
    state = {"transform": None}

    def apply(invert):
        if state["transform"] is not None:
            restore = state["transform"].Inverse()
            sc.doc.Objects.Transform(child_id, restore, True)
            state["transform"] = None
        transform = solve_child_transform(parent_circle, child_circle, invert)
        sc.doc.Objects.Transform(child_id, transform, True)
        state["transform"] = transform
        sc.doc.Views.Redraw()

    apply(False)

    class _JointDialog(forms.Dialog[bool]):
        def __init__(self):
            super(_JointDialog, self).__init__()
            self.Title = "Ondsel joint solve"
            self.Resizable = False
            self.accepted = False

            self.invert_checkbox = forms.CheckBox()
            self.invert_checkbox.Text = "Invert child plane (flip approach)"
            self.invert_checkbox.CheckedChanged += self._invert_changed

            done_button = forms.Button()
            done_button.Text = "Done"
            done_button.Click += self._done

            layout = forms.TableLayout()
            layout.Rows.Add(forms.TableRow(forms.TableCell(self.invert_checkbox, True)))
            layout.Rows.Add(
                forms.TableRow(
                    forms.TableCell(forms.Panel(), True),
                    forms.TableCell(done_button),
                )
            )
            self.Content = layout

        def _invert_changed(self, sender, event):
            try:
                apply(bool(self.invert_checkbox.Checked))
            except Exception as error:
                print("Re-solve failed: {}".format(error))

        def _done(self, sender, event):
            self.accepted = True
            self.Close()

    dialog = _JointDialog()
    dialog.ShowModal(Rhino.UI.RhinoEtoApp.MainWindow)

    result = {
        "parent_id": str(parent_data["object_id"]),
        "child_id": str(child_id),
        "final_transform_applied": state["transform"] is not None,
        "inverted": bool(dialog.invert_checkbox.Checked),
    }
    print("DEBUG result={!r}".format(result))
    return result


connection = SocketConnection()
install_sticky_environment(connection)

with OutputParasite(connection, done_msg=True):
    payload = main()
    if payload is not None:
        connection.send_data(json.dumps(payload))
