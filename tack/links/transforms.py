"""Plane and object transform calculations shared by Tack runtime and previews."""

import Rhino

from tack.core.objects import find_object

_TRANSFORM_FIELDS = (
    "M00",
    "M01",
    "M02",
    "M03",
    "M10",
    "M11",
    "M12",
    "M13",
    "M20",
    "M21",
    "M22",
    "M23",
    "M30",
    "M31",
    "M32",
    "M33",
)


def identity_transform_data():
    return [
        1.0,
        0.0,
        0.0,
        0.0,
        0.0,
        1.0,
        0.0,
        0.0,
        0.0,
        0.0,
        1.0,
        0.0,
        0.0,
        0.0,
        0.0,
        1.0,
    ]


def plane_to_plane_transform(parent_plane, child_plane):
    return Rhino.Geometry.Transform.PlaneToPlane(child_plane, parent_plane)


def constrained_target_child_plane(
    target_plane,
    child_plane,
    translation=True,
    rotation=True,
):
    """Keep the child components excluded by a Tack's degrees of freedom."""
    origin = target_plane.Origin if translation else child_plane.Origin
    x_axis = target_plane.XAxis if rotation else child_plane.XAxis
    y_axis = target_plane.YAxis if rotation else child_plane.YAxis
    return Rhino.Geometry.Plane(origin, x_axis, y_axis)


def constrained_plane_transform(
    parent_plane,
    child_plane,
    translation=True,
    rotation=True,
):
    target_plane = constrained_target_child_plane(
        parent_plane,
        child_plane,
        translation,
        rotation,
    )
    return Rhino.Geometry.Transform.PlaneToPlane(child_plane, target_plane)


def transform_object_in_place(doc, obj, transform):
    if obj is None or obj.Geometry is None:
        return None
    object_id = obj.Id
    attributes = obj.Attributes.Duplicate()
    geometry = obj.Geometry.Duplicate()
    if geometry is None or not geometry.Transform(transform):
        return None
    if not doc.Objects.Replace(object_id, geometry, True):
        return None
    if not doc.Objects.ModifyAttributes(object_id, attributes, True):
        return None
    return find_object(doc, object_id)


def inherit_transform_data(parent_plane, child_plane):
    """Encode the child plane in the parent plane's local coordinates."""
    relative_child = Rhino.Geometry.Plane(child_plane)
    relative_child.Transform(
        Rhino.Geometry.Transform.PlaneToPlane(
            parent_plane,
            Rhino.Geometry.Plane.WorldXY,
        )
    )
    transform = Rhino.Geometry.Transform.PlaneToPlane(
        Rhino.Geometry.Plane.WorldXY,
        relative_child,
    )
    return [float(getattr(transform, field)) for field in _TRANSFORM_FIELDS]


def inherit_target_child_plane(parent_plane, transform_data):
    """Resolve an inherited child plane from its parent-local transform."""
    transform = Rhino.Geometry.Transform.Identity
    try:
        for field, value in zip(_TRANSFORM_FIELDS, transform_data):
            setattr(transform, field, float(value))
    except (TypeError, ValueError):
        return None
    relative_child = Rhino.Geometry.Plane(Rhino.Geometry.Plane.WorldXY)
    if not relative_child.Transform(transform):
        return None
    if not relative_child.Transform(
        Rhino.Geometry.Transform.PlaneToPlane(
            Rhino.Geometry.Plane.WorldXY,
            parent_plane,
        )
    ):
        return None
    return relative_child if relative_child.IsValid else None


def planes_match(parent_plane, child_plane, tolerance):
    return (
        parent_plane.Origin.DistanceTo(child_plane.Origin) <= tolerance
        and parent_plane.XAxis * child_plane.XAxis >= 1.0 - tolerance
        and parent_plane.YAxis * child_plane.YAxis >= 1.0 - tolerance
    )


def transform_data_matches(left, right, tolerance=1e-9):
    if len(left) != len(right):
        return False
    return all(
        abs(left_value - right_value)
        <= tolerance * max(1.0, abs(left_value), abs(right_value))
        for left_value, right_value in zip(left, right)
    )
