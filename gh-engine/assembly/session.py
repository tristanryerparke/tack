"""Live AssemblyGH session management.

A session is the bridge between individual mate commands and one generated
Grasshopper document. Mate commands should mutate the mate records, then ask the
generator to rebuild the GH definition from those records.
"""

import json
import os
import uuid

from assembly.bodies import body_registry_from_records
from assembly.constants import GENERATED_DIR_NAME, GENERATED_PROJECT_PREFIX, STICKY_KEY
from assembly.joint_records import validate_joint_record
from assembly.mate_records import validate_mate_record

HANDLERS_KEY = STICKY_KEY + ".Handlers"
IDLE_SOLVE_HANDLER_KEY = STICKY_KEY + ".IdleSolveHandler"


class AssemblySessionError(Exception):
    pass


def _project_root():
    return os.path.dirname(os.path.dirname(os.path.dirname(__file__)))


def generated_dir():
    path = os.path.join(_project_root(), "gh-engine", GENERATED_DIR_NAME)
    if not os.path.isdir(path):
        os.makedirs(path)
    return path


def _safe_filename_part(value):
    text = str(value or "").strip()
    invalid = set('/\\:*?"<>|')
    cleaned = "".join("_" if character in invalid else character for character in text)
    return cleaned or "untitled"


def _load_grasshopper():
    import clr

    clr.AddReference("Grasshopper")
    import Grasshopper
    from Grasshopper import Instances
    from Grasshopper.Kernel import GH_Document, GH_DocumentIO

    try:
        Instances.AutoShowBanner = False
        Instances.AutoHideBanner = True
    except Exception:
        pass

    return {
        "Grasshopper": Grasshopper,
        "Instances": Instances,
        "GH_Document": GH_Document,
        "GH_DocumentIO": GH_DocumentIO,
    }


def _active_rhino_doc():
    import Rhino

    doc = Rhino.RhinoDoc.ActiveDoc
    if doc is not None:
        return doc
    try:
        import scriptcontext as sc

        return sc.doc
    except Exception:
        return None


def _sticky():
    import scriptcontext as sc

    return sc.sticky


def _document_server(api):
    return api["Instances"].DocumentServer


def show_session_document(session):
    """Make the generated GH document the visible Grasshopper canvas document."""
    ghdoc = session.get("ghdoc") if session else None
    if ghdoc is None:
        return False
    api = _load_grasshopper()
    try:
        api["Instances"].DocumentServer.PromoteDocument(ghdoc)
    except Exception:
        pass
    canvas = getattr(api["Instances"], "ActiveCanvas", None)
    if canvas is None:
        return False
    try:
        canvas.Document = ghdoc
    except Exception:
        try:
            canvas.set_Document(ghdoc)
        except Exception:
            return False
    try:
        api["Instances"].RedrawCanvas()
    except Exception:
        pass
    try:
        canvas.Refresh()
    except Exception:
        pass
    return True


def _metadata_path(definition_path):
    root, _ = os.path.splitext(definition_path)
    return root + ".assembly.json"


def _bind_grasshopper_document_path(ghdoc, path):
    try:
        ghdoc.FilePath = path
    except Exception:
        pass
    try:
        ghdoc.Properties.ProjectFileName = os.path.basename(path)
    except Exception:
        pass


def _delete_file_if_exists(path):
    if path and os.path.isfile(path):
        os.remove(path)
        return True
    return False


def _delete_session_files(session):
    removed = []
    definition_path = session.get("path") if session else None
    for path in (definition_path, _metadata_path(definition_path) if definition_path else None):
        if _delete_file_if_exists(path):
            removed.append(path)
    return removed


def _generated_definition_path(rhino_doc, session_id):
    rhino_path = getattr(rhino_doc, "Path", None) if rhino_doc is not None else None
    if rhino_path:
        directory = os.path.dirname(str(rhino_path))
        base_name = os.path.splitext(os.path.basename(str(rhino_path)))[0]
    else:
        directory = generated_dir()
        base_name = "unsaved_rhino_document"

    if not os.path.isdir(directory):
        os.makedirs(directory)

    filename = "{}_AssemblyGH_{}.ghx".format(
        _safe_filename_part(base_name),
        _safe_filename_part(str(session_id).split("-", 1)[0]),
    )
    return os.path.join(directory, filename)


