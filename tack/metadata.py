import json

from tack import utils


LINK_KEY = "Tack.AnchorLink.v2"
CHILD_KEY = "Tack.AnchorChildId.v2"
_ANCHOR_TYPES = ("BoundingBox", "BrepVertex")


def _set_user_value(doc, object_id, key, value):
    obj = doc.Objects.Find(object_id)
    if obj is None:
        return False
    attrs = obj.Attributes.Duplicate()
    attrs.UserDictionary.Set(key, value)
    return doc.Objects.ModifyAttributes(object_id, attrs, True)


def _point_data(point):
    return [point.X, point.Y, point.Z]


def _parse_point(data):
    if not isinstance(data, (list, tuple)) or len(data) != 3:
        return None
    try:
        return [float(value) for value in data]
    except (TypeError, ValueError):
        return None


def _parse_anchor(data):
    if not isinstance(data, dict):
        return None
    anchor_type = data.get("anchor_type")
    if anchor_type not in _ANCHOR_TYPES:
        return None
    point = _parse_point(data.get("point"))
    try:
        index = int(data["index"])
    except (KeyError, TypeError, ValueError):
        return None
    if point is None or index < 0:
        return None
    return {
        "anchor_type": anchor_type,
        "index": index,
        "point": point,
    }


def _parse_link(data):
    if not isinstance(data, dict) or data.get("version") != 2:
        return None
    parent_anchor = _parse_anchor(data.get("parent_anchor"))
    child_anchor = _parse_anchor(data.get("child_anchor"))
    offset = _parse_point(data.get("offset"))
    if (
        not data.get("parent_id")
        or not data.get("child_id")
        or parent_anchor is None
        or child_anchor is None
        or offset is None
    ):
        return None
    return {
        "version": 2,
        "parent_id": str(data["parent_id"]),
        "child_id": str(data["child_id"]),
        "parent_anchor": parent_anchor,
        "child_anchor": child_anchor,
        "offset": offset,
    }


def write_link(doc, parent_id, child_id, parent_anchor, child_anchor):
    parent_type, parent_index, parent_location = parent_anchor
    child_type, child_index, child_location = child_anchor
    link = {
        "version": 2,
        "parent_id": str(parent_id),
        "child_id": str(child_id),
        "parent_anchor": {
            "anchor_type": parent_type,
            "index": int(parent_index),
            "point": _point_data(parent_location),
        },
        "child_anchor": {
            "anchor_type": child_type,
            "index": int(child_index),
            "point": _point_data(child_location),
        },
        "offset": _point_data(child_location - parent_location),
    }
    if not _set_user_value(doc, child_id, LINK_KEY, json.dumps(link)):
        return False
    return _set_user_value(doc, parent_id, CHILD_KEY, str(child_id))


def read_link(obj):
    try:
        data = json.loads(str(obj.Attributes.UserDictionary[LINK_KEY]))
    except Exception:
        return None
    return _parse_link(data)


def read_child_id(obj):
    try:
        return str(obj.Attributes.UserDictionary[CHILD_KEY])
    except Exception:
        return None


def update_anchor(
    doc,
    state,
    link,
    role,
    anchor_type,
    anchor_index,
    anchor_location,
):
    link["version"] = 2
    link["parent_id"] = str(state["parent_id"])
    link["child_id"] = str(state["child_id"])
    anchor = link[role + "_anchor"]
    anchor["anchor_type"] = anchor_type
    anchor["index"] = int(anchor_index)
    anchor["point"] = _point_data(anchor_location)
    state["link"] = link

    child_saved = _set_user_value(
        doc,
        state["child_id"],
        LINK_KEY,
        json.dumps(link),
    )
    parent_saved = _set_user_value(
        doc,
        state["parent_id"],
        CHILD_KEY,
        str(state["child_id"]),
    )
    if utils.DEBUG:
        print(
            "[Tack anchor] metadata update role={} anchor_type={} index={} point={} child_saved={} parent_saved={}".format(
                role,
                anchor_type,
                anchor_index,
                utils.debug_point(anchor_location),
                child_saved,
                parent_saved,
            )
        )
    return child_saved and parent_saved


def update_child_anchor(doc, state, link, anchor_location):
    link["child_anchor"]["point"] = _point_data(anchor_location)
    state["link"] = link
    return _set_user_value(
        doc,
        state["child_id"],
        LINK_KEY,
        json.dumps(link),
    )


def candidate_role(state, candidate):
    child_id = read_child_id(candidate)
    if child_id is not None and utils.same_id(child_id, state["child_id"]):
        return "parent"
    link = read_link(candidate)
    if link is not None and utils.same_id(link.get("parent_id"), state["parent_id"]):
        return "child"
    return None


def candidates(doc, state):
    for candidate in doc.Objects:
        if candidate is not None and candidate_role(state, candidate) is not None:
            yield candidate
