import json
import traceback
import uuid

import Rhino
import scriptcontext as sc

from ondsel.assembly import assembly_common

DATA_KEY = "Ondsel.Assembly.v1"
RUNTIME_KEY = "Ondsel.Assembly.Runtime.v1"
HANDLER_KEY = "Ondsel.Assembly.Handlers.v1"
SOLVING_KEY = "Ondsel.Assembly.Solving.v1"


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


def _current_pose_from_home(doc, part_meta):
    """Current part pose from its registered home edge.

    The part frame is defined by the chosen home edge itself. If the user moves
    the part, the live home-edge frame *is* the part's current world pose.
    """
    home = part_meta.get("home")
    if home is None:
        return {"position": [0.0, 0.0, 0.0], "quaternion": [1.0, 0.0, 0.0, 0.0]}
    live_plane = _edge_plane(doc, part_meta["object_id"], home["edge_index"])
    if live_plane is None:
        return home["pose"]
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


def _local_marker_pose(doc, part_meta, edge_index):
    current_pose = _current_pose_from_home(doc, part_meta)
    current_plane = _pose_to_plane(current_pose)
    edge_plane = _edge_plane(doc, part_meta["object_id"], edge_index)
    if edge_plane is None:
        return None
    to_local = assembly_common.transform_between_planes(current_plane, Rhino.Geometry.Plane.WorldXY)
    local_plane = assembly_common.transformed_plane(edge_plane, to_local)
    return _plane_to_pose(local_plane)


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
        "a": {"part": part_a["object_id"], "marker": marker_a},
        "b": {"part": part_b["object_id"], "marker": marker_b},
    }
    data["constraints"].append(constraint)
    write_data(doc, data)
    _store_serials(doc, data["parts"].keys())
    return constraint


def add_world_anchor(doc, rhino_object):
    data = read_data(doc)
    part = _ensure_part(doc, data, rhino_object.Id)
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
    return part


def add_slider_axis(doc, side, axis_origin, axis_direction):
    data = read_data(doc)
    part = _register_part_from_edge(doc, data, side["object_id"], side["edge_index"])
    marker = _local_marker_pose(doc, part, side["edge_index"])
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
            "axis_origin": list(assembly_common.point_tuple(axis_origin)),
            "axis_direction": list(assembly_common.vector_tuple(axis_direction)),
        }
    )
    write_data(doc, data)
    _store_serials(doc, data["parts"].keys())
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


def prealign_slider_child(doc, side, axis_origin, axis_direction):
    plane = _edge_plane(doc, side["object_id"], side["edge_index"])
    if plane is None:
        return False
    point = plane.Origin
    projected = _project_point_to_line(point, axis_origin, axis_direction)
    translation = projected - point
    transform = Rhino.Geometry.Transform.Translation(translation)
    doc.Objects.Transform(assembly_common.parse_guid(side["object_id"]), transform, True)
    return True


def solve_and_propagate(doc):
    data = read_data(doc)
    if not data["constraints"] or not data["parts"]:
        return {"moved": []}

    has_anchor = any(c.get("type") == "world_anchor" for c in data["constraints"])
    if not has_anchor:
        print("[Ondsel assembly] No world anchor yet; skipping solve.")
        return {"moved": []}

    module = assembly_common.load_ondsel_module()
    assembly = module.Assembly("Assembly1")
    assembly.add_part("world", (0.0, 0.0, 0.0), (1.0, 0.0, 0.0, 0.0))
    assembly.set_fixed("world", True)

    current_poses = {}
    input_poses = {}
    for part in data["parts"].values():
        current_pose, input_pose = _pose_of_part_for_solver(doc, data, part)
        current_poses[part["object_id"]] = current_pose
        input_poses[part["object_id"]] = input_pose
        assembly.add_part(part["name"], input_pose["position"], input_pose["quaternion"])

    for constraint in data["constraints"]:
        ctype = constraint.get("type")
        if ctype == "revolute":
            for side_name in ("a", "b"):
                side = constraint[side_name]
                part = data["parts"][side["part"]]
                local_marker = side["marker"]
                assembly.add_marker(part["name"], constraint["id"] + "_" + side_name, local_marker["position"], local_marker["quaternion"])
            part_a = data["parts"][constraint["a"]["part"]]["name"]
            part_b = data["parts"][constraint["b"]["part"]]["name"]
            assembly.add_revolute_joint(constraint["id"], part_a, constraint["id"] + "_a", part_b, constraint["id"] + "_b")
        elif ctype == "slider_axis":
            part = data["parts"][constraint["part"]]
            local_marker = constraint["marker"]
            axis_plane = assembly_common.plane_from_axis(
                Rhino.Geometry.Point3d(*constraint["axis_origin"]),
                Rhino.Geometry.Vector3d(*constraint["axis_direction"]),
            )
            axis_pose = _plane_to_pose(axis_plane)
            assembly.add_marker(part["name"], constraint["id"] + "_part", local_marker["position"], local_marker["quaternion"])
            assembly.add_marker("world", constraint["id"] + "_world", axis_pose["position"], axis_pose["quaternion"])
            assembly.add_point_in_line_joint(constraint["id"], part["name"], constraint["id"] + "_part", "world", constraint["id"] + "_world")
        elif ctype == "world_anchor":
            part = data["parts"][constraint["part"]]
            local_marker = constraint["marker"]
            world_pose = constraint["world_pose"]
            assembly.add_marker(part["name"], constraint["id"] + "_part", local_marker["position"], local_marker["quaternion"])
            assembly.add_marker("world", constraint["id"] + "_world", world_pose["position"], world_pose["quaternion"])
            assembly.add_fixed_joint(constraint["id"], part["name"], constraint["id"] + "_part", "world", constraint["id"] + "_world")

    assembly.solve()

    moved = []
    for part in data["parts"].values():
        solved_position, solved_quaternion = assembly.get_pose(part["name"])
        solved_pose = {
            "position": list(solved_position),
            "quaternion": list(solved_quaternion),
        }
        delta = _pose_delta(current_poses[part["object_id"]], solved_pose)
        if delta.IsIdentity:
            continue
        doc.Objects.Transform(assembly_common.parse_guid(part["object_id"]), delta, True)
        moved.append(part["object_id"])

    _store_serials(doc, data["parts"].keys())
    doc.Views.Redraw()
    return {"moved": moved}


def _report_error():
    traceback.print_exc()


def EndCommandHandler(sender, event):
    try:
        doc = Rhino.RhinoDoc.ActiveDoc
        if doc is None or is_solving(doc):
            return
        data = read_data(doc)
        if not data["parts"]:
            return
        changed = changed_part_ids(doc)
        if not changed:
            return
        _set_solving(doc, True)
        solve_and_propagate(doc)
    except Exception:
        _report_error()
    finally:
        doc = Rhino.RhinoDoc.ActiveDoc
        if doc is not None:
            _set_solving(doc, False)


def CloseDocumentHandler(sender, event):
    doc = getattr(event, "Document", None)
    if doc is not None:
        _runtime_registry(True).pop(_doc_key(doc), None)


def subscribe():
    unsubscribe()
    handlers = (EndCommandHandler, CloseDocumentHandler)
    sc.sticky[HANDLER_KEY] = handlers
    Rhino.Commands.Command.EndCommand += EndCommandHandler
    Rhino.RhinoDoc.CloseDocument += CloseDocumentHandler


def unsubscribe():
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
