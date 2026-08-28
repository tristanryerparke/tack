"""Recreate CPlane 3Point's red-X/green-Y live axis preview.

Run this from the parent terminal:

    uv run rhino-watch demos/cplane_3point_dynamic_draw.py --debug

Each accepted point emits a JSON callback both as terminal output (so
``rhino-watch`` displays it) and as watcher data (so a programmatic parent can
consume it). The final accepted plane is reported only; the active viewport's
CPlane is not changed.
"""

import json

import Rhino
from Rhino.Commands import Result
from run_in_rhino.rhino_env.client import SocketConnection
from run_in_rhino.rhino_env.env import install_os_environment
from run_in_rhino.rhino_env.parasite import OutputParasite


AXIS_SCREEN_LENGTH = 120.0


def _dot(left, right):
    return left.X * right.X + left.Y * right.Y + left.Z * right.Z


def _unit(vector):
    result = Rhino.Geometry.Vector3d(vector)
    if not result.Unitize():
        return None
    return result


def _perpendicular(vector, axis):
    """Return vector projected into the plane normal to the unit axis."""
    return _unit(vector - axis * _dot(vector, axis))


def _axis_length(viewport, origin):
    # RhinoViewport.GetWorldToScreenScale has an ``out`` argument. Rhino's
    # Python bridge exposes that as ``(success, pixels_per_unit)``, rather than
    # as the scalar returned by the newer ViewportInfo overload.
    success, pixels_per_unit = viewport.GetWorldToScreenScale(origin)
    if success and pixels_per_unit > 0.0:
        return AXIS_SCREEN_LENGTH / pixels_per_unit
    return 10.0


def _point_data(point):
    return [point.X, point.Y, point.Z]


def _emit_callback(connection, parasite, event, **data):
    payload = {"callback": "cplane_3point_dynamic_draw", "event": event}
    payload.update(data)
    encoded = json.dumps(payload, sort_keys=True)
    print("CALLBACK {}".format(encoded))
    # OutputParasite buffers output until it exits. Flush each callback so the
    # terminal parent sees point selections while the command remains active.
    parasite.flush()
    connection.send_data(encoded)


def _draw_axes(display, origin, x_axis, y_axis, axis_length):
    appearance = Rhino.ApplicationSettings.AppearanceSettings
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

    def _axes(self, current):
        if self.origin is None:
            # Origin stage: preserve the active CPlane orientation exactly.
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

            # The first axis is being picked. Keep its companion perpendicular
            # while choosing the direction that is closest to the current
            # CPlane's Y axis.
            y_axis = _perpendicular(self.construction_plane.YAxis, x_axis)
            if y_axis is None:
                y_axis = _perpendicular(self.construction_plane.ZAxis, x_axis)
            return self.origin, x_axis, y_axis

        # Y's displayed direction is the current point projected perpendicular
        # to the fixed X axis. This is the same right-angle constraint that the
        # Plane(origin, x_point, y_point) constructor applies to the final Y.
        y_axis = _perpendicular(current - self.origin, x_axis)
        if y_axis is None:
            y_axis = _perpendicular(self.construction_plane.YAxis, x_axis)
        return self.origin, x_axis, y_axis

    def OnMouseMove(self, event):
        # A DisplayConduit avoids the clipping failure that can hide geometry
        # drawn solely from GetPoint.OnDynamicDraw. It is updated for every
        # point-getter mouse move and redrawn in the same interaction frame.
        if self.preview is not None:
            self.preview.update(event.Point, event.Viewport)
            Rhino.RhinoDoc.ActiveDoc.Views.Redraw()
        super(AxisPreviewGetPoint, self).OnMouseMove(event)

    def OnDynamicDraw(self, event):
        # Keep the DynamicDraw callback in the flow too. This catches changes
        # that reach GetPoint without a mouse-move callback (for example snaps).
        if self.preview is not None:
            self.preview.update(event.CurrentPoint, event.Viewport)
        super(AxisPreviewGetPoint, self).OnDynamicDraw(event)


