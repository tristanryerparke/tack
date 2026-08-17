import json
import math
import traceback
import uuid

import Rhino
import scriptcontext as sc

from ondsel.assembly import assembly_common
from ondsel.assembly import assembly_scheduler


def _debug(message):
    text = "[Ondsel assembly] " + str(message)
    print(text)
    try:
        from tack import watcher

        with watcher.output(True):
            print(text)
    except Exception:
        pass

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


def _pose_to_plane(pose):
    return assembly_common.plane_from_pose(pose["position"], pose["quaternion"])


def _plane_to_pose(plane):
    position, quaternion = assembly_common.pose_from_plane(plane)
    return {"position": list(position), "quaternion": list(quaternion)}


def _identity_pose():
    return {"position": [0.0, 0.0, 0.0], "quaternion": [1.0, 0.0, 0.0, 0.0]}


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


def _current_pose_from_home(doc, part_meta):
    """Current part pose from its registered home frame.

    If a part was registered from an edge, that edge defines the live body pose.
    If a part was anchored before it had a home edge, it keeps a stored static
    body frame instead.
    """
    home = part_meta.get("home")
    if home is None:
        return _identity_pose()
    edge_index = home.get("edge_index")
    if edge_index is None:
        return home.get("pose", _identity_pose())
    live_plane = _edge_plane(doc, part_meta["object_id"], edge_index)
    if live_plane is None:
        return home.get("pose", _identity_pose())
    return _plane_to_pose(live_plane)


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


def _local_pose_from_world_plane(doc, part_meta, world_plane):
    current_pose = _current_pose_from_home(doc, part_meta)
    current_plane = _pose_to_plane(current_pose)
    to_local = assembly_common.transform_between_planes(current_plane, Rhino.Geometry.Plane.WorldXY)
    local_plane = assembly_common.transformed_plane(world_plane, to_local)
    return _plane_to_pose(local_plane)


def _local_marker_pose(doc, part_meta, edge_index):
    edge_plane = _edge_plane(doc, part_meta["object_id"], edge_index)
    if edge_plane is None:
        return None
    return _local_pose_from_world_plane(doc, part_meta, edge_plane)


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


def _pose_of_part_for_solver(doc, data, part_meta):
    current_pose = _current_pose_from_home(doc, part_meta)
    return current_pose, current_pose


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
    return max(1, min(40, int(max(math.ceil(translation / 2.0), math.ceil(rotation / 0.05)))))


def _driver_pose_error(current_pose, solved_pose):
    translation = Rhino.Geometry.Point3d(*current_pose["position"]).DistanceTo(
        Rhino.Geometry.Point3d(*solved_pose["position"])
    )
    rotation = _quaternion_distance(current_pose["quaternion"], solved_pose["quaternion"])
    return translation, rotation


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
        if ctype == "revolute":
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


