import Rhino


ANCHOR_TYPE = "BoundingBox"
CENTER_INDEX = 8
_AXIS_BITS = (1, 2, 4)


def _bounding_box(obj):
    geometry = getattr(obj, "Geometry", obj)
    try:
        bounding_box = geometry.GetBoundingBox(True)
    except Exception:
        return None
    return bounding_box if bounding_box.IsValid else None


def anchors(obj):
    bounding_box = _bounding_box(obj)
    if bounding_box is None:
        return []

    minimum = bounding_box.Min
    maximum = bounding_box.Max
    extents = (
        maximum.X - minimum.X,
        maximum.Y - minimum.Y,
        maximum.Z - minimum.Z,
    )
    active_bits = [
        bit
        for bit, extent in zip(_AXIS_BITS, extents)
        if abs(extent) > Rhino.RhinoMath.ZeroTolerance
    ]
    if not active_bits:
        return [(CENTER_INDEX, Rhino.Geometry.Point3d(bounding_box.Center))]

    active_mask = sum(active_bits)
    candidate_anchors = []
    for index in range(CENTER_INDEX):
        if index & ~active_mask:
            continue
        candidate_anchors.append(
            (
                index,
                Rhino.Geometry.Point3d(
                    maximum.X if index & 1 else minimum.X,
                    maximum.Y if index & 2 else minimum.Y,
                    maximum.Z if index & 4 else minimum.Z,
                ),
            )
        )
    candidate_anchors.append(
        (CENTER_INDEX, Rhino.Geometry.Point3d(bounding_box.Center))
    )
    return candidate_anchors


def wire_segments(obj):
    corners = {
        index: point
        for index, point in anchors(obj)
        if index != CENTER_INDEX
    }
    segments = []
    for index, point in corners.items():
        for bit in _AXIS_BITS:
            other_index = index | bit
            if not index & bit and other_index in corners:
                segments.append((point, corners[other_index]))
    return segments


def resolve(obj, anchor):
    return dict(anchors(obj)).get(int(anchor["index"]))


def replacement_anchor(candidate, anchor, tolerance):
    candidate_anchors = anchors(candidate)
    index = int(anchor["index"])
    if index not in dict(candidate_anchors):
        index = None
    return candidate_anchors, index


def remap_anchor(old_obj, new_obj, anchor, tolerance):
    new_anchors = anchors(new_obj)
    index = int(anchor["index"])
    if index not in dict(new_anchors):
        index = None
    return new_anchors, index
