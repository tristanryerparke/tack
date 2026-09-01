"""Resolve and persistently display supported analytic plane definitions."""

import copy
import math

import Rhino
import System
import System.Drawing
import scriptcontext as sc

from tack import anchor_definitions


STATE_KEY = "Tack.AnalyticThreePointPlane.State"
CONDUIT_KEY = "Tack.AnalyticThreePointPlane.Conduit"
HANDLER_KEY = "Tack.AnalyticThreePointPlane.EndCommandHandler"
CROSSHAIR_SIZE = 20.0
GRID_SPACING = 1.0
DEFAULT_MAJOR_GRID_FREQUENCY = 5
CROSSHAIR_COLOR = System.Drawing.Color.Orange
CROSSHAIR_THICKNESS = 2
GRID_THICKNESS = 1


def preview_half_extent():
    return CROSSHAIR_SIZE * 0.5


def preview_circle_radius():
    return CROSSHAIR_SIZE * 0.25


def _definition_object(doc, definition):
    try:
        object_id = System.Guid(str(definition["object_id"]))
    except Exception:
        return None
    return doc.Objects.FindId(object_id)


def _resolve_three_point_plane(doc, definition):
    obj = _definition_object(doc, definition)
    if obj is None:
        return None
    try:
        origin_definition = definition["origin_anchor"]
        x_definition = definition["x_axis_anchor"]
        y_definition = definition["y_axis_anchor"]
    except Exception:
        return None

    tolerance = max(doc.ModelAbsoluteTolerance, 1e-7)
    origin = anchor_definitions.resolve(obj, origin_definition, tolerance)
    x_point = anchor_definitions.resolve(obj, x_definition, tolerance)
    y_point = anchor_definitions.resolve(obj, y_definition, tolerance)
    if origin is None or x_point is None or y_point is None:
        return None

    plane = Rhino.Geometry.Plane(origin, x_point, y_point)
    return plane if plane.IsValid else None


def _plane_from_circular_curve(curve, circle):
    x_axis = curve.PointAtStart - circle.Center
    if not x_axis.Unitize():
        return None
    normal = Rhino.Geometry.Vector3d(circle.Normal)
    if not normal.Unitize():
        return None
    y_axis = Rhino.Geometry.Vector3d.CrossProduct(normal, x_axis)
    if not y_axis.Unitize():
        return None

    plane = Rhino.Geometry.Plane(circle.Center, x_axis, y_axis)
    return plane if plane.IsValid else None


def _resolve_circular_edge_plane(doc, definition):
    obj = _definition_object(doc, definition)
    if obj is None:
        return None
    try:
        center_definition = definition["edge_center_anchor"]
    except Exception:
        return None

    resolved = anchor_definitions.circular_edge(
        obj,
        center_definition,
        max(doc.ModelAbsoluteTolerance, 1e-7),
    )
    if resolved is None:
        return None
    edge, circle = resolved
    return _plane_from_circular_curve(edge, circle)


def _resolve_circular_curve_plane(doc, definition):
    obj = _definition_object(doc, definition)
    if obj is None:
        return None
    try:
        center_definition = definition["curve_center_anchor"]
    except Exception:
        return None

    resolved = anchor_definitions.circular_curve(
        obj,
        center_definition,
        max(doc.ModelAbsoluteTolerance, 1e-7),
    )
    if resolved is None:
        return None
    curve, circle = resolved
    return _plane_from_circular_curve(curve, circle)


_DEFINITION_RESOLVERS = {
    "three_point_plane": _resolve_three_point_plane,
    "circular_edge_plane": _resolve_circular_edge_plane,
    "circular_curve_plane": _resolve_circular_curve_plane,
}


def resolve_definition(doc, definition):
    """Regenerate a plane using its type-specific resolver."""
    if not isinstance(definition, dict):
        return None
    resolver = _DEFINITION_RESOLVERS.get(definition.get("type"))
    return None if resolver is None else resolver(doc, definition)


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


