import json

from tack import utils


LINK_KEY = "Tack.CoincidentLink.v1"
CHILD_KEY = "Tack.CoincidentChildId.v1"


def _set_user_value(doc, object_id, key, value):
    obj = doc.Objects.Find(object_id)
    if obj is None:
        return False
    attrs = obj.Attributes.Duplicate()
    attrs.UserDictionary.Set(key, value)
    return doc.Objects.ModifyAttributes(object_id, attrs, True)


def _point_data(point):
    return [point.X, point.Y, point.Z]


def write_link(doc, parent_id, child_id, parent_vertex,
               child_vertex, parent_point, child_point):
    link = {
        "version": 1,
        "parent_id": str(parent_id),
        "child_id": str(child_id),
        "parent_vertex": {
            "type": parent_vertex[0],
            "index": int(parent_vertex[1]),
            "point": _point_data(parent_point),
        },
        "child_vertex": {
            "type": child_vertex[0],
            "index": int(child_vertex[1]),
            "point": _point_data(child_point),
        },
        "offset": _point_data(child_point - parent_point),
    }
    if not _set_user_value(doc, child_id, LINK_KEY, json.dumps(link)):
        return False
    return _set_user_value(doc, parent_id, CHILD_KEY, str(child_id))


def read_link(obj):
    try:
        return json.loads(str(obj.Attributes.UserDictionary[LINK_KEY]))
    except Exception:
        return None


def update_link(doc, state, link, role, vertex_type, vertex_index, point):
    link["parent_id"] = str(state["parent_id"])
    link["child_id"] = str(state["child_id"])
    vertex = link[role + "_vertex"]
    vertex["type"] = vertex_type
    vertex["index"] = int(vertex_index)
    vertex["point"] = _point_data(point)
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
            "[Tack coincident] metadata update role={} index={} point={} child_saved={} parent_saved={}".format(
                role,
                vertex_index,
                utils.debug_point(point),
                child_saved,
                parent_saved,
            )
        )
    return True


def candidate_role(state, candidate):
    try:
        child_id = candidate.Attributes.UserDictionary[CHILD_KEY]
        if utils.same_id(child_id, state["child_id"]):
            return "parent"
    except Exception:
        pass
    link = read_link(candidate)
    if link is not None and utils.same_id(link.get("parent_id"), state["parent_id"]):
        return "child"
    return None


def candidates(doc, state):
    for candidate in doc.Objects:
        if candidate is not None and candidate_role(state, candidate) is not None:
            yield candidate
