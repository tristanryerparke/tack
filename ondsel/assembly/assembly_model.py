import json
import math
import traceback
import uuid

import Rhino
import scriptcontext as sc

from ondsel.assembly import assembly_common
from ondsel.assembly import assembly_scheduler


LOG_PATH = "/tmp/ondsel_handler.log"
WATCHER_CONNECTION_KEY = "Ondsel.Assembly.WatcherConnection.v1"


def get_watcher_connection():
    """Return a sticky-stored watcher connection, creating it on first use.

    Handlers reuse this single socket so their feedback streams to the
    server for the lifetime of the watcher that subscribed them.
    """
    connection = sc.sticky.get(WATCHER_CONNECTION_KEY)
    if connection is not None:
        return connection
    try:
        from run_in_rhino.rhino_env.client import SocketConnection

        connection = SocketConnection()
    except Exception:
        return None
    sc.sticky[WATCHER_CONNECTION_KEY] = connection
    return connection


def drop_watcher_connection():
    """Close the persistent watcher socket before removing its sticky value."""
    connection = sc.sticky.pop(WATCHER_CONNECTION_KEY, None)
    websocket = getattr(connection, "ws", None)
    if websocket is not None:
        try:
            websocket.close()
        except Exception:
            pass
        socket = getattr(websocket, "sock", None)
        if socket is not None:
            try:
                socket.close()
            except Exception:
                pass


def _send_terminal(text):
    connection = get_watcher_connection()
    if connection is None:
        return
    try:
        connection.send_terminal(text)
    except Exception:
        drop_watcher_connection()


def _log_line(text):
    try:
        with open(LOG_PATH, "a") as log:
            log.write(text.rstrip("\n") + "\n")
    except Exception:
        pass


def _debug(message):
    text = "[Ondsel assembly] " + str(message)
    print(text)
    _log_line(text)
    _send_terminal(text)

DATA_KEY = "Ondsel.Assembly.v1"
RUNTIME_KEY = "Ondsel.Assembly.Runtime.v1"
HANDLER_KEY = "Ondsel.Assembly.Handlers.v1"
SOLVING_KEY = "Ondsel.Assembly.Solving.v1"
COMMAND_BUSY_KEY = "Ondsel.Assembly.CommandBusy.v1"
SETTLED_POSES_KEY = "settled_poses"
DRIVER_PART_KEY = "driver_part_id"


def _doc_key(doc):
    return int(doc.RuntimeSerialNumber)


def _runtime_registry(create=False):
    if create:
        return sc.sticky.setdefault(RUNTIME_KEY, {})
    return sc.sticky.get(RUNTIME_KEY, {})


def _runtime(doc, create=False):
    registry = _runtime_registry(create)
    if doc is None:
        return None
    key = _doc_key(doc)
    if create:
        return registry.setdefault(key, {})
    return registry.get(key, {})


def _set_solving(doc, value):
    state = _runtime(doc, True)
    state[SOLVING_KEY] = bool(value)


def is_solving(doc):
    return bool(_runtime(doc).get(SOLVING_KEY))


def _set_command_busy(doc, value):
    state = _runtime(doc, True)
    state[COMMAND_BUSY_KEY] = bool(value)


def is_command_busy(doc):
    return bool(_runtime(doc).get(COMMAND_BUSY_KEY))


def _set_driver_part_id(doc, object_id):
    state = _runtime(doc, True)
    state[DRIVER_PART_KEY] = assembly_common.guid_string(object_id) if object_id is not None else None


def _pop_driver_part_id(doc):
    state = _runtime(doc, True)
    return state.pop(DRIVER_PART_KEY, None)


def _store_serials(doc, part_ids):
    state = _runtime(doc, True)
    serials = {}
    for object_id in part_ids:
        obj = doc.Objects.FindId(assembly_common.parse_guid(object_id))
        serials[assembly_common.guid_string(object_id)] = assembly_common.object_runtime_serial(obj)
    state["serials"] = serials


def changed_part_ids(doc):
    state = _runtime(doc, True)
    serials = state.setdefault("serials", {})
    changed = []
    for object_id, previous in list(serials.items()):
        obj = doc.Objects.FindId(assembly_common.parse_guid(object_id))
        current = assembly_common.object_runtime_serial(obj)
        if current != previous:
            changed.append(object_id)
            serials[object_id] = current
    return changed


def dynamically_transformed_part_ids(doc, data):
    changed = []
    for object_id in data["parts"]:
        rhino_object = doc.Objects.FindId(assembly_common.parse_guid(object_id))
        if _dynamic_transform(rhino_object, debug=True) is not None:
            changed.append(object_id)
    return changed


def _copy_pose(pose):
    return {
        "position": list(pose["position"]),
        "quaternion": list(pose["quaternion"]),
    }


def _store_settled_poses(doc, data, poses):
    state = _runtime(doc, True)
    stored = {}
    for object_id in data["parts"].keys():
        pose = poses.get(object_id)
        if pose is not None:
            stored[assembly_common.guid_string(object_id)] = _copy_pose(pose)
    state[SETTLED_POSES_KEY] = stored


def _settled_pose(doc, object_id):
    return _runtime(doc).get(SETTLED_POSES_KEY, {}).get(assembly_common.guid_string(object_id))


def _quaternion_distance(quaternion_a, quaternion_b):
    same = sum((a - b) * (a - b) for a, b in zip(quaternion_a, quaternion_b)) ** 0.5
    flipped = sum((a + b) * (a + b) for a, b in zip(quaternion_a, quaternion_b)) ** 0.5
    return min(same, flipped)


