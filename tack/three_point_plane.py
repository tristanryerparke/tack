"""Resolve and persistently display analytic three-anchor planes."""

import copy
import math

import Rhino
import System
import scriptcontext as sc

from tack import anchor_definitions


STATE_KEY = "Tack.AnalyticThreePointPlane.State"
CONDUIT_KEY = "Tack.AnalyticThreePointPlane.Conduit"
HANDLER_KEY = "Tack.AnalyticThreePointPlane.EndCommandHandler"
AXIS_SCREEN_LENGTH = 120.0


def resolve_definition(doc, definition):
    """Regenerate a plane from a saved three-anchor definition."""
    if not isinstance(definition, dict) or definition.get("type") != "three_point_plane":
        return None
    try:
        object_id = System.Guid(definition["object_id"])
        origin_definition = definition["origin_anchor"]
        x_definition = definition["x_axis_anchor"]
        y_definition = definition["y_axis_anchor"]
    except Exception:
        return None

    obj = doc.Objects.FindId(object_id)
    if obj is None:
        return None

    tolerance = max(doc.ModelAbsoluteTolerance, 1e-7)
    origin = anchor_definitions.resolve(obj, origin_definition, tolerance)
    x_point = anchor_definitions.resolve(obj, x_definition, tolerance)
    y_point = anchor_definitions.resolve(obj, y_definition, tolerance)
    if origin is None or x_point is None or y_point is None:
        return None

    plane = Rhino.Geometry.Plane(origin, x_point, y_point)
    return plane if plane.IsValid else None


def axis_length(viewport, origin):
    success, pixels_per_unit = viewport.GetWorldToScreenScale(origin)
    if success and pixels_per_unit > 0.0:
        return AXIS_SCREEN_LENGTH / pixels_per_unit
    return 10.0


def millimeter_spacing(doc):
    if doc is None:
        return None
    spacing = Rhino.RhinoMath.UnitScale(
        Rhino.UnitSystem.Millimeters,
        doc.ModelUnitSystem,
    )
    return spacing if math.isfinite(spacing) and spacing > 0.0 else None


def plane_border(origin, x_axis, y_axis, length):
    """Return a square with side length ``2 * length`` centered on origin."""
    if x_axis is None or y_axis is None:
        return []
    return [
        origin - x_axis * length - y_axis * length,
        origin + x_axis * length - y_axis * length,
        origin + x_axis * length + y_axis * length,
        origin - x_axis * length + y_axis * length,
    ]


def _grid_lines(origin, x_axis, y_axis, length, spacing):
    if x_axis is None or y_axis is None or spacing is None:
        return []

    # Exclude offsets exactly on the border; the border has its own color.
    offset_count = max(0, int(math.ceil(length / spacing)) - 1)
    lines = []
    for index in range(-offset_count, offset_count + 1):
        offset = index * spacing
        lines.append(
            Rhino.Geometry.Line(
                origin + x_axis * offset - y_axis * length,
                origin + x_axis * offset + y_axis * length,
            )
        )
        lines.append(
            Rhino.Geometry.Line(
                origin + y_axis * offset - x_axis * length,
                origin + y_axis * offset + x_axis * length,
            )
        )
    return lines


def draw_preview(display, origin, x_axis, y_axis, length, grid_spacing=None):
    appearance = Rhino.ApplicationSettings.AppearanceSettings
    grid_lines = _grid_lines(
        origin,
        x_axis,
        y_axis,
        length,
        grid_spacing,
    )
    if grid_lines:
        display.DrawLines(grid_lines, appearance.GridThinLineColor, 1)

    border = plane_border(origin, x_axis, y_axis, length)
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
            origin + x_axis * length,
            appearance.GridXAxisLineColor,
            2,
        )
    if y_axis is not None:
        display.DrawLine(
            origin,
            origin + y_axis * length,
            appearance.GridYAxisLineColor,
            2,
        )


def _document_matches(event, state):
    doc = getattr(event, "RhinoDoc", None)
    return doc is not None and doc.RuntimeSerialNumber == state["document_serial"]


def _display_points(state):
    plane = state.get("plane")
    length = state.get("axis_length")
    if plane is None or length is None:
        return []
    points = plane_border(plane.Origin, plane.XAxis, plane.YAxis, length)
    points.extend(
        (
            plane.Origin,
            plane.Origin + plane.XAxis * length,
            plane.Origin + plane.YAxis * length,
        )
    )
    return points


class PersistentPlaneConduit(Rhino.Display.DisplayConduit):
    def __init__(self, state):
        super(PersistentPlaneConduit, self).__init__()
        self.state = state

    def CalculateBoundingBox(self, event):
        if not _document_matches(event, self.state):
            return
        points = _display_points(self.state)
        if points:
            event.IncludeBoundingBox(Rhino.Geometry.BoundingBox(points))

    def DrawOverlay(self, event):
        if not _document_matches(event, self.state):
            return
        plane = self.state.get("plane")
        length = self.state.get("axis_length")
        if plane is None or length is None:
            return
        draw_preview(
            event.Display,
            plane.Origin,
            plane.XAxis,
            plane.YAxis,
            length,
            self.state.get("grid_spacing"),
        )


def _refresh(doc, state):
    plane = resolve_definition(doc, state["definition"])
    state["plane"] = plane
    state["axis_length"] = None
    state["grid_spacing"] = millimeter_spacing(doc)
    if plane is None:
        return False

    view = doc.Views.ActiveView
    if view is None:
        return False
    state["axis_length"] = axis_length(view.ActiveViewport, plane.Origin)
    return True


def EndCommandHandler(sender, event):
    """Re-resolve the sticky plane after every completed Rhino command."""
    state = sc.sticky.get(STATE_KEY)
    if state is None:
        return
    doc = Rhino.RhinoDoc.ActiveDoc
    if doc is None or doc.RuntimeSerialNumber != state["document_serial"]:
        return
    try:
        _refresh(doc, state)
    except Exception:
        # A document edit can temporarily make topology unavailable. Keep the
        # command lifecycle healthy and hide the preview until it resolves.
        state["plane"] = None
        state["axis_length"] = None
        state["grid_spacing"] = None
    finally:
        doc.Views.Redraw()


def uninstall():
    """Remove the previously installed handler, conduit, and sticky state."""
    handler = sc.sticky.pop(HANDLER_KEY, None)
    if handler is not None:
        try:
            Rhino.Commands.Command.EndCommand -= handler
        except Exception:
            pass

    conduit = sc.sticky.pop(CONDUIT_KEY, None)
    if conduit is not None:
        conduit.Enabled = False

    state = sc.sticky.pop(STATE_KEY, None)
    doc = Rhino.RhinoDoc.ActiveDoc
    if doc is not None:
        doc.Views.Redraw()
    return state


def install(doc, definition):
    """Install a sticky conduit and EndCommand handler for a saved definition."""
    uninstall()
    state = {
        "document_serial": doc.RuntimeSerialNumber,
        "definition": copy.deepcopy(definition),
        "plane": None,
        "axis_length": None,
        "grid_spacing": None,
    }
    if not _refresh(doc, state):
        return None

    conduit = PersistentPlaneConduit(state)
    conduit.Enabled = True
    sc.sticky[STATE_KEY] = state
    sc.sticky[CONDUIT_KEY] = conduit
    sc.sticky[HANDLER_KEY] = EndCommandHandler
    Rhino.Commands.Command.EndCommand += EndCommandHandler
    doc.Views.Redraw()
    return state
