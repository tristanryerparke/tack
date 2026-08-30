"""Interactive pickers for supported analytic plane definitions."""

import Rhino

from tack import anchor_definitions
from tack import three_point_plane
from tack.prompting.osnap_anchor_picker import AnchorPickSession


CIRCULAR_OPTION = "Circular"


def _dot(left, right):
    return left.X * right.X + left.Y * right.Y + left.Z * right.Z


def _unit(vector):
    result = Rhino.Geometry.Vector3d(vector)
    if not result.Unitize():
        return None
    return result


def _perpendicular(vector, axis):
    return _unit(vector - axis * _dot(vector, axis))


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
            self.preview.update(event.Point)
            Rhino.RhinoDoc.ActiveDoc.Views.Redraw()
        super(AxisPreviewGetPoint, self).OnMouseMove(event)

    def OnDynamicDraw(self, event):
        if self.preview is not None:
            self.preview.update(event.CurrentPoint)
        super(AxisPreviewGetPoint, self).OnDynamicDraw(event)


class AxisPreviewConduit(Rhino.Display.DisplayConduit):
    def __init__(self, getter):
        super(AxisPreviewConduit, self).__init__()
        self.getter = getter
        self.state = None

    def update(self, current):
        origin, x_axis, y_axis = self.getter.axes(current)
        self.state = (
            origin,
            x_axis,
            y_axis,
            three_point_plane.PLANE_HALF_EXTENT,
        )

    def CalculateBoundingBox(self, event):
        if self.state is None:
            return
        origin, x_axis, y_axis, half_extent = self.state
        points = [origin]
        points.extend(
            three_point_plane.plane_border(
                origin,
                x_axis,
                y_axis,
                half_extent,
            )
        )
        event.IncludeBoundingBox(Rhino.Geometry.BoundingBox(points))

    def DrawOverlay(self, event):
        if self.state is not None:
            three_point_plane.draw_preview(
                event.Display,
                *self.state,
                grid_spacing=three_point_plane.GRID_SPACING,
                major_frequency=(
                    event.Viewport.GetConstructionPlane().ThickLineFrequency
                ),
            )


def _live_circular_plane(candidates, point, tolerance):
    """Return the unambiguous plane at a live circular-center point.

    Trimmed arcs commonly share one circle center. They are not ambiguous for
    preview purposes when their analytic planes are coplanar; use the first
    such candidate. Different coplanarity still suppresses the preview.
    """
    matches = [
        candidate
        for candidate in candidates
        if candidate["point"].DistanceTo(point) <= tolerance
    ]
    if not matches:
        return None
    plane = matches[0]["plane"]
    return (
        plane
        if all(
            abs(plane.ZAxis * candidate["plane"].ZAxis) >= 1.0 - tolerance
            for candidate in matches[1:]
        )
        else None
    )


class CircularPreviewGetPoint(Rhino.Input.Custom.GetPoint):
    def __init__(self, candidates, tolerance):
        super(CircularPreviewGetPoint, self).__init__()
        self.candidates = candidates
        self.tolerance = tolerance
        self.preview = None

    def _update_preview(self, point):
        if self.preview is None:
            return
        self.preview.plane = _live_circular_plane(
            self.candidates,
            point,
            self.tolerance,
        )
    def OnMouseMove(self, event):
        self._update_preview(event.Point)
        Rhino.RhinoDoc.ActiveDoc.Views.Redraw()
        super(CircularPreviewGetPoint, self).OnMouseMove(event)

    def OnDynamicDraw(self, event):
        self._update_preview(event.CurrentPoint)
        super(CircularPreviewGetPoint, self).OnDynamicDraw(event)


class CircularPreviewConduit(Rhino.Display.DisplayConduit):
    def __init__(self, getter):
        super(CircularPreviewConduit, self).__init__()
        self.getter = getter
        self.plane = None

    def CalculateBoundingBox(self, event):
        if self.plane is None:
            return
        points = three_point_plane.plane_border(
            self.plane.Origin,
            self.plane.XAxis,
            self.plane.YAxis,
            three_point_plane.PLANE_HALF_EXTENT,
        )
        points.append(self.plane.Origin)
        event.IncludeBoundingBox(Rhino.Geometry.BoundingBox(points))

    def DrawOverlay(self, event):
        if self.plane is None:
            return
        three_point_plane.draw_preview(
            event.Display,
            self.plane.Origin,
            self.plane.XAxis,
            self.plane.YAxis,
            three_point_plane.PLANE_HALF_EXTENT,
            grid_spacing=three_point_plane.GRID_SPACING,
            major_frequency=(
                event.Viewport.GetConstructionPlane().ThickLineFrequency
            ),
        )


