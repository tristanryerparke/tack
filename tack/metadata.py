import json
import uuid

from tack import utils


LINKS_KEY = "Tack.AnchorLinks.v3"
PARENT_LINKS_KEY = "Tack.AnchorParentLinks.v3"
_ANCHOR_TYPES = ("BoundingBox", "BrepVertex", "PolylineVertex")


def _set_user_value(doc, object_id, key, value):
    obj = utils.find_object(doc, object_id)
    if obj is None:
        return False
    attrs = obj.Attributes.Duplicate()
    attrs.UserDictionary.Set(key, value)
    return doc.Objects.ModifyAttributes(obj.Id, attrs, True)


def _read_json_object(obj, key):
    if obj is None:
        return {}
    try:
        data = json.loads(str(obj.Attributes.UserDictionary[key]))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


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
    try:
        index = int(data["index"])
    except (KeyError, TypeError, ValueError):
        return None
    if index < 0:
        return None
    return {
        "anchor_type": anchor_type,
        "index": index,
    }


def _parse_link(data, expected_link_id=None):
    if not isinstance(data, dict) or data.get("version") != 3:
        return None
    link_id = str(data.get("link_id") or "")
    if not link_id or (
        expected_link_id is not None
        and not utils.same_id(link_id, expected_link_id)
    ):
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
        "version": 3,
        "link_id": link_id,
        "parent_id": str(data["parent_id"]),
        "child_id": str(data["child_id"]),
        "parent_anchor": parent_anchor,
        "child_anchor": child_anchor,
        "offset": offset,
    }


def read_links(obj):
    links = {}
    for link_id, data in _read_json_object(obj, LINKS_KEY).items():
        link = _parse_link(data, expected_link_id=link_id)
        if link is not None:
            links[link["link_id"]] = link
    return links


def read_link(obj, link_id):
    for saved_id, link in read_links(obj).items():
        if utils.same_id(saved_id, link_id):
            return link
    return None


def read_parent_links(obj):
    links = {}
    for link_id, child_id in _read_json_object(obj, PARENT_LINKS_KEY).items():
        if link_id and child_id:
            links[str(link_id)] = str(child_id)
    return links


def _write_child_link(doc, link):
    child = utils.find_object(doc, link["child_id"])
    if child is None:
        return False
    links = read_links(child)
    links[link["link_id"]] = link
    return _set_user_value(
        doc,
        link["child_id"],
        LINKS_KEY,
        json.dumps(links),
    )


def _write_parent_link(doc, link):
    parent = utils.find_object(doc, link["parent_id"])
    if parent is None:
        return False
    links = read_parent_links(parent)
    links[link["link_id"]] = str(link["child_id"])
    return _set_user_value(
        doc,
        link["parent_id"],
        PARENT_LINKS_KEY,
        json.dumps(links),
    )


def write_link(doc, parent_id, child_id, parent_anchor, child_anchor):
    parent_type, parent_index, parent_location = parent_anchor
    child_type, child_index, child_location = child_anchor
    link_id = str(uuid.uuid4())
    link = {
        "version": 3,
        "link_id": link_id,
        "parent_id": str(parent_id),
        "child_id": str(child_id),
        "parent_anchor": {
            "anchor_type": parent_type,
            "index": int(parent_index),
        },
        "child_anchor": {
            "anchor_type": child_type,
            "index": int(child_index),
        },
        "offset": _point_data(child_location - parent_location),
    }
    if not _write_child_link(doc, link):
        return None
    if not _write_parent_link(doc, link):
        return None
    return link_id


def all_links(doc):
    links = {}
    for obj in doc.Objects:
        if obj is None:
            continue
        for link_id, saved_link in read_links(obj).items():
            is_canonical = utils.same_id(obj.Id, saved_link["child_id"])
            if link_id not in links or is_canonical:
                links[link_id] = saved_link
    return list(links.values())


def save_link(doc, state, link):
    link["version"] = 3
    link["link_id"] = str(state["link_id"])
    link["parent_id"] = str(state["parent_id"])
    link["child_id"] = str(state["child_id"])
    state["link"] = link
    child_saved = _write_child_link(doc, link)
    parent_saved = _write_parent_link(doc, link)
    return child_saved and parent_saved


def update_anchor(
    doc,
    state,
    link,
    role,
    anchor_type,
    anchor_index,
    anchor_location,
):
    link["version"] = 3
    link["link_id"] = str(state["link_id"])
    link["parent_id"] = str(state["parent_id"])
    link["child_id"] = str(state["child_id"])
    anchor = link[role + "_anchor"]
    anchor["anchor_type"] = anchor_type
    anchor["index"] = int(anchor_index)
    state["link"] = link

    child_saved = _write_child_link(doc, link)
    parent_saved = _write_parent_link(doc, link)
    if utils.DEBUG:
        print(
            "[Tack anchor] metadata update link={} role={} anchor_type={} index={} point={} child_saved={} parent_saved={}".format(
                link["link_id"],
                role,
                anchor_type,
                anchor_index,
                utils.debug_point(anchor_location),
                child_saved,
                parent_saved,
            )
        )
    return child_saved and parent_saved


def candidate_role(state, candidate):
    if candidate is None:
        return None
    link_id = state["link_id"]
    if any(
        utils.same_id(saved_id, link_id)
        for saved_id in read_parent_links(candidate)
    ):
        return "parent"
    if any(
        utils.same_id(saved_id, link_id)
        for saved_id in read_links(candidate)
    ):
        return "child"
    return None


def candidates(doc, state):
    for candidate in doc.Objects:
        if candidate is not None and candidate_role(state, candidate) is not None:
            yield candidate
