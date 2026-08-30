"""Define a persistent three-anchor plane with CPlane-style live axes.

Run this from the parent terminal:

    uv run rhino-watch demos/cplane_3point_dynamic_draw.py --debug

The reusable anchor model lives in ``tack/anchor_definitions.py``. Reusable
OSnap interaction and global-state cleanup live in
``tack/prompting/osnap_anchor_picker.py``. This file contains only the
plane-specific definition, resolver, and dynamic axis preview.
"""

import importlib
import json
import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import Rhino
import System
from Rhino.Commands import Result
from run_in_rhino.rhino_env.client import SocketConnection
from run_in_rhino.rhino_env.env import install_os_environment
from run_in_rhino.rhino_env.parasite import OutputParasite

import tack

importlib.reload(tack).reload()

from tack import anchor_definitions
from tack.prompting.osnap_anchor_picker import AnchorPickSession
from tack.prompting.osnap_anchor_picker import select_object


AXIS_SCREEN_LENGTH = 120.0
PICKER_CALLBACK = "analytic_three_anchor_plane"


def _point_data(point):
    return [point.X, point.Y, point.Z]


def _dot(left, right):
    return left.X * right.X + left.Y * right.Y + left.Z * right.Z


def _unit(vector):
    result = Rhino.Geometry.Vector3d(vector)
    if not result.Unitize():
        return None
    return result


def _perpendicular(vector, axis):
    return _unit(vector - axis * _dot(vector, axis))


def _axis_length(viewport, origin):
    success, pixels_per_unit = viewport.GetWorldToScreenScale(origin)
    if success and pixels_per_unit > 0.0:
        return AXIS_SCREEN_LENGTH / pixels_per_unit
    return 10.0


def _emit_callback(connection, parasite, event, **data):
    payload = {"callback": PICKER_CALLBACK, "event": event}
    payload.update(data)
    encoded = json.dumps(payload, sort_keys=True)
    print("CALLBACK {}".format(encoded))
    parasite.flush()
    connection.send_data(encoded)


def resolve_plane_definition(doc, definition):
    """Analytically regenerate a plane from a saved three-anchor definition."""
    try:
        object_id = System.Guid(definition["object_id"])
    except Exception:
        return None
    obj = doc.Objects.FindId(object_id)
    if obj is None:
        return None

    tolerance = max(doc.ModelAbsoluteTolerance, 1e-7)
    origin = anchor_definitions.resolve(
        obj,
        definition["origin_anchor"],
        tolerance,
    )
    x_point = anchor_definitions.resolve(
        obj,
        definition["x_axis_anchor"],
        tolerance,
    )
    y_point = anchor_definitions.resolve(
        obj,
        definition["y_axis_anchor"],
        tolerance,
    )
    if origin is None or x_point is None or y_point is None:
        return None

    plane = Rhino.Geometry.Plane(origin, x_point, y_point)
    return plane if plane.IsValid else None


def _plane_border(origin, x_axis, y_axis, axis_length):
    if x_axis is None or y_axis is None:
        return []
    return [
        origin - x_axis * axis_length - y_axis * axis_length,
        origin + x_axis * axis_length - y_axis * axis_length,
        origin + x_axis * axis_length + y_axis * axis_length,
        origin - x_axis * axis_length + y_axis * axis_length,
    ]


def _draw_preview(display, origin, x_axis, y_axis, axis_length):
    appearance = Rhino.ApplicationSettings.AppearanceSettings
    border = _plane_border(origin, x_axis, y_axis, axis_length)
    for index, start in enumerate(border):
        display.DrawLine(
            start,
            border[(index + 1) % len(border)],
            appearance.GridThickLineColor,
            1,
        )

    if x_axis is not None:
        display.DrawLine(
            origin,
            origin + x_axis * axis_length,
            appearance.GridXAxisLineColor,
            2,
        )
    if y_axis is not None:
        display.DrawLine(
            origin,
            origin + y_axis * axis_length,
            appearance.GridYAxisLineColor,
            2,
        )


class AxisPreviewGetPoint(Rhino.Input.Custom.GetPoint):
    def __init__(self, construction_plane, origin=None, x_point=None):
        super(AxisPreviewGetPoint, self).__init__()
        self.construction_plane = construction_plane
        self.origin = origin
        self.x_point = x_point
        self.preview = None

    def axes(self, current):
        if self.origin is None:
            return current, self.construction_plane.XAxis, self.construction_plane.YAxis

        x_axis = (
            _unit(self.x_point - self.origin)
            if self.x_point is not None
            else None
        )
        if x_axis is None:
            x_axis = _unit(current - self.origin)
            if x_axis is None:
                x_axis = self.construction_plane.XAxis
            y_axis = _perpendicular(self.construction_plane.YAxis, x_axis)
            if y_axis is None:
                y_axis = _perpendicular(self.construction_plane.ZAxis, x_axis)
            return self.origin, x_axis, y_axis

        y_axis = _perpendicular(current - self.origin, x_axis)
        if y_axis is None:
            y_axis = _perpendicular(self.construction_plane.YAxis, x_axis)
        return self.origin, x_axis, y_axis

    def OnMouseMove(self, event):
        if self.preview is not None:
            self.preview.update(event.Point, event.Viewport)
            Rhino.RhinoDoc.ActiveDoc.Views.Redraw()
        super(AxisPreviewGetPoint, self).OnMouseMove(event)

    def OnDynamicDraw(self, event):
        if self.preview is not None:
            self.preview.update(event.CurrentPoint, event.Viewport)
        super(AxisPreviewGetPoint, self).OnDynamicDraw(event)