def _new_session(api, rhino_doc=None, *, name=None):
    rhino_doc = rhino_doc or _active_rhino_doc()
    ghdoc = api["GH_Document"]()
    ghdoc.Enabled = True
    ghdoc.ActiveDoc = True

    session_id = str(uuid.uuid4())
    display_name = name or "{} {}".format(GENERATED_PROJECT_PREFIX, session_id.split("-", 1)[0])
    definition_path = _generated_definition_path(rhino_doc, session_id)
    ghdoc.Properties.ProjectFileName = os.path.basename(definition_path)

    session = {
        "id": session_id,
        "name": display_name,
        "rhino_doc_id": str(getattr(rhino_doc, "DocumentId", "")),
        "ghdoc": ghdoc,
        "path": definition_path,
        "mates": [],
        "joints": [],
        "bodies": {},
        "controlled_objects": {},
        "dirty": True,
        "object_runtime_serials": {},
        "busy": False,
        "debug": {
            "end_command_count": 0,
            "scheduled_count": 0,
            "idle_count": 0,
            "solve_count": 0,
            "skip_count": 0,
            "last_command": None,
            "last_changed_triggers": [],
        },
        "version": 1,
    }
    _document_server(api).AddDocument(ghdoc)
    _document_server(api).PromoteDocument(ghdoc)
    show_session_document(session)
    return session


def get_active_session(required=False):
    session = _sticky().get(STICKY_KEY)
    if session is None and required:
        raise AssemblySessionError("No active AssemblyGH session. Run assembly_start.py first.")
    return session


def recreate_session_document(session):
    """Attach a fresh GH_Document to an existing session.

    This is useful during development or after the user closes/opens generated
    GH files manually. Mate records remain unchanged.
    """
    api = _load_grasshopper()
    old_ghdoc = session.get("ghdoc")
    if old_ghdoc is not None:
        try:
            api["Instances"].DocumentServer.RemoveDocument(old_ghdoc)
        except Exception:
            pass
        try:
            old_ghdoc.Dispose()
        except Exception:
            pass

    ghdoc = api["GH_Document"]()
    ghdoc.Enabled = True
    ghdoc.ActiveDoc = True
    ghdoc.Properties.ProjectFileName = os.path.basename(session.get("path") or session.get("name") or GENERATED_PROJECT_PREFIX)
    api["Instances"].DocumentServer.AddDocument(ghdoc)
    api["Instances"].DocumentServer.PromoteDocument(ghdoc)
    session["ghdoc"] = ghdoc
    show_session_document(session)
    session["dirty"] = True
    return session


def _serializable_session(session):
    _ensure_session_schema(session)
    return {
        "id": session.get("id"),
        "name": session.get("name"),
        "rhino_doc_id": session.get("rhino_doc_id"),
        "path": session.get("path"),
        "mates": session.get("mates", []),
        "joints": session.get("joints", []),
        "bodies": session.get("bodies", {}),
        "controlled_objects": session.get("controlled_objects", {}),
        "debug": session.get("debug", {}),
        "version": session.get("version", 1),
    }


def save_session_metadata(session):
    path = _metadata_path(session["path"])
    with open(path, "w") as handle:
        json.dump(_serializable_session(session), handle, indent=2, sort_keys=True)
    return path


def _candidate_metadata_paths(rhino_doc):
    rhino_path = getattr(rhino_doc, "Path", None) if rhino_doc is not None else None
    if rhino_path:
        directory = os.path.dirname(str(rhino_path))
        base_name = os.path.splitext(os.path.basename(str(rhino_path)))[0]
    else:
        directory = generated_dir()
        base_name = "unsaved_rhino_document"
    if not os.path.isdir(directory):
        return []
    prefix = "{}_AssemblyGH_".format(_safe_filename_part(base_name))
    return [
        os.path.join(directory, name)
        for name in os.listdir(directory)
        if name.startswith(prefix) and name.endswith(".assembly.json")
    ]


def _load_latest_session_metadata(api, rhino_doc=None):
    paths = _candidate_metadata_paths(rhino_doc or _active_rhino_doc())
    if not paths:
        return None
    path = sorted(paths, key=os.path.getmtime)[-1]
    with open(path) as handle:
        data = json.load(handle)

    ghdoc = api["GH_Document"]()
    ghdoc.Enabled = True
    ghdoc.ActiveDoc = True
    definition_path = data.get("path") or path.replace(".assembly.json", ".ghx")
    ghdoc.Properties.ProjectFileName = os.path.basename(definition_path)
    api["Instances"].DocumentServer.AddDocument(ghdoc)
    api["Instances"].DocumentServer.PromoteDocument(ghdoc)

    session = {
        "id": data.get("id") or str(uuid.uuid4()),
        "name": data.get("name") or GENERATED_PROJECT_PREFIX,
        "rhino_doc_id": data.get("rhino_doc_id", ""),
        "ghdoc": ghdoc,
        "path": definition_path,
        "mates": data.get("mates", []),
        "joints": data.get("joints", []),
        "bodies": data.get("bodies", {}),
        "controlled_objects": data.get("controlled_objects", {}),
        "dirty": True,
        "object_runtime_serials": {},
        "busy": False,
        "debug": data.get("debug", {
            "end_command_count": 0,
            "scheduled_count": 0,
            "idle_count": 0,
            "solve_count": 0,
            "skip_count": 0,
            "last_command": None,
            "last_changed_triggers": [],
        }),
        "version": data.get("version", 1),
    }
    _ensure_session_schema(session)
    show_session_document(session)
    return session