def _pose_motion_metric(previous_pose, current_pose):
    translation = Rhino.Geometry.Point3d(*previous_pose["position"]).DistanceTo(
        Rhino.Geometry.Point3d(*current_pose["position"])
    )
    rotation = _quaternion_distance(previous_pose["quaternion"], current_pose["quaternion"])
    return translation + rotation


def _choose_driver_part_id(doc, data, changed_object_ids):
    if not changed_object_ids:
        return None
    if len(changed_object_ids) == 1:
        return changed_object_ids[0]
    best_id = changed_object_ids[0]
    best_metric = -1.0
    for object_id in changed_object_ids:
        part = data["parts"].get(assembly_common.guid_string(object_id))
        if part is None:
            continue
        current_pose = _current_pose_from_home(doc, part)
        previous_pose = _settled_pose(doc, object_id) or current_pose
        metric = _pose_motion_metric(previous_pose, current_pose)
        if metric > best_metric:
            best_id = object_id
            best_metric = metric
    return best_id


def _default_data():
    return {
        "version": 1,
        "parts": {},
        "constraints": [],
    }


def read_data(doc):
    try:
        raw = doc.Strings.GetValue(DATA_KEY)
        if not raw:
            return _default_data()
        data = json.loads(str(raw))
        if not isinstance(data, dict) or data.get("version") != 1:
            return _default_data()
        data.setdefault("parts", {})
        data.setdefault("constraints", [])
        return data
    except Exception:
        return _default_data()


def write_data(doc, data):
    doc.Strings.SetString(DATA_KEY, json.dumps(data, separators=(",", ":")))
    return data


def clear(doc):
    doc.Strings.Delete(DATA_KEY)
    _runtime_registry(True).pop(_doc_key(doc), None)


def _new_part_name(data):
    return "part_{}".format(len(data["parts"]))


def _part_meta(data, object_id):
    return data["parts"].get(assembly_common.guid_string(object_id))


def _edge_plane(doc, object_id, edge_index):
    obj = doc.Objects.FindId(assembly_common.parse_guid(object_id))
    if obj is None:
        return None
    brep = obj.Geometry if isinstance(obj.Geometry, Rhino.Geometry.Brep) else obj.Geometry.ToBrep()
    if brep is None or edge_index < 0 or edge_index >= brep.Edges.Count:
        return None
    circle = assembly_common.circle_from_edge(brep.Edges[edge_index], doc.ModelAbsoluteTolerance)
    if circle is None:
        return None
    return circle.Plane


def _face_plane(doc, object_id, face_index):
    obj = doc.Objects.FindId(assembly_common.parse_guid(object_id))
    if obj is None or obj.Geometry is None:
        return None
    geometry = obj.Geometry
    brep = geometry if isinstance(geometry, Rhino.Geometry.Brep) else geometry.ToBrep()
    if brep is None or face_index < 0 or face_index >= brep.Faces.Count:
        return None
    return assembly_common.plane_from_brep_face(
        brep.Faces[face_index],
        doc.ModelAbsoluteTolerance,
    )


def _pose_to_plane(pose):
    return assembly_common.plane_from_pose(pose["position"], pose["quaternion"])


def _plane_to_pose(plane):
    position, quaternion = assembly_common.pose_from_plane(plane)
    return {"position": list(position), "quaternion": list(quaternion)}


def _identity_pose():
    return {"position": [0.0, 0.0, 0.0], "quaternion": [1.0, 0.0, 0.0, 0.0]}


def _dynamic_transform(rhino_object, debug=False):
    object_id = "<none>" if rhino_object is None else str(rhino_object.Id)[:8]
    if rhino_object is None:
        if debug:
            _debug("GetDynamicTransform object={} available=False".format(object_id))
        return None
    try:
        result = rhino_object.GetDynamicTransform()
        available = bool(result[0])
        transform = result[1]
    except Exception as error:
        if debug:
            _debug("GetDynamicTransform object={} error={}".format(object_id, error))
        return None
    identity = transform is None or transform.IsIdentity
    if debug:
        _debug(
            "GetDynamicTransform object={} available={} identity={}".format(
                object_id,
                available,
                identity,
            )
        )
    if not available or identity:
        return None
    return transform


def _object_home_pose(doc, object_id):
    obj = doc.Objects.FindId(assembly_common.parse_guid(object_id))
    if obj is None or obj.Geometry is None:
        return _identity_pose()
    bbox = obj.Geometry.GetBoundingBox(True)
    if bbox is None or not bbox.IsValid:
        return _identity_pose()
    return _plane_to_pose(
        Rhino.Geometry.Plane(
            bbox.Center,
            Rhino.Geometry.Vector3d.XAxis,
            Rhino.Geometry.Vector3d.YAxis,
        )
    )


def _current_pose_from_home(doc, part_meta, include_dynamic=True):
    """Current part pose, optionally including Rhino's live dynamic transform."""
    home = part_meta.get("home")
    if home is None:
        pose = _identity_pose()
    else:
        edge_index = home.get("edge_index")
        face_index = home.get("face_index")
        if edge_index is not None:
            live_plane = _edge_plane(doc, part_meta["object_id"], edge_index)
            pose = home.get("pose", _identity_pose()) if live_plane is None else _plane_to_pose(live_plane)
        elif face_index is not None:
            live_plane = _face_plane(doc, part_meta["object_id"], face_index)
            pose = home.get("pose", _identity_pose()) if live_plane is None else _plane_to_pose(live_plane)
        else:
            pose = home.get("pose", _identity_pose())

    rhino_object = doc.Objects.FindId(assembly_common.parse_guid(part_meta["object_id"]))
    dynamic_transform = _dynamic_transform(rhino_object) if include_dynamic else None
    if dynamic_transform is None:
        return pose
    plane = _pose_to_plane(pose)
    plane.Transform(dynamic_transform)
    return _plane_to_pose(plane)