class AxisPreviewConduit(Rhino.Display.DisplayConduit):
    def __init__(self, getter):
        super(AxisPreviewConduit, self).__init__()
        self.getter = getter
        self.state = None

    def update(self, current, viewport):
        origin, x_axis, y_axis = self.getter.axes(current)
        self.state = (origin, x_axis, y_axis, _axis_length(viewport, origin))

    def CalculateBoundingBox(self, event):
        if self.state is None:
            return
        origin, x_axis, y_axis, axis_length = self.state
        points = [origin]
        points.extend(_plane_border(origin, x_axis, y_axis, axis_length))
        if x_axis is not None:
            points.append(origin + x_axis * axis_length)
        if y_axis is not None:
            points.append(origin + y_axis * axis_length)
        event.IncludeBoundingBox(Rhino.Geometry.BoundingBox(points))

    def DrawOverlay(self, event):
        if self.state is not None:
            _draw_preview(event.Display, *self.state)


def _getter_factory(construction_plane, origin=None, x_point=None):
    return lambda: AxisPreviewGetPoint(construction_plane, origin, x_point)


def _preview_factory(getter):
    conduit = AxisPreviewConduit(getter)
    getter.preview = conduit
    return conduit


def _pick_nonzero_x(session, construction_plane, origin):
    while True:
        picked = session.pick(
            "Pick an analytic anchor for the X axis",
            getter_factory=_getter_factory(construction_plane, origin),
            preview_factory=_preview_factory,
        )
        if picked is None:
            return None
        point, definition = picked
        if _unit(point - origin) is not None:
            return point, definition
        print("The X-axis anchor must resolve away from the origin anchor.")


def _pick_valid_y(session, construction_plane, origin, x_point):
    while True:
        picked = session.pick(
            "Pick an analytic anchor for the Y axis",
            getter_factory=_getter_factory(
                construction_plane,
                origin,
                x_point,
            ),
            preview_factory=_preview_factory,
        )
        if picked is None:
            return None
        point, definition = picked
        plane = Rhino.Geometry.Plane(origin, x_point, point)
        if plane.IsValid:
            return point, definition
        print("The Y-axis anchor must not resolve onto the X axis.")


def RunCommand(is_interactive, connection, parasite):
    doc = Rhino.RhinoDoc.ActiveDoc
    view = doc.Views.ActiveView if doc is not None else None
    if view is None:
        _emit_callback(connection, parasite, "cancelled", reason="no_active_view")
        return Result.Cancel

    obj = select_object(doc, "Select object that will define the plane")
    if obj is None:
        _emit_callback(connection, parasite, "cancelled", stage="object")
        return Result.Cancel

    construction_plane = view.ActiveViewport.ConstructionPlane()
    with AnchorPickSession(doc, obj) as session:
        _emit_callback(connection, parasite, "started", object_id=str(obj.Id))

        origin_result = session.pick(
            "Pick an analytic anchor for the plane origin",
            getter_factory=_getter_factory(construction_plane),
            preview_factory=_preview_factory,
        )
        if origin_result is None:
            _emit_callback(connection, parasite, "cancelled", stage="origin")
            return Result.Cancel
        origin, origin_definition = origin_result
        _emit_callback(
            connection,
            parasite,
            "origin",
            point=_point_data(origin),
            anchor=origin_definition,
        )

        x_result = _pick_nonzero_x(session, construction_plane, origin)
        if x_result is None:
            _emit_callback(connection, parasite, "cancelled", stage="x_axis")
            return Result.Cancel
        x_point, x_definition = x_result
        _emit_callback(
            connection,
            parasite,
            "x_axis",
            point=_point_data(x_point),
            anchor=x_definition,
        )

        y_result = _pick_valid_y(
            session,
            construction_plane,
            origin,
            x_point,
        )
        if y_result is None:
            _emit_callback(connection, parasite, "cancelled", stage="y_axis")
            return Result.Cancel
        y_point, y_definition = y_result
        _emit_callback(
            connection,
            parasite,
            "y_axis",
            point=_point_data(y_point),
            anchor=y_definition,
        )

    definition = {
        "type": "three_point_plane",
        "object_id": str(obj.Id),
        "origin_anchor": origin_definition,
        "x_axis_anchor": x_definition,
        "y_axis_anchor": y_definition,
    }
    resolved_plane = resolve_plane_definition(doc, definition)
    if resolved_plane is None:
        print("The completed anchor definition could not be resolved.")
        _emit_callback(connection, parasite, "failed", definition=definition)
        return Result.Failure

    print("Plane anchor definition: {}".format(json.dumps(definition, sort_keys=True)))
    _emit_callback(
        connection,
        parasite,
        "completed",
        definition=definition,
        resolved_plane={
            "origin": _point_data(resolved_plane.Origin),
            "x_axis": _point_data(resolved_plane.XAxis),
            "y_axis": _point_data(resolved_plane.YAxis),
            "z_axis": _point_data(resolved_plane.ZAxis),
        },
    )
    return Result.Success


if __name__ == "__main__":
    connection = SocketConnection()
    install_os_environment(connection)
    with OutputParasite(connection, done_msg=True) as parasite:
        RunCommand(True, connection, parasite)