class AxisPreviewConduit(Rhino.Display.DisplayConduit):
    def __init__(self, getter):
        super(AxisPreviewConduit, self).__init__()
        self.getter = getter
        self.state = None

    def update(self, current, viewport):
        origin, x_axis, y_axis = self.getter._axes(current)
        self.state = (origin, x_axis, y_axis, _axis_length(viewport, origin))

    def CalculateBoundingBox(self, event):
        if self.state is None:
            return
        origin, x_axis, y_axis, axis_length = self.state
        points = [origin]
        if x_axis is not None:
            points.append(origin + x_axis * axis_length)
        if y_axis is not None:
            points.append(origin + y_axis * axis_length)
        event.IncludeBoundingBox(Rhino.Geometry.BoundingBox(points))

    def DrawOverlay(self, event):
        if self.state is None:
            return
        _draw_axes(event.Display, *self.state)


def _pick_point(prompt, construction_plane, origin=None, x_point=None):
    getter = AxisPreviewGetPoint(construction_plane, origin, x_point)
    getter.SetCommandPrompt(prompt)
    getter.AcceptNothing(False)
    getter.PermitObjectSnap(True)
    getter.FullFrameRedrawDuringGet = True

    conduit = AxisPreviewConduit(getter)
    getter.preview = conduit
    conduit.Enabled = True
    try:
        if getter.Get() != Rhino.Input.GetResult.Point:
            return None
        return getter.Point()
    finally:
        conduit.Enabled = False
        Rhino.RhinoDoc.ActiveDoc.Views.Redraw()


def _pick_nonzero_x(construction_plane, origin, connection, parasite):
    while True:
        point = _pick_point("CPlane 3Point demo: pick X axis", construction_plane, origin)
        if point is None:
            return None
        if _unit(point - origin) is not None:
            return point
        _emit_callback(connection, parasite, "invalid_x", point=_point_data(point))
        print("The X-axis point must differ from the origin.")
        parasite.flush()


def _pick_valid_y(construction_plane, origin, x_point, connection, parasite):
    while True:
        point = _pick_point(
            "CPlane 3Point demo: pick Y axis",
            construction_plane,
            origin,
            x_point,
        )
        if point is None:
            return None
        plane = Rhino.Geometry.Plane(origin, x_point, point)
        if plane.IsValid:
            return point, plane
        _emit_callback(connection, parasite, "invalid_y", point=_point_data(point))
        print("The Y-axis point must not be on the X axis.")
        parasite.flush()


def RunCommand(is_interactive, connection, parasite):
    doc = Rhino.RhinoDoc.ActiveDoc
    view = doc.Views.ActiveView if doc is not None else None
    if view is None:
        _emit_callback(connection, parasite, "cancelled", reason="no_active_view")
        return Result.Cancel

    viewport = view.ActiveViewport
    construction_plane = viewport.ConstructionPlane()
    _emit_callback(connection, parasite, "started")

    origin = _pick_point("CPlane 3Point demo: pick origin", construction_plane)
    if origin is None:
        _emit_callback(connection, parasite, "cancelled", stage="origin")
        return Result.Cancel
    _emit_callback(connection, parasite, "origin", point=_point_data(origin))

    x_point = _pick_nonzero_x(construction_plane, origin, connection, parasite)
    if x_point is None:
        _emit_callback(connection, parasite, "cancelled", stage="x_axis")
        return Result.Cancel
    _emit_callback(connection, parasite, "x_axis", point=_point_data(x_point))

    y_result = _pick_valid_y(
        construction_plane,
        origin,
        x_point,
        connection,
        parasite,
    )
    if y_result is None:
        _emit_callback(connection, parasite, "cancelled", stage="y_axis")
        return Result.Cancel
    y_point, plane = y_result
    _emit_callback(connection, parasite, "y_axis", point=_point_data(y_point))

    definition = {
        "origin": _point_data(plane.Origin),
        "x_axis": _point_data(plane.XAxis),
        "y_axis": _point_data(plane.YAxis),
        "z_axis": _point_data(plane.ZAxis),
    }
    print("Plane definition: {}".format(json.dumps(definition, sort_keys=True)))
    _emit_callback(connection, parasite, "completed", **definition)
    return Result.Success


if __name__ == "__main__":
    connection = SocketConnection()
    install_os_environment(connection)
    with OutputParasite(connection, done_msg=True) as parasite:
        RunCommand(True, connection, parasite)
