"""Live AssemblyGH session management.

A session is the bridge between individual mate commands and one generated
Grasshopper document. Mate commands should mutate the mate records, then ask the
generator to rebuild the GH definition from those records.
"""

import os
import uuid

from assembly.constants import GENERATED_DIR_NAME, GENERATED_PROJECT_PREFIX, STICKY_KEY
from assembly.mate_records import validate_mate_record


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

    return Rhino.RhinoDoc.ActiveDoc


def _sticky():
    import scriptcontext as sc

    return sc.sticky


def _document_server(api):
    return api["Instances"].DocumentServer


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
        "controlled_objects": {},
        "dirty": True,
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


def get_or_create_session(*, name=None):
    session = get_active_session(False)
    if session is not None and session.get("ghdoc") is not None:
        return session

    api = _load_grasshopper()
    session = _new_session(api, name=name)
    _sticky()[STICKY_KEY] = session
    return session


def append_mate(record):
    validate_mate_record(record)
    session = get_or_create_session()
    session["mates"].append(record)
    for control in record.get("controls", []):
        object_id = control.get("object_id")
        if object_id:
            session["controlled_objects"][object_id] = control
    session["dirty"] = True
    return session


def replace_mates(records):
    session = get_or_create_session()
    session["mates"] = []
    session["controlled_objects"] = {}
    for record in records:
        validate_mate_record(record)
        session["mates"].append(record)
        for control in record.get("controls", []):
            object_id = control.get("object_id")
            if object_id:
                session["controlled_objects"][object_id] = control
    session["dirty"] = True
    return session


def save_session_definition():
    session = get_active_session(required=True)
    ghdoc = session.get("ghdoc")
    if ghdoc is None:
        raise AssemblySessionError("Active session has no GH document.")
    api = _load_grasshopper()
    io = api["GH_DocumentIO"](ghdoc)
    if not io.SaveQuiet(session["path"]):
        raise AssemblySessionError("Could not save generated definition: {}".format(session["path"]))
    session["dirty"] = False
    return session["path"]


def solve_session():
    session = get_active_session(required=True)
    ghdoc = session.get("ghdoc")
    if ghdoc is None:
        raise AssemblySessionError("Active session has no GH document.")
    ghdoc.ExpireSolution()
    ghdoc.NewSolution(True)
    return session


def reset_session(*, remove_document=True):
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
    return "AssemblyGH session {}: {} mate(s), {} controlled object(s), path={}".format(
        session.get("id", "")[:8],
        len(session.get("mates", [])),
        len(session.get("controlled_objects", {})),
        session.get("path"),
    )