def get_or_create_session(*, name=None):
    session = get_active_session(False)
    if session is not None and session.get("ghdoc") is not None:
        _ensure_session_schema(session)
        _refresh_runtime_serials(session)
        _subscribe_updates()
        show_session_document(session)
        return session

    api = _load_grasshopper()
    session = _load_latest_session_metadata(api)
    if session is None:
        session = _new_session(api, name=name)
    _sticky()[STICKY_KEY] = session
    _ensure_session_schema(session)
    _refresh_runtime_serials(session)
    _subscribe_updates()
    return session


def _effective_controls(record):
    driver_mode = record.get("parameters", {}).get("driver_mode", "live_driver")
    controls = []
    for control in record.get("controls", []):
        if record.get("type") == "eccentric_joint" and control.get("role") == "eccentric_rotator" and driver_mode != "slider":
            continue
        controls.append(control)
    return controls


def _controlled_objects_from_records(mates, joints):
    controlled = {}
    for record in list(mates or []) + list(joints or []):
        for control in _effective_controls(record):
            object_id = control.get("object_id")
            if object_id:
                controlled[object_id] = control
    return controlled


def _ensure_session_schema(session):
    session.setdefault("mates", [])
    session.setdefault("joints", [])
    session["bodies"] = body_registry_from_records(
        mates=session.get("mates", []),
        joints=session.get("joints", []),
    )
    session["controlled_objects"] = _controlled_objects_from_records(
        session.get("mates", []),
        session.get("joints", []),
    )
    session.setdefault("busy", False)
    debug = session.setdefault("debug", {})
    debug.setdefault("end_command_count", 0)
    debug.setdefault("scheduled_count", 0)
    debug.setdefault("idle_count", 0)
    debug.setdefault("solve_count", 0)
    debug.setdefault("skip_count", 0)
    debug.setdefault("last_command", None)
    debug.setdefault("last_changed_triggers", [])
    return session


def append_mate(record):
    validate_mate_record(record)
    session = _ensure_session_schema(get_or_create_session())
    session["mates"].append(record)
    _ensure_session_schema(session)
    session["dirty"] = True
    return session


def append_joint(record):
    validate_joint_record(record)
    session = _ensure_session_schema(get_or_create_session())
    session["joints"].append(record)
    _ensure_session_schema(session)
    session["dirty"] = True
    return session


def replace_mates(records):
    session = _ensure_session_schema(get_or_create_session())
    session["mates"] = []
    for record in records:
        validate_mate_record(record)
        session["mates"].append(record)
    _ensure_session_schema(session)
    session["dirty"] = True
    return session


def replace_joints(records):
    session = _ensure_session_schema(get_or_create_session())
    session["joints"] = []
    for record in records:
        validate_joint_record(record)
        session["joints"].append(record)
    _ensure_session_schema(session)
    session["dirty"] = True
    return session


def _object_runtime_serial(object_id):
    import Rhino
    import System

    doc = _active_rhino_doc()
    if doc is None:
        return None
    rhino_object = doc.Objects.Find(System.Guid(str(object_id)))
    if rhino_object is None:
        return None
    return int(rhino_object.RuntimeSerialNumber)


def _referenced_object_ids(session):
    _ensure_session_schema(session)
    object_ids = set(session.get("bodies", {}).keys())
    object_ids.update(session.get("controlled_objects", {}).keys())
    return sorted(object_ids)


def _joint_ref_body_id(joint, ref_key):
    reference = joint.get("references", {}).get(ref_key)
    if reference is None:
        return None
    return reference.get("body_id")