def _register_part_from_edge(doc, data, object_id, edge_index):
    key = assembly_common.guid_string(object_id)
    part = data["parts"].get(key)
    if part is None:
        part = {
            "object_id": key,
            "name": _new_part_name(data),
        }
        data["parts"][key] = part
    if part.get("home") is None:
        plane = _edge_plane(doc, object_id, edge_index)
        if plane is not None:
            part["home"] = {
                "edge_index": int(edge_index),
                "pose": _plane_to_pose(plane),
            }
    return part


def _register_part_from_face(doc, data, object_id, face_index):
    key = assembly_common.guid_string(object_id)
    part = data["parts"].get(key)
    if part is None:
        part = {
            "object_id": key,
            "name": _new_part_name(data),
        }
        data["parts"][key] = part
    if part.get("home") is None:
        plane = _face_plane(doc, object_id, face_index)
        if plane is not None:
            part["home"] = {
                "face_index": int(face_index),
                "pose": _plane_to_pose(plane),
            }
    return part


def _ensure_part(doc, data, object_id):
    key = assembly_common.guid_string(object_id)
    part = data["parts"].get(key)
    if part is None:
        part = {
            "object_id": key,
            "name": _new_part_name(data),
        }
        data["parts"][key] = part
    return part


def _local_pose_from_world_plane(doc, part_meta, world_plane, include_dynamic=True):
    current_pose = _current_pose_from_home(doc, part_meta, include_dynamic=include_dynamic)
    current_plane = _pose_to_plane(current_pose)
    to_local = assembly_common.transform_between_planes(current_plane, Rhino.Geometry.Plane.WorldXY)
    local_plane = assembly_common.transformed_plane(world_plane, to_local)
    return _plane_to_pose(local_plane)


def _local_marker_pose(doc, part_meta, edge_index):
    edge_plane = _edge_plane(doc, part_meta["object_id"], edge_index)
    if edge_plane is None:
        return None
    return _local_pose_from_world_plane(
        doc,
        part_meta,
        edge_plane,
        include_dynamic=False,
    )


def _local_face_marker_pose(doc, part_meta, face_index):
    face_plane = _face_plane(doc, part_meta["object_id"], face_index)
    if face_plane is None:
        return None
    return _local_pose_from_world_plane(
        doc,
        part_meta,
        face_plane,
        include_dynamic=False,
    )


def add_revolute(doc, side_a, side_b):
    data = read_data(doc)
    part_a = _register_part_from_edge(doc, data, side_a["object_id"], side_a["edge_index"])
    part_b = _register_part_from_edge(doc, data, side_b["object_id"], side_b["edge_index"])
    marker_a = _local_marker_pose(doc, part_a, side_a["edge_index"])
    marker_b = _local_marker_pose(doc, part_b, side_b["edge_index"])
    if marker_a is None or marker_b is None:
        return None
    constraint = {
        "id": str(uuid.uuid4()),
        "type": "revolute",
        "a": {
            "part": part_a["object_id"],
            "edge_index": int(side_a["edge_index"]),
        },
        "b": {
            "part": part_b["object_id"],
            "edge_index": int(side_b["edge_index"]),
        },
    }
    data["constraints"].append(constraint)
    write_data(doc, data)
    _store_serials(doc, data["parts"].keys())
    _store_settled_poses(doc, data, {part["object_id"]: _current_pose_from_home(doc, part) for part in data["parts"].values()})
    return constraint


def add_planar_offset(doc, side_a, side_b, offset):
    """Persist a planar face joint and fix its first part in world space."""
    data = read_data(doc)
    part_a = _register_part_from_face(doc, data, side_a["object_id"], side_a["face_index"])
    part_b = _register_part_from_face(doc, data, side_b["object_id"], side_b["face_index"])
    marker_a = _local_face_marker_pose(doc, part_a, side_a["face_index"])
    marker_b = _local_face_marker_pose(doc, part_b, side_b["face_index"])
    if marker_a is None or marker_b is None:
        return None

    selected_parts = {part_a["object_id"], part_b["object_id"]}
    data["constraints"] = [
        constraint
        for constraint in data["constraints"]
        if not (
            constraint.get("type") == "world_anchor"
            and constraint.get("part") in selected_parts
        )
        and not (
            constraint.get("type") == "planar_offset"
            and {
                constraint.get("a", {}).get("part"),
                constraint.get("b", {}).get("part"),
            }
            == selected_parts
        )
    ]
    data["constraints"].append(
        {
            "id": str(uuid.uuid4()),
            "type": "world_anchor",
            "part": part_a["object_id"],
            "world_pose": _current_pose_from_home(doc, part_a),
            "marker": _identity_pose(),
        }
    )
    constraint = {
        "id": str(uuid.uuid4()),
        "type": "planar_offset",
        "offset": float(offset),
        "a": {
            "part": part_a["object_id"],
            "face_index": int(side_a["face_index"]),
        },
        "b": {
            "part": part_b["object_id"],
            "face_index": int(side_b["face_index"]),
        },
    }
    data["constraints"].append(constraint)
    write_data(doc, data)
    _store_serials(doc, data["parts"].keys())
    _store_settled_poses(
        doc,
        data,
        {
            part["object_id"]: _current_pose_from_home(doc, part)
            for part in data["parts"].values()
        },
    )
    return constraint


