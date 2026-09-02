"""Interactive pickers for supported analytic plane definitions."""

import Rhino

from tack import anchor_definitions
from tack import analytic_plane
from tack.prompting.osnap_anchor_picker import AnchorPickSession


CIRCULAR_OPTION = "Circular"
THREE_POINT_OPTION = "3Point"


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

    def preview_plane(self, current):
        origin, x_axis, y_axis = self.axes(current)
        plane = Rhino.Geometry.Plane(origin, x_axis, y_axis)
        return plane if plane.IsValid else None

    def OnDynamicDraw(self, event):
        analytic_plane.draw_preview(
            event.Display,
            self.preview_plane(event.CurrentPoint),
        )
        super(AxisPreviewGetPoint, self).OnDynamicDraw(event)


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

    def OnDynamicDraw(self, event):
        analytic_plane.draw_preview(
            event.Display,
            _live_circular_plane(
                self.candidates,
                event.CurrentPoint,
                self.tolerance,
            ),
        )
        super(CircularPreviewGetPoint, self).OnDynamicDraw(event)


class SmartOriginPreviewGetPoint(AxisPreviewGetPoint):
    """Use a circular plane at a center, otherwise use CPlane-style axes."""

    def __init__(self, construction_plane, candidates, tolerance):
        super(SmartOriginPreviewGetPoint, self).__init__(construction_plane)
        self.candidates = candidates
        self.tolerance = tolerance

    def preview_plane(self, current):
        return _live_circular_plane(
            self.candidates,
            current,
            self.tolerance,
        ) or super(SmartOriginPreviewGetPoint, self).preview_plane(current)


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
            plane = analytic_plane.resolve_definition(doc, definition)
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


def _pick_nonzero_x(session, construction_plane, origin):
    while True:
        picked = session.pick(
            "Pick an analytic anchor for the X axis",
            getter_factory=_getter_factory(construction_plane, origin),
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
            definition_filter=_is_circular_center,
            rejected_message=(
                "Only a center snap on a circular Brep edge or circular curve "
                "is accepted."
            ),
        )
    if picked is None:
        return None

    center, center_anchor = picked
    return _circular_result(obj, center, center_anchor)


def _circular_result(obj, center, center_anchor):
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


def _circular_result_at_live_center(doc, obj, candidates, point, tolerance):
    plane = _live_circular_plane(candidates, point, tolerance)
    if plane is None:
        return None
    candidate = next(
        candidate
        for candidate in candidates
        if candidate["point"].DistanceTo(point) <= tolerance
        and candidate["plane"] is plane
    )
    definition = candidate["definition"]
    if definition["type"] == "circular_edge_plane":
        anchor = definition["edge_center_anchor"]
    else:
        anchor = definition["curve_center_anchor"]
    return _circular_result(obj, candidate["point"], anchor)


def pick_three_point_plane(doc, obj, construction_plane, allow_circular=False):
    """Pick a three-point plane, optionally exposing a Circular button."""
    circular_requested = False
    with AnchorPickSession(doc, obj) as session:
        origin_result = session.pick(
            "Pick an analytic anchor for the plane origin",
            getter_factory=_getter_factory(construction_plane),
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
    """Pick a one-click circular plane or reconcile a three-point plane."""
    tolerance = max(doc.ModelAbsoluteTolerance, 1e-7)
    candidates = _circular_plane_candidates(doc, obj)
    with AnchorPickSession(doc, obj) as session:
        origin_result = session.pick(
            "Pick an analytic plane origin or choose 3Point",
            getter_factory=(
                (
                    lambda: SmartOriginPreviewGetPoint(
                        construction_plane,
                        candidates,
                        tolerance,
                    )
                )
                if candidates
                else _getter_factory(construction_plane)
            ),
            options=(THREE_POINT_OPTION,),
        )
        force_three_point = isinstance(origin_result, dict)
        if origin_result is None:
            return None
        if force_three_point:
            origin_result = session.pick(
                "3Point mode: pick an analytic anchor for the plane origin",
                getter_factory=_getter_factory(construction_plane),
            )
            if origin_result is None:
                return None

        origin, origin_definition = origin_result
        if not force_three_point:
            if _is_circular_center(origin_definition):
                return _circular_result(obj, origin, origin_definition)
            # A circular center can coincide with the synthetic bounding-box
            # center, which AnchorPickSession resolves before PointOnObject.
            circular_result = _circular_result_at_live_center(
                doc,
                obj,
                candidates,
                origin,
                tolerance,
            )
            if circular_result is not None:
                return circular_result

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