def _grid_lines(
    origin,
    x_axis,
    y_axis,
    length,
    spacing,
    major_frequency,
):
    if x_axis is None or y_axis is None or spacing is None:
        return [], []

    frequency = max(1, int(major_frequency or DEFAULT_MAJOR_GRID_FREQUENCY))
    # Exclude offsets exactly on the border; the border has its own color.
    offset_count = max(0, int(math.ceil(length / spacing)) - 1)
    minor_lines = []
    major_lines = []
    for index in range(-offset_count, offset_count + 1):
        offset = index * spacing
        destination = major_lines if index % frequency == 0 else minor_lines
        destination.append(
            Rhino.Geometry.Line(
                origin + x_axis * offset - y_axis * length,
                origin + x_axis * offset + y_axis * length,
            )
        )
        destination.append(
            Rhino.Geometry.Line(
                origin + y_axis * offset - x_axis * length,
                origin + y_axis * offset + x_axis * length,
            )
        )
    return minor_lines, major_lines


def draw_preview(
    display,
    origin,
    x_axis,
    y_axis,
    length,
    grid_spacing=None,
    major_frequency=DEFAULT_MAJOR_GRID_FREQUENCY,
):
    if x_axis is None or y_axis is None:
        return

    appearance = Rhino.ApplicationSettings.AppearanceSettings
    display.DrawLine(
        origin,
        origin - x_axis * length,
        CROSSHAIR_COLOR,
        CROSSHAIR_THICKNESS,
    )
    display.DrawLine(
        origin,
        origin - y_axis * length,
        CROSSHAIR_COLOR,
        CROSSHAIR_THICKNESS,
    )

    plane = Rhino.Geometry.Plane(origin, x_axis, y_axis)
    display.DrawCircle(
        Rhino.Geometry.Circle(plane, preview_circle_radius()),
        CROSSHAIR_COLOR,
        CROSSHAIR_THICKNESS,
    )

    display.DrawLine(
        origin,
        origin + x_axis * length,
        appearance.GridXAxisLineColor,
        CROSSHAIR_THICKNESS,
    )
    display.DrawLine(
        origin,
        origin + y_axis * length,
        appearance.GridYAxisLineColor,
        CROSSHAIR_THICKNESS,
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
            self.state.get("major_grid_frequency"),
        )


def _active_major_grid_frequency(doc):
    view = doc.Views.ActiveView
    if view is None:
        return DEFAULT_MAJOR_GRID_FREQUENCY
    construction_plane = view.ActiveViewport.GetConstructionPlane()
    return max(1, int(construction_plane.ThickLineFrequency))


def _refresh(doc, state):
    plane = resolve_definition(doc, state["definition"])
    state["plane"] = plane
    state["axis_length"] = None
    state["grid_spacing"] = GRID_SPACING
    state["major_grid_frequency"] = _active_major_grid_frequency(doc)
    if plane is None:
        return False

    state["axis_length"] = preview_half_extent()
    return True


def _command_name(event):
    return (
        getattr(event, "CommandEnglishName", None)
        or getattr(event, "EnglishName", None)
        or getattr(event, "CommandName", None)
        or "completed"
    )


def _show_broken_plane_alert(command_name, state):
    definition = state.get("definition", {})
    message = (
        "The {} command broke the ability to define the analytic plane "
        "from its saved anchor metadata.\n\n"
        "Plane type: {}\n"
        "Object: {}\n\n"
        "The plane preview will remain hidden until the metadata can resolve "
        "again."
    ).format(
        command_name,
        definition.get("type", "<unknown>"),
        definition.get("object_id", "<unknown>"),
    )
    Rhino.UI.Dialogs.ShowMessage(
        message,
        "Analytic plane definition broken",
        Rhino.UI.ShowMessageButton.OK,
        Rhino.UI.ShowMessageIcon.Warning,
    )


def EndCommandHandler(sender, event):
    """Re-resolve the sticky plane after every completed Rhino command."""
    state = sc.sticky.get(STATE_KEY)
    if state is None:
        return
    doc = Rhino.RhinoDoc.ActiveDoc
    if doc is None or doc.RuntimeSerialNumber != state["document_serial"]:
        return

    was_resolvable = state.get("plane") is not None
    resolved = False
    try:
        resolved = _refresh(doc, state)
    except Exception:
        # A document edit can temporarily make topology unavailable. Keep the
        # command lifecycle healthy and hide the preview until it resolves.
        state["plane"] = None
        state["axis_length"] = None
        state["grid_spacing"] = None
        state["major_grid_frequency"] = None
    finally:
        doc.Views.Redraw()

    if was_resolvable and not resolved:
        try:
            _show_broken_plane_alert(_command_name(event), state)
        except Exception:
            pass


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
        "major_grid_frequency": None,
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