def add_world_anchor(doc, rhino_object):
    data = read_data(doc)
    part = _ensure_part(doc, data, rhino_object.Id)
    if part.get("home") is None:
        part["home"] = {
            "pose": _object_home_pose(doc, part["object_id"]),
        }
    current_pose = _current_pose_from_home(doc, part)
    data["constraints"] = [
        c for c in data["constraints"]
        if not (c.get("type") == "world_anchor" and c.get("part") == part["object_id"])
    ]
    data["constraints"].append(
        {
            "id": str(uuid.uuid4()),
            "type": "world_anchor",
            "part": part["object_id"],
            "world_pose": current_pose,
            "marker": {
                "position": [0.0, 0.0, 0.0],
                "quaternion": [1.0, 0.0, 0.0, 0.0],
            },
        }
    )
    write_data(doc, data)
    _store_serials(doc, data["parts"].keys())
    _store_settled_poses(doc, data, {item["object_id"]: _current_pose_from_home(doc, item) for item in data["parts"].values()})
    return part


def add_slider_axis(doc, rhino_object, part_axis_origin, part_axis_direction, world_axis_origin, world_axis_direction):
    data = read_data(doc)
    part = _ensure_part(doc, data, rhino_object.Id)
    if part.get("home") is None:
        part["home"] = {
            "pose": _object_home_pose(doc, part["object_id"]),
        }
    part_axis_plane = assembly_common.plane_from_axis(part_axis_origin, part_axis_direction)
    marker = _local_pose_from_world_plane(doc, part, part_axis_plane)
    if marker is None:
        return None
    data["constraints"] = [
        c for c in data["constraints"]
        if not (c.get("type") == "slider_axis" and c.get("part") == part["object_id"])
    ]
    data["constraints"].append(
        {
            "id": str(uuid.uuid4()),
            "type": "slider_axis",
            "part": part["object_id"],
            "marker": marker,
            "world_axis_origin": list(assembly_common.point_tuple(world_axis_origin)),
            "world_axis_direction": list(assembly_common.vector_tuple(world_axis_direction)),
        }
    )
    write_data(doc, data)
    _store_serials(doc, data["parts"].keys())
    _store_settled_poses(doc, data, {item["object_id"]: _current_pose_from_home(doc, item) for item in data["parts"].values()})
    return part


def _pose_of_part_for_solver(doc, data, part_meta, initial_pose=None):
    current_pose = (
        _copy_pose(initial_pose)
        if initial_pose is not None
        else _current_pose_from_home(doc, part_meta, include_dynamic=False)
    )
    return current_pose, _copy_pose(current_pose)


def _compose_pose(part_pose, local_marker_pose):
    part_plane = _pose_to_plane(part_pose)
    local_plane = _pose_to_plane(local_marker_pose)
    world_plane = assembly_common.transformed_plane(local_plane, assembly_common.transform_between_planes(Rhino.Geometry.Plane.WorldXY, part_plane))
    return _plane_to_pose(world_plane)


def _pose_delta(current_pose, solved_pose):
    current_plane = _pose_to_plane(current_pose)
    solved_plane = _pose_to_plane(solved_pose)
    return assembly_common.transform_between_planes(current_plane, solved_plane)


def _is_identity_pose(pose, tolerance=1e-8):
    position = pose["position"]
    quaternion = pose["quaternion"]
    return (
        abs(position[0]) < tolerance
        and abs(position[1]) < tolerance
        and abs(position[2]) < tolerance
        and abs(quaternion[0] - 1.0) < tolerance
        and abs(quaternion[1]) < tolerance
        and abs(quaternion[2]) < tolerance
        and abs(quaternion[3]) < tolerance
    )


def _undo_or_redo(doc, command_name=None):
    command_name = (command_name or "").lower()
    return bool(getattr(doc, "UndoActive", False)) or bool(getattr(doc, "RedoActive", False)) or command_name in ("undo", "redo")


def _normalize_quaternion(quaternion):
    length = math.sqrt(sum(value * value for value in quaternion))
    if length <= 1e-12:
        return [1.0, 0.0, 0.0, 0.0]
    return [value / length for value in quaternion]


def _interpolate_pose(start_pose, end_pose, t):
    position = [
        start_value + (end_value - start_value) * t
        for start_value, end_value in zip(start_pose["position"], end_pose["position"])
    ]
    start_quaternion = list(start_pose["quaternion"])
    end_quaternion = list(end_pose["quaternion"])
    if sum(a * b for a, b in zip(start_quaternion, end_quaternion)) < 0.0:
        end_quaternion = [-value for value in end_quaternion]
    quaternion = _normalize_quaternion([
        start_value + (end_value - start_value) * t
        for start_value, end_value in zip(start_quaternion, end_quaternion)
    ])
    return {"position": position, "quaternion": quaternion}


def _drag_substep_count(start_pose, end_pose):
    translation = Rhino.Geometry.Point3d(*start_pose["position"]).DistanceTo(
        Rhino.Geometry.Point3d(*end_pose["position"])
    )
    rotation = _quaternion_distance(start_pose["quaternion"], end_pose["quaternion"])
    return max(1, min(60, int(max(math.ceil(translation / 2.0), math.ceil(rotation / 0.02)))))