def _joint_live_driver_object_ids(session):
    """First-pass joint-graph drivers.

    Until the bidirectional temporary-driver solver is implemented, the generated
    crank-slider adapter is live-driver: the body in a fixed-axis revolute joint
    drives the graph, just like the original eccentric proof.
    """
    drivers = []
    for joint in session.get("joints", []):
        if joint.get("type") == "revolute" and joint.get("parameters", {}).get("mode") == "body_to_world_axis":
            object_id = _joint_ref_body_id(joint, "body")
            if object_id:
                drivers.append(object_id)
    return sorted(set(drivers))


def _trigger_object_ids(session):
    """Objects whose user edits should trigger a solve."""
    _ensure_session_schema(session)
    joint_drivers = _joint_live_driver_object_ids(session)
    if joint_drivers:
        return joint_drivers
    body_ids = set(session.get("bodies", {}).keys())
    controlled_ids = set(session.get("controlled_objects", {}).keys())
    return sorted(body_ids - controlled_ids)


def _short_id(object_id):
    return str(object_id).split("-", 1)[0]


def _debug(session, message):
    session_id = (session or {}).get("id", "")[:8]
    print("[AssemblyGH debug {}] {}".format(session_id, message))


def _refresh_runtime_serials(session):
    session["object_runtime_serials"] = {
        object_id: _object_runtime_serial(object_id)
        for object_id in _referenced_object_ids(session)
    }
    return session["object_runtime_serials"]


def _changed_object_ids(session, object_ids):
    previous = session.get("object_runtime_serials", {})
    changed = []
    for object_id in object_ids:
        current = _object_runtime_serial(object_id)
        if current != previous.get(object_id):
            changed.append(object_id)
    return changed


def _trigger_objects_changed(session):
    changed = _changed_object_ids(session, _trigger_object_ids(session))
    session["debug"]["last_changed_triggers"] = changed
    return changed


def save_session_definition():
    session = get_active_session(required=True)
    ghdoc = session.get("ghdoc")
    if ghdoc is None:
        raise AssemblySessionError("Active session has no GH document.")
    api = _load_grasshopper()
    io = api["GH_DocumentIO"](ghdoc)
    if not io.SaveQuiet(session["path"]):
        raise AssemblySessionError("Could not save generated definition: {}".format(session["path"]))
    _bind_grasshopper_document_path(ghdoc, session["path"])
    save_session_metadata(session)
    session["dirty"] = False
    return session["path"]


def solve_session():
    session = _ensure_session_schema(get_active_session(required=True))
    if session.get("busy"):
        session["debug"]["skip_count"] += 1
        _debug(session, "solve skipped; session is busy")
        return session
    ghdoc = session.get("ghdoc")
    if ghdoc is None:
        raise AssemblySessionError("Active session has no GH document.")
    session["busy"] = True
    try:
        ghdoc.ExpireSolution()
        ghdoc.NewSolution(True)
        _refresh_runtime_serials(session)
        session["debug"]["solve_count"] += 1
        _debug(session, "solve #{} complete; tracking {} object(s), trigger object(s)={}".format(
            session["debug"]["solve_count"],
            len(_referenced_object_ids(session)),
            ",".join(_short_id(object_id) for object_id in _trigger_object_ids(session)) or "none",
        ))
        return session
    finally:
        session["busy"] = False


def _schedule_changed_session_solve(command_name=None):
    import Rhino

    sticky = _sticky()
    session = get_active_session(False)
    if session is not None:
        _ensure_session_schema(session)
        session["debug"]["scheduled_count"] += 1
        session["debug"]["last_command"] = command_name
        _debug(session, "schedule request #{} after command={!r}; trigger object(s)={}".format(
            session["debug"]["scheduled_count"],
            command_name,
            ",".join(_short_id(object_id) for object_id in _trigger_object_ids(session)) or "none",
        ))
    if sticky.get(IDLE_SOLVE_HANDLER_KEY) is not None:
        if session is not None:
            session["debug"]["skip_count"] += 1
            _debug(session, "idle solve already scheduled; skipping duplicate schedule")
        return

    def on_idle(sender, event):
        try:
            Rhino.RhinoApp.Idle -= on_idle
        except Exception:
            pass
        sticky.pop(IDLE_SOLVE_HANDLER_KEY, None)
        session = get_active_session(False)
        if session is None:
            return
        _ensure_session_schema(session)
        session["debug"]["idle_count"] += 1
        if session.get("busy"):
            session["debug"]["skip_count"] += 1
            _debug(session, "idle #{} skipped; session busy".format(session["debug"]["idle_count"]))
            return
        changed = _trigger_objects_changed(session)
        if not changed:
            session["debug"]["skip_count"] += 1
            ignored = _changed_object_ids(session, session.get("controlled_objects", {}).keys())
            _debug(session, "idle #{} skipped; no trigger object changed; controlled changes ignored={}".format(
                session["debug"]["idle_count"],
                ",".join(_short_id(object_id) for object_id in ignored) or "none",
            ))
            _refresh_runtime_serials(session)
            return
        _debug(session, "idle #{} solving; changed trigger object(s)={}".format(
            session["debug"]["idle_count"],
            ",".join(_short_id(object_id) for object_id in changed),
        ))
        try:
            from assembly import generate_definition

            recreate_session_document(session)
            generate_definition.rebuild_session_definition(session, save=True)
            solve_session()
            _debug(session, "rebuilt and solved after Rhino object change")
        except Exception as error:
            session["debug"]["skip_count"] += 1
            _debug(session, "solve after object change failed: {}".format(error))

    sticky[IDLE_SOLVE_HANDLER_KEY] = on_idle
    Rhino.RhinoApp.Idle += on_idle