def solve_and_propagate(doc, driver_part_id=None):
    data = read_data(doc)
    if not data["constraints"] or not data["parts"]:
        _debug("solve skipped: no constraints or no parts")
        return {"moved": []}

    has_anchor = any(c.get("type") == "world_anchor" for c in data["constraints"])
    if not has_anchor:
        _debug("solve skipped: no world anchor yet")
        return {"moved": []}

    if driver_part_id is None:
        driver_part_id = _pop_driver_part_id(doc)
    if driver_part_id is not None:
        driver_part_id = assembly_common.guid_string(driver_part_id)
        if driver_part_id not in data["parts"]:
            driver_part_id = None

    _debug(
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
    for part in parts_in_order:
        current_pose, input_pose = _pose_of_part_for_solver(doc, data, part)
        current_poses[part["object_id"]] = current_pose
        assembly.add_part(part["name"], input_pose["position"], input_pose["quaternion"])
        _debug(
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
                    _debug("revolute {} skipped: missing live edge/marker for side {}".format(constraint["id"][:8], side_name))
                    skip_constraint = True
                    break
                assembly.add_marker(part["name"], constraint["id"] + "_" + side_name, local_marker["position"], local_marker["quaternion"])
            if skip_constraint:
                continue
            part_a = data["parts"][constraint["a"]["part"]]["name"]
            part_b = data["parts"][constraint["b"]["part"]]["name"]
            assembly.add_revolute_joint(constraint["id"], part_a, constraint["id"] + "_a", part_b, constraint["id"] + "_b")
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
        start_pose = _settled_pose(doc, driver_part_id) or driver_pose
        step_count = _drag_substep_count(start_pose, driver_pose)
        _debug(
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
        _debug("assembly.drag() complete")
    else:
        _debug("assembly.solve()")
        assembly.solve()
        _debug("assembly.solve() complete")

    solved_poses = {}
    for part in parts_in_order:
        solved_position, solved_quaternion = assembly.get_pose(part["name"])
        solved_pose = {
            "position": list(solved_position),
            "quaternion": list(solved_quaternion),
        }
        solved_poses[part["object_id"]] = solved_pose
        _debug(
            "part {} solved pose pos={} quat={}".format(
                part["name"],
                [round(v, 6) for v in solved_pose["position"]],
                [round(v, 6) for v in solved_pose["quaternion"]],
            )
        )

    keep_driver = False
    if driver_part_id is not None:
        driver_translation_error, driver_rotation_error = _driver_pose_error(
            current_poses[driver_part_id],
            solved_poses[driver_part_id],
        )
        keep_driver = (
            driver_translation_error <= max(doc.ModelAbsoluteTolerance * 10.0, 0.1)
            and driver_rotation_error <= 0.01
        )
        if keep_driver:
            _debug(
                "driver feasible: translation_error={} rotation_error={}".format(
                    round(driver_translation_error, 6),
                    round(driver_rotation_error, 6),
                )
            )
        else:
            _debug(
                "driver infeasible: translation_error={} rotation_error={} -> snapping to solved pose".format(
                    round(driver_translation_error, 6),
                    round(driver_rotation_error, 6),
                )
            )

    moved = []
    settled_poses = {}
    metadata_dirty = False
    for part in parts_in_order:
        old_object_id = part["object_id"]
        solved_pose = solved_poses[old_object_id]
        if driver_part_id == old_object_id and keep_driver:
            settled_poses[old_object_id] = _copy_pose(current_poses[old_object_id])
            _debug("part {} kept as driver".format(part["name"]))
            continue
        settled_poses[old_object_id] = _copy_pose(solved_pose)
        if _pose_motion_metric(current_poses[old_object_id], solved_pose) < 1e-6:
            _debug("part {} delta is tiny".format(part["name"]))
            continue
        delta = _pose_delta(current_poses[old_object_id], solved_pose)
        if delta.IsIdentity:
            _debug("part {} delta is identity".format(part["name"]))
            continue
        _debug("transforming part {} id={}".format(part["name"], old_object_id[:8]))
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
    _debug("solve end: moved {} object(s)".format(len(moved)))
    return {"moved": moved}


def _report_error():
    traceback.print_exc()
    try:
        from tack import watcher

        with watcher.output(True):
            traceback.print_exc()
    except Exception:
        pass


def EndCommandHandler(sender, event):
    try:
        doc = Rhino.RhinoDoc.ActiveDoc
        command_name = getattr(event, "EnglishName", None) or getattr(event, "CommandEnglishName", None) or getattr(event, "CommandName", None) or "<unknown>"
        if doc is None:
            _debug("EndCommand ignored: no active doc")
            return
        if is_command_busy(doc):
            _debug("EndCommand ignored during command edit: {}".format(command_name))
            return
        if is_solving(doc) or assembly_scheduler.is_solving():
            _debug("EndCommand ignored during solve: {}".format(command_name))
            return
        data = read_data(doc)
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
    handlers = (EndCommandHandler, CloseDocumentHandler)
    sc.sticky[HANDLER_KEY] = handlers
    Rhino.Commands.Command.EndCommand += EndCommandHandler
    Rhino.RhinoDoc.CloseDocument += CloseDocumentHandler


def unsubscribe():
    assembly_scheduler.disarm()
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