def _driver_pose_error(current_pose, solved_pose):
    translation = Rhino.Geometry.Point3d(*current_pose["position"]).DistanceTo(
        Rhino.Geometry.Point3d(*solved_pose["position"])
    )
    rotation = _quaternion_distance(current_pose["quaternion"], solved_pose["quaternion"])
    return translation, rotation


def _planar_offset_error(doc, data, driver_part_id):
    """Return the largest live offset and normal error for driver's face joints."""
    offset_error = 0.0
    normal_error = 0.0
    found = False
    for constraint in data["constraints"]:
        if constraint.get("type") != "planar_offset":
            continue
        sides = (constraint.get("a", {}), constraint.get("b", {}))
        if driver_part_id not in [side.get("part") for side in sides]:
            continue
        plane_a = _face_plane(
            doc,
            constraint["a"]["part"],
            int(constraint["a"]["face_index"]),
        )
        plane_b = _face_plane(
            doc,
            constraint["b"]["part"],
            int(constraint["b"]["face_index"]),
        )
        if plane_a is None or plane_b is None:
            return float("inf"), float("inf"), True
        found = True
        actual_offset = (plane_b.Origin - plane_a.Origin) * plane_a.ZAxis
        offset_error = max(
            offset_error,
            abs(actual_offset - float(constraint["offset"])),
        )
        normal_error = max(
            normal_error,
            1.0 - abs(plane_a.ZAxis * plane_b.ZAxis),
        )
    return offset_error, normal_error, found


def _project_planar_driver_translation(doc, data, driver_part_id, current_pose):
    """Project only normal translation, retaining the driver's free motion.

    Ondsel's underconstrained solve can choose an arbitrary in-plane position.
    For an untilted planar relationship, the face metadata provides the exact
    correction: translate the moved part only along the first face's normal.
    """
    constraints = [
        constraint
        for constraint in data["constraints"]
        if constraint.get("type") == "planar_offset"
        and driver_part_id
        in (
            constraint.get("a", {}).get("part"),
            constraint.get("b", {}).get("part"),
        )
    ]
    if len(constraints) != 1:
        return None

    constraint = constraints[0]
    plane_a = _face_plane(
        doc,
        constraint["a"]["part"],
        int(constraint["a"]["face_index"]),
    )
    plane_b = _face_plane(
        doc,
        constraint["b"]["part"],
        int(constraint["b"]["face_index"]),
    )
    if plane_a is None or plane_b is None:
        return None
    normal_error = 1.0 - abs(plane_a.ZAxis * plane_b.ZAxis)
    if normal_error > 1e-8:
        return None

    actual_offset = (plane_b.Origin - plane_a.Origin) * plane_a.ZAxis
    offset_error = actual_offset - float(constraint["offset"])
    if abs(offset_error) <= doc.ModelAbsoluteTolerance:
        return None

    direction = Rhino.Geometry.Vector3d(plane_a.ZAxis)
    if driver_part_id == constraint["a"]["part"]:
        direction = direction * offset_error
    else:
        direction = direction * -offset_error
    projected_pose = _copy_pose(current_pose)
    projected_pose["position"] = [
        value + correction
        for value, correction in zip(
            projected_pose["position"],
            assembly_common.vector_tuple(direction),
        )
    ]
    return projected_pose, offset_error


def _planar_parent_follow_poses(doc, data, driver_part_id, current_poses):
    """Carry planar children by the moved parent's live rigid delta."""
    parent_constraints = [
        constraint
        for constraint in data["constraints"]
        if constraint.get("type") == "planar_offset"
        and constraint.get("a", {}).get("part") == driver_part_id
    ]
    previous_parent_pose = _settled_pose(doc, driver_part_id)
    if not parent_constraints or previous_parent_pose is None:
        return {}

    parent_delta = _pose_delta(previous_parent_pose, current_poses[driver_part_id])
    followers = {}
    for constraint in parent_constraints:
        child_part_id = constraint["b"]["part"]
        child_pose = current_poses.get(child_part_id)
        if child_pose is None:
            continue
        child_plane = _pose_to_plane(child_pose)
        child_plane.Transform(parent_delta)
        followers[child_part_id] = _plane_to_pose(child_plane)
    return followers


def _rewrite_part_id(data, old_object_id, new_object_id):
    old_key = assembly_common.guid_string(old_object_id)
    new_key = assembly_common.guid_string(new_object_id)
    if old_key == new_key:
        return new_key
    part = data["parts"].pop(old_key, None)
    if part is None:
        return new_key
    part["object_id"] = new_key
    data["parts"][new_key] = part
    for constraint in data["constraints"]:
        ctype = constraint.get("type")
        if ctype in ("revolute", "planar_offset"):
            for side_name in ("a", "b"):
                if constraint[side_name].get("part") == old_key:
                    constraint[side_name]["part"] = new_key
        elif ctype in ("world_anchor", "slider_axis"):
            if constraint.get("part") == old_key:
                constraint["part"] = new_key
    return new_key


def _adopt_replacement_runtime(doc, old_object_id, new_object_id):
    old_key = assembly_common.guid_string(old_object_id)
    new_key = assembly_common.guid_string(new_object_id)
    state = _runtime(doc, True)
    if state.get(DRIVER_PART_KEY) == old_key:
        state[DRIVER_PART_KEY] = new_key
    serials = state.get("serials", {})
    if old_key in serials:
        serials[new_key] = serials.pop(old_key)
    settled = state.get(SETTLED_POSES_KEY, {})
    if old_key in settled:
        settled[new_key] = settled.pop(old_key)