def _command_name(event):
    for name in ("CommandEnglishName", "CommandName"):
        try:
            value = getattr(event, name)
            if value:
                return str(value)
        except Exception:
            pass
    return None


def _end_command_handler(sender, event):
    session = get_active_session(False)
    command_name = _command_name(event)
    if session is not None:
        _ensure_session_schema(session)
        session["debug"]["end_command_count"] += 1
        _debug(session, "EndCommand #{} command={!r}".format(session["debug"]["end_command_count"], command_name))
    _schedule_changed_session_solve(command_name)


def _close_document_handler(sender, event):
    reset_session(remove_document=False)


def _subscribe_updates():
    import Rhino

    sticky = _sticky()
    old_handlers = sticky.pop(HANDLERS_KEY, ())
    if len(old_handlers) >= 1:
        try:
            Rhino.Commands.Command.EndCommand -= old_handlers[0]
        except Exception:
            pass
    if len(old_handlers) >= 2:
        try:
            Rhino.RhinoDoc.CloseDocument -= old_handlers[1]
        except Exception:
            pass
    Rhino.Commands.Command.EndCommand += _end_command_handler
    Rhino.RhinoDoc.CloseDocument += _close_document_handler
    sticky[HANDLERS_KEY] = (_end_command_handler, _close_document_handler)


def _unsubscribe_updates():
    import Rhino

    sticky = _sticky()
    idle_handler = sticky.pop(IDLE_SOLVE_HANDLER_KEY, None)
    if idle_handler is not None:
        try:
            Rhino.RhinoApp.Idle -= idle_handler
        except Exception:
            pass
    handlers = sticky.pop(HANDLERS_KEY, ())
    if len(handlers) >= 1:
        try:
            Rhino.Commands.Command.EndCommand -= handlers[0]
        except Exception:
            pass
    if len(handlers) >= 2:
        try:
            Rhino.RhinoDoc.CloseDocument -= handlers[1]
        except Exception:
            pass


def clear_saved_sessions(rhino_doc=None):
    removed = []
    for metadata_path in _candidate_metadata_paths(rhino_doc or _active_rhino_doc()):
        definition_path = metadata_path.replace(".assembly.json", ".ghx")
        for path in (metadata_path, definition_path):
            if _delete_file_if_exists(path):
                removed.append(path)
    return removed


def reset_session(*, remove_document=True, remove_metadata=False):
    _unsubscribe_updates()
    session = _sticky().pop(STICKY_KEY, None)
    removed_files = []
    if session is not None and remove_metadata:
        removed_files.extend(_delete_session_files(session))
    if session is None:
        if remove_metadata:
            removed_files.extend(clear_saved_sessions())
        return False

    ghdoc = session.get("ghdoc")
    if remove_document and ghdoc is not None:
        try:
            api = _load_grasshopper()
            try:
                api["Instances"].DocumentServer.RemoveDocument(ghdoc)
            except Exception:
                pass
            try:
                ghdoc.Dispose()
            except Exception:
                pass
        except Exception:
            try:
                ghdoc.Dispose()
            except Exception:
                pass
    return True


def session_summary(session=None):
    session = session or get_active_session(False)
    if session is None:
        return "No active AssemblyGH session."
    _ensure_session_schema(session)
    return "AssemblyGH session {}: {} mate(s), {} joint(s), {} body(s), {} controlled object(s), path={}".format(
        session.get("id", "")[:8],
        len(session.get("mates", [])),
        len(session.get("joints", [])),
        len(session.get("bodies", {})),
        len(session.get("controlled_objects", {})),
        session.get("path"),
    )