def _circular_plane_candidates(doc, obj):
    tolerance = max(doc.ModelAbsoluteTolerance, 1e-7)
    result = []
    for feature_type in (
        anchor_definitions.CIRCULAR_EDGE_CENTER,
        anchor_definitions.CURVE_CENTER,
    ):
        for anchor, center in anchor_definitions.candidates(
            obj,
            feature_type,
            tolerance,
        ):
            if feature_type == anchor_definitions.CIRCULAR_EDGE_CENTER:
                definition = {
                    "type": "circular_edge_plane",
                    "object_id": str(obj.Id),
                    "edge_center_anchor": anchor,
                }
            else:
                definition = {
                    "type": "circular_curve_plane",
                    "object_id": str(obj.Id),
                    "curve_center_anchor": anchor,
                }
            plane = three_point_plane.resolve_definition(doc, definition)
            if plane is not None:
                result.append(
                    {
                        "point": center,
                        "plane": plane,
                        "definition": definition,
                    }
                )
    return result


def _getter_factory(construction_plane, origin=None, x_point=None):
    return lambda: AxisPreviewGetPoint(construction_plane, origin, x_point)


def _preview_factory(getter):
    conduit = AxisPreviewConduit(getter)
    getter.preview = conduit
    return conduit


def _circular_preview_factory(getter):
    conduit = CircularPreviewConduit(getter)
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
        if Rhino.Geometry.Plane(origin, x_point, point).IsValid:
            return point, definition
        print("The Y-axis anchor must not resolve onto the X axis.")


def _is_circular_center(definition):
    return definition.get("type") in (
        anchor_definitions.CIRCULAR_EDGE_CENTER,
        anchor_definitions.CURVE_CENTER,
    )


def pick_circular_plane(doc, obj):
    """Pick one circular edge/curve center and return its analytic plane data."""
    candidates = _circular_plane_candidates(doc, obj)
    if not candidates:
        print("The selected object has no resolvable circular center planes.")
        return None
    tolerance = max(doc.ModelAbsoluteTolerance, 1e-7)

    with AnchorPickSession(
        doc,
        obj,
        include_bounding_box_center=False,
    ) as session:
        picked = session.pick(
            "Center-snap to a circular Brep edge or circular curve",
            getter_factory=lambda: CircularPreviewGetPoint(candidates, tolerance),
            preview_factory=_circular_preview_factory,
            definition_filter=_is_circular_center,
            rejected_message=(
                "Only a center snap on a circular Brep edge or circular curve "
                "is accepted."
            ),
        )
    if picked is None:
        return None

    center, center_anchor = picked
    if center_anchor["type"] == anchor_definitions.CIRCULAR_EDGE_CENTER:
        definition = {
            "type": "circular_edge_plane",
            "object_id": str(obj.Id),
            "edge_center_anchor": center_anchor,
        }
        role = "edge_center"
    else:
        definition = {
            "type": "circular_curve_plane",
            "object_id": str(obj.Id),
            "curve_center_anchor": center_anchor,
        }
        role = "curve_center"

    return {
        "mode": "circular",
        "definition": definition,
        "picks": [
            {
                "role": role,
                "point": center,
                "anchor": center_anchor,
            }
        ],
    }


def pick_three_point_plane(doc, obj, construction_plane, allow_circular=False):
    """Pick a three-point plane, optionally exposing a Circular button."""
    circular_requested = False
    with AnchorPickSession(doc, obj) as session:
        origin_result = session.pick(
            "Pick an analytic anchor for the plane origin",
            getter_factory=_getter_factory(construction_plane),
            preview_factory=_preview_factory,
            options=(CIRCULAR_OPTION,) if allow_circular else (),
        )
        if isinstance(origin_result, dict):
            circular_requested = origin_result.get("option") == CIRCULAR_OPTION
        elif origin_result is None:
            return None
        else:
            origin, origin_definition = origin_result
            x_result = _pick_nonzero_x(session, construction_plane, origin)
            if x_result is None:
                return None
            x_point, x_definition = x_result

            y_result = _pick_valid_y(
                session,
                construction_plane,
                origin,
                x_point,
            )
            if y_result is None:
                return None
            y_point, y_definition = y_result

            return {
                "mode": "three_point",
                "definition": {
                    "type": "three_point_plane",
                    "object_id": str(obj.Id),
                    "origin_anchor": origin_definition,
                    "x_axis_anchor": x_definition,
                    "y_axis_anchor": y_definition,
                },
                "picks": [
                    {
                        "role": "origin",
                        "point": origin,
                        "anchor": origin_definition,
                    },
                    {
                        "role": "x_axis",
                        "point": x_point,
                        "anchor": x_definition,
                    },
                    {
                        "role": "y_axis",
                        "point": y_point,
                        "anchor": y_definition,
                    },
                ],
            }

    if circular_requested:
        return pick_circular_plane(doc, obj)
    return None


def pick_plane(doc, obj, construction_plane):
    """Default to three-point picking with a Circular command-line button."""
    return pick_three_point_plane(
        doc,
        obj,
        construction_plane,
        allow_circular=True,
    )