def _transform_part_with_replacement(doc, data, part, delta):
    old_object_id = part["object_id"]
    transformed_id = doc.Objects.Transform(assembly_common.parse_guid(old_object_id), delta, True)
    if transformed_id is None:
        return old_object_id, False
    new_object_id = assembly_common.guid_string(transformed_id)
    replaced = new_object_id != old_object_id
    if replaced:
        _debug("part {} replaced id {} -> {}".format(part["name"], old_object_id[:8], new_object_id[:8]))
        _rewrite_part_id(data, old_object_id, new_object_id)
        _adopt_replacement_runtime(doc, old_object_id, new_object_id)
    return new_object_id, replaced


def _align_revolute_child(doc, side_a, side_b):
    parent_plane = _edge_plane(doc, side_a["object_id"], side_a["edge_index"])
    child_plane = _edge_plane(doc, side_b["object_id"], side_b["edge_index"])
    if parent_plane is None or child_plane is None:
        return False
    transform = assembly_common.transform_between_planes(child_plane, parent_plane)
    doc.Objects.Transform(assembly_common.parse_guid(side_b["object_id"]), transform, True)
    return True


def _project_point_to_line(point, line_origin, line_direction):
    vector = point - line_origin
    distance = vector * line_direction
    return line_origin + line_direction * distance


def prealign_slider_child(doc, rhino_object, part_axis_origin, part_axis_direction, world_axis_origin, world_axis_direction):
    part_axis_plane = assembly_common.plane_from_axis(part_axis_origin, part_axis_direction)
    world_axis_plane = assembly_common.plane_from_axis(world_axis_origin, world_axis_direction)
    transform = assembly_common.transform_between_planes(part_axis_plane, world_axis_plane)
    doc.Objects.Transform(rhino_object.Id, transform, True)
    return True


