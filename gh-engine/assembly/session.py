"""Live AssemblyGH session management.

A session is the bridge between individual mate commands and one generated
Grasshopper document. Mate commands should mutate the mate records, then ask the
generator to rebuild the GH definition from those records.
"""

import json
import os
import uuid

from assembly.bodies import body_registry_from_mates
from assembly.constants import GENERATED_DIR_NAME, GENERATED_PROJECT_PREFIX, STICKY_KEY
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


def _metadata_path(definition_path):
    root, _ = os.path.splitext(definition_path)
    return root + ".assembly.json"


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
    ghdoc.Properties.ProjectFileName = display_name

    session = {
        "id": session_id,
        "name": display_name,
        "rhino_doc_id": str(getattr(rhino_doc, "DocumentId", "")),
        "ghdoc": ghdoc,
        "path": _generated_definition_path(rhino_doc, session_id),
        "mates": [],
        "bodies": {},
        "controlled_objects": {},
        "dirty": True,
        "object_runtime_serials": {},
        "version": 1,
    }
    _document_server(api).AddDocument(ghdoc)
    _document_server(api).PromoteDocument(ghdoc)
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
    ghdoc.Properties.ProjectFileName = session.get("name") or GENERATED_PROJECT_PREFIX
    api["Instances"].DocumentServer.AddDocument(ghdoc)
    api["Instances"].DocumentServer.PromoteDocument(ghdoc)
    session["ghdoc"] = ghdoc
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
        "bodies": session.get("bodies", {}),
        "controlled_objects": session.get("controlled_objects", {}),
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
    ghdoc.Properties.ProjectFileName = data.get("name") or GENERATED_PROJECT_PREFIX
    api["Instances"].DocumentServer.AddDocument(ghdoc)
    api["Instances"].DocumentServer.PromoteDocument(ghdoc)

    session = {
        "id": data.get("id") or str(uuid.uuid4()),
        "name": data.get("name") or GENERATED_PROJECT_PREFIX,
        "rhino_doc_id": data.get("rhino_doc_id", ""),
        "ghdoc": ghdoc,
        "path": data.get("path") or path.replace(".assembly.json", ".ghx"),
        "mates": data.get("mates", []),
        "bodies": data.get("bodies", {}),
        "controlled_objects": data.get("controlled_objects", {}),
        "dirty": True,
        "object_runtime_serials": {},
        "version": data.get("version", 1),
    }
    _ensure_session_schema(session)
    return session


def get_or_create_session(*, name=None):
    session = get_active_session(False)
    if session is not None and session.get("ghdoc") is not None:
        _ensure_session_schema(session)
        _refresh_runtime_serials(session)
        _subscribe_updates()
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


def _controlled_objects_from_mates(records):
    controlled = {}
    for record in records:
        for control in _effective_controls(record):
            object_id = control.get("object_id")
            if object_id:
                controlled[object_id] = control
    return controlled


def _ensure_session_schema(session):
    session.setdefault("mates", [])
    session["bodies"] = body_registry_from_mates(session.get("mates", []))
    session["controlled_objects"] = _controlled_objects_from_mates(session.get("mates", []))
    return session


def append_mate(record):
    validate_mate_record(record)
    session = _ensure_session_schema(get_or_create_session())
    session["mates"].append(record)
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


def _refresh_runtime_serials(session):
    session["object_runtime_serials"] = {
        object_id: _object_runtime_serial(object_id)
        for object_id in _referenced_object_ids(session)
    }
    return session["object_runtime_serials"]


def _referenced_objects_changed(session):
    previous = session.get("object_runtime_serials", {})
    for object_id in _referenced_object_ids(session):
        if _object_runtime_serial(object_id) != previous.get(object_id):
            return True
    return False


def save_session_definition():
    session = get_active_session(required=True)
    ghdoc = session.get("ghdoc")
    if ghdoc is None:
        raise AssemblySessionError("Active session has no GH document.")
    api = _load_grasshopper()
    io = api["GH_DocumentIO"](ghdoc)
    if not io.SaveQuiet(session["path"]):
        raise AssemblySessionError("Could not save generated definition: {}".format(session["path"]))
    save_session_metadata(session)
    session["dirty"] = False
    return session["path"]


def solve_session():
    session = get_active_session(required=True)
    ghdoc = session.get("ghdoc")
    if ghdoc is None:
        raise AssemblySessionError("Active session has no GH document.")
    ghdoc.ExpireSolution()
    ghdoc.NewSolution(True)
    _refresh_runtime_serials(session)
    return session


def _schedule_changed_session_solve():
    import Rhino

    sticky = _sticky()
    if sticky.get(IDLE_SOLVE_HANDLER_KEY) is not None:
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
        if not _referenced_objects_changed(session):
            return
        try:
            # Transactional solve: rebuild the generated GH document from current
            # metadata/live geometry snapshots, then solve/write once. This is
            # the analogue of Tack resolving current anchors before applying a
            # relationship.
            from assembly import generate_definition

            recreate_session_document(session)
            generate_definition.rebuild_session_definition(session, save=True)
            solve_session()
            print("[AssemblyGH] rebuilt and solved after Rhino object change")
        except Exception as error:
            print("[AssemblyGH] solve after object change failed: {}".format(error))

    sticky[IDLE_SOLVE_HANDLER_KEY] = on_idle
    Rhino.RhinoApp.Idle += on_idle


def _end_command_handler(sender, event):
    _schedule_changed_session_solve()


def _close_document_handler(sender, event):
    reset_session(remove_document=False)


def _subscribe_updates():
    import Rhino

    sticky = _sticky()
    if sticky.get(HANDLERS_KEY):
        return
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


def reset_session(*, remove_document=True):
    _unsubscribe_updates()
    session = _sticky().pop(STICKY_KEY, None)
    if session is None:
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
    return "AssemblyGH session {}: {} mate(s), {} body(s), {} controlled object(s), path={}".format(
        session.get("id", "")[:8],
        len(session.get("mates", [])),
        len(session.get("bodies", {})),
        len(session.get("controlled_objects", {})),
        session.get("path"),
    )