def solve_and_propagate(doc, driver_part_id=None, driver_pose=None, apply=True, initial_poses=None):
    debug_log = _debug if apply else (lambda message: None)
    data = read_data(doc)
    if not data["constraints"] or not data["parts"]:
        debug_log("solve skipped: no constraints or no parts")
        return {"moved": []}

    has_anchor = any(c.get("type") == "world_anchor" for c in data["constraints"])
    if not has_anchor:
        debug_log("solve skipped: no world anchor yet")
        return {"moved": []}

    if driver_part_id is None:
        driver_part_id = _pop_driver_part_id(doc)
    if driver_part_id is not None:
        driver_part_id = assembly_common.guid_string(driver_part_id)
        if driver_part_id not in data["parts"]:
            driver_part_id = None

    debug_log(
        "solve start: parts={} constraints={} driver={}".format(
            len(data["parts"]), len(data["constraints"]),
            str(driver_part_id)[:8] if driver_part_id else "<none>"
        )
    )

    module = assembly_common.load_ondsel_module()
    assembly = module.Assembly("Assembly_{}".format(uuid.uuid4().hex[:8]))
    assembly.add_part("world", (0.0, 0.0, 0.0), (1.0, 0.0, 0.0, 0.0))
    assembly.set_fixed("world", True)

    parts_in_order = list(data["parts"].values())
    current_poses = {}
    requested_driver_pose = _copy_pose(driver_pose) if driver_pose is not None else None
    for part in parts_in_order:
        initial_pose = None if initial_poses is None else initial_poses.get(part["object_id"])
        current_pose, input_pose = _pose_of_part_for_solver(doc, data, part, initial_pose)
        if (
            requested_driver_pose is not None
            and part["object_id"] == driver_part_id
        ):
            current_pose = _copy_pose(requested_driver_pose)
        current_poses[part["object_id"]] = current_pose
        assembly.add_part(part["name"], input_pose["position"], input_pose["quaternion"])
        debug_log(
            "part {} input pose pos={} quat={}".format(
                part["name"],
                [round(v, 6) for v in input_pose["position"]],
                [round(v, 6) for v in input_pose["quaternion"]],
            )
        )

    for constraint in data["constraints"]:
        ctype = constraint.get("type")
        if ctype == "revolute":
            skip_constraint = False
            for side_name in ("a", "b"):
                side = constraint[side_name]
                part = data["parts"][side["part"]]
                if "edge_index" in side:
                    local_marker = _local_marker_pose(doc, part, int(side["edge_index"]))
                else:
                    local_marker = side.get("marker")
                if local_marker is None:
                    debug_log("revolute {} skipped: missing live edge/marker for side {}".format(constraint["id"][:8], side_name))
                    skip_constraint = True
                    break
                assembly.add_marker(part["name"], constraint["id"] + "_" + side_name, local_marker["position"], local_marker["quaternion"])
            if skip_constraint:
                continue
            part_a = data["parts"][constraint["a"]["part"]]["name"]
            part_b = data["parts"][constraint["b"]["part"]]["name"]
            assembly.add_revolute_joint(constraint["id"], part_a, constraint["id"] + "_a", part_b, constraint["id"] + "_b")
        elif ctype == "planar_offset":
            markers = {}
            for side_name in ("a", "b"):
                side = constraint[side_name]
                part = data["parts"][side["part"]]
                marker = _local_face_marker_pose(doc, part, int(side["face_index"]))
                if marker is None:
                    debug_log(
                        "planar offset {} skipped: missing face for side {}".format(
                            constraint["id"][:8],
                            side_name,
                        )
                    )
                    markers = None
                    break
                markers[side_name] = marker
            if markers is None:
                continue
            part_a = data["parts"][constraint["a"]["part"]]["name"]
            part_b = data["parts"][constraint["b"]["part"]]["name"]
            assembly.add_marker(
                part_a,
                constraint["id"] + "_a",
                markers["a"]["position"],
                markers["a"]["quaternion"],
            )
            assembly.add_marker(
                part_b,
                constraint["id"] + "_b",
                markers["b"]["position"],
                markers["b"]["quaternion"],
            )
            assembly.add_planar_joint(
                constraint["id"],
                part_a,
                constraint["id"] + "_a",
                part_b,
                constraint["id"] + "_b",
                float(constraint["offset"]),
            )
        elif ctype == "slider_axis":
            part = data["parts"][constraint["part"]]
            local_marker = constraint["marker"]
            axis_plane = assembly_common.plane_from_axis(
                Rhino.Geometry.Point3d(*constraint["world_axis_origin"]),
                Rhino.Geometry.Vector3d(*constraint["world_axis_direction"]),
            )
            axis_pose = _plane_to_pose(axis_plane)
            assembly.add_marker(part["name"], constraint["id"] + "_part", local_marker["position"], local_marker["quaternion"])
            assembly.add_marker("world", constraint["id"] + "_world", axis_pose["position"], axis_pose["quaternion"])
            assembly.add_point_in_line_joint(constraint["id"] + "_line", part["name"], constraint["id"] + "_part", "world", constraint["id"] + "_world")
            assembly.add_parallel_axes_joint(constraint["id"] + "_axis", part["name"], constraint["id"] + "_part", "world", constraint["id"] + "_world")
        elif ctype == "world_anchor":
            part = data["parts"][constraint["part"]]
            local_marker = constraint["marker"]
            world_pose = constraint["world_pose"]
            assembly.add_marker(part["name"], constraint["id"] + "_part", local_marker["position"], local_marker["quaternion"])
            assembly.add_marker("world", constraint["id"] + "_world", world_pose["position"], world_pose["quaternion"])
            assembly.add_fixed_joint(constraint["id"], part["name"], constraint["id"] + "_part", "world", constraint["id"] + "_world")

    if driver_part_id is not None:
        driver_part = data["parts"][driver_part_id]
        driver_pose = current_poses[driver_part_id]
        start_pose = (
            None if initial_poses is None else initial_poses.get(driver_part_id)
        ) or _settled_pose(doc, driver_part_id) or driver_pose
        step_count = _drag_substep_count(start_pose, driver_pose)
        debug_log(
            "assembly.drag() driver={} pos={} quat={} steps={}".format(
                driver_part["name"],
                [round(v, 6) for v in driver_pose["position"]],
                [round(v, 6) for v in driver_pose["quaternion"]],
                step_count,
            )
        )
        assembly.begin_drag()
        for step_index in range(1, step_count + 1):
            step_pose = _interpolate_pose(start_pose, driver_pose, float(step_index) / float(step_count))
            assembly.drag_step(
                [driver_part["name"]],
                [step_pose["position"]],
                [step_pose["quaternion"]],
            )
        assembly.end_drag()
        debug_log("assembly.drag() complete")
    else:
        debug_log("assembly.solve()")
        assembly.solve()
        debug_log("assembly.solve() complete")

    solved_poses = {}
    for part in parts_in_order:
        solved_position, solved_quaternion = assembly.get_pose(part["name"])
        solved_pose = {
            "position": list(solved_position),
            "quaternion": list(solved_quaternion),
        }
        solved_poses[part["object_id"]] = solved_pose
        debug_log(
            "part {} solved pose pos={} quat={}".format(
                part["name"],
                [round(v, 6) for v in solved_pose["position"]],
                [round(v, 6) for v in solved_pose["quaternion"]],
            )
        )

    if driver_part_id is not None:
        planar_projection = _project_planar_driver_translation(
            doc,
            data,
            driver_part_id,
            current_poses[driver_part_id],
        )
        if planar_projection is not None:
            solved_poses[driver_part_id], projected_offset_error = planar_projection
            debug_log(
                "driver planar translation projection: offset_error={}".format(
                    round(projected_offset_error, 9),
                )
            )

    parent_followers = {}
    if driver_part_id is not None:
        parent_followers = _planar_parent_follow_poses(
            doc,
            data,
            driver_part_id,
            current_poses,
        )
        if parent_followers:
            solved_poses.update(parent_followers)
            debug_log(
                "parent driver={} carries planar children={}".format(
                    driver_part_id[:8],
                    [object_id[:8] for object_id in parent_followers],
                )
            )

    keep_driver = False
    if driver_part_id is not None:
        driver_translation_error, driver_rotation_error = _driver_pose_error(
            current_poses[driver_part_id],
            solved_poses[driver_part_id],
        )
        offset_error, normal_error, driver_has_planar_offset = _planar_offset_error(
            doc,
            data,
            driver_part_id,
        )
        # Preserve valid in-plane translation/spin exactly. Project only a
        # driver that has changed its signed face gap or face-normal alignment.
        planar_is_valid = (
            offset_error <= doc.ModelAbsoluteTolerance
            and normal_error <= 1e-8
        )
        keep_driver = bool(parent_followers) or not driver_has_planar_offset or planar_is_valid
        debug_log(
            "driver {}: translation_error={} rotation_error={} "
            "planar_offset_error={} planar_normal_error={}".format(
                "preserved as parent" if parent_followers else (
                    "preserved" if keep_driver else "projected for planar offset"
                ),
                round(driver_translation_error, 6),
                round(driver_rotation_error, 6),
                round(offset_error, 9),
                round(normal_error, 9),
            )
        )

    if not apply:
        preview_poses = {
            object_id: _copy_pose(pose)
            for object_id, pose in solved_poses.items()
        }
        debug_log("preview solve end: poses={}".format(len(preview_poses)))
        return {
            "moved": [],
            "poses": preview_poses,
            "driver_part_id": driver_part_id,
        }

    moved = []
    settled_poses = {}
    metadata_dirty = False
    for part in parts_in_order:
        old_object_id = part["object_id"]
        solved_pose = solved_poses[old_object_id]
        if driver_part_id == old_object_id and keep_driver:
            settled_poses[old_object_id] = _copy_pose(current_poses[old_object_id])
            debug_log("part {} kept as driver".format(part["name"]))
            continue
        settled_poses[old_object_id] = _copy_pose(solved_pose)
        if _pose_motion_metric(current_poses[old_object_id], solved_pose) < 1e-6:
            debug_log("part {} delta is tiny".format(part["name"]))
            continue
        delta = _pose_delta(current_poses[old_object_id], solved_pose)
        if delta.IsIdentity:
            debug_log("part {} delta is identity".format(part["name"]))
            continue
        debug_log("transforming part {} id={}".format(part["name"], old_object_id[:8]))
        new_object_id, replaced = _transform_part_with_replacement(doc, data, part, delta)
        if replaced:
            metadata_dirty = True
            current_poses[new_object_id] = current_poses.pop(old_object_id)
            solved_poses[new_object_id] = solved_poses.pop(old_object_id)
            settled_poses[new_object_id] = settled_poses.pop(old_object_id)
            if driver_part_id == old_object_id:
                driver_part_id = new_object_id
        moved.append(new_object_id)

    if metadata_dirty:
        write_data(doc, data)
    _store_serials(doc, data["parts"].keys())
    _store_settled_poses(doc, data, settled_poses)
    doc.Views.Redraw()
    debug_log("solve end: moved {} object(s)".format(len(moved)))
    return {"moved": moved}


def _report_error():
    traceback.print_exc()
    _log_line(traceback.format_exc())
    _send_terminal(traceback.format_exc())


def EndCommandHandler(sender, event):
    try:
        doc = Rhino.RhinoDoc.ActiveDoc
        command_name = getattr(event, "EnglishName", None) or getattr(event, "CommandEnglishName", None) or getattr(event, "CommandName", None) or "<unknown>"
        if doc is None:
            _debug("EndCommand ignored: no active doc")
            return
        _debug(
            "EndCommand received: command={} doc={}".format(
                command_name,
                doc.RuntimeSerialNumber,
            )
        )
        try:
            from ondsel.assembly import assembly_dynamic_conduit
            assembly_dynamic_conduit.command_ended(doc)
        except Exception:
            pass
        if is_command_busy(doc):
            _debug("EndCommand ignored during command edit: {}".format(command_name))
            return
        if is_solving(doc) or assembly_scheduler.is_solving():
            _debug("EndCommand ignored during solve: {}".format(command_name))
            return
        data = read_data(doc)
        _debug(
            "EndCommand state: command={} parts={} constraints={}".format(
                command_name,
                len(data["parts"]),
                len(data["constraints"]),
            )
        )
        if not data["parts"]:
            _debug("EndCommand ignored: no assembly parts ({})".format(command_name))
            return
        if _undo_or_redo(doc, command_name):
            _debug("EndCommand ignored during undo/redo: {}".format(command_name))
            _store_serials(doc, data["parts"].keys())
            _store_settled_poses(doc, data, {part["object_id"]: _current_pose_from_home(doc, part) for part in data["parts"].values()})
            _set_driver_part_id(doc, None)
            return
        changed = changed_part_ids(doc)
        for object_id in dynamically_transformed_part_ids(doc, data):
            if object_id not in changed:
                changed.append(object_id)
        if not changed:
            _debug("EndCommand no-op: no changed parts ({})".format(command_name))
            return
        driver_part_id = _choose_driver_part_id(doc, data, changed)
        _set_driver_part_id(doc, driver_part_id)
        _debug(
            "EndCommand {} changed parts={} driver={}".format(
                command_name,
                [str(value)[:8] for value in changed],
                str(driver_part_id)[:8] if driver_part_id else "<none>",
            )
        )
        assembly_scheduler.expire_document(doc, reason="EndCommand {}".format(command_name))
    except Exception:
        _report_error()
    finally:
        pass


def CloseDocumentHandler(sender, event):
    doc = getattr(event, "Document", None)
    if doc is not None:
        assembly_scheduler.drop_document(doc)
        _runtime_registry(True).pop(_doc_key(doc), None)


def subscribe():
    unsubscribe()
    drop_watcher_connection()  # drop any connection from a previous watcher
    get_watcher_connection()  # establish the feedback socket for this watcher
    handlers = (EndCommandHandler, CloseDocumentHandler)
    sc.sticky[HANDLER_KEY] = handlers
    Rhino.Commands.Command.EndCommand += EndCommandHandler
    Rhino.RhinoDoc.CloseDocument += CloseDocumentHandler


def unsubscribe():
    assembly_scheduler.disarm()
    try:
        from ondsel.assembly import assembly_dynamic_conduit
        assembly_dynamic_conduit.stop()
    except Exception:
        pass
    stored_handlers = sc.sticky.pop(HANDLER_KEY, ())
    events = (
        Rhino.Commands.Command.EndCommand,
        Rhino.RhinoDoc.CloseDocument,
    )
    for handler, event in zip(stored_handlers, events):
        try:
            event -= handler
        except Exception:
            pass
