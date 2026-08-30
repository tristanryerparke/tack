"""Trace Add Link, movement, and any number of Undo commands.

Run only with persistent watcher mode because later Rhino commands must
continue forwarding handler output to the original terminal. Add Link is run
separately from Rhino so it keeps its own command/undo boundary:

    uv run rhino-watch demos/debug_analytic_plane_link_undo.py --debug --nostop
"""

import importlib
import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import Rhino
import scriptcontext as sc
from run_in_rhino.rhino_env.client import SocketConnection
from run_in_rhino.rhino_env.env import install_os_environment
from run_in_rhino.rhino_env.parasite import OutputParasite

import tack

importlib.reload(tack).reload()

from tack import plane_link
from tack import plane_link_metadata
from tack import utils
from tack import watcher


STATE_KEY = "Tack.AnalyticPlaneLink.UndoDiagnostic"
STOP_CALLBACK_KEY = "Tack.AnalyticPlaneLink.UndoDiagnosticStopCallback"


def _output(message):
    with watcher.output(True):
        print(message)


def _point(point):
    if point is None:
        return None
    return [round(point.X, 6), round(point.Y, 6), round(point.Z, 6)]


def _center(obj):
    if obj is None or obj.Geometry is None:
        return None
    bounding_box = obj.Geometry.GetBoundingBox(True)
    return bounding_box.Center if bounding_box.IsValid else None


def _object_data(obj):
    if obj is None:
        return None
    return {
        "id": str(obj.Id),
        "serial": int(obj.RuntimeSerialNumber),
        "geometry": obj.Geometry.GetType().Name,
        "center": _point(_center(obj)),
        "link_ids": sorted(plane_link_metadata.read_links(obj)),
    }


def _runtime_data(state):
    doc = state["doc"]
    return [
        {
            "link_id": link_state.get("link_id"),
            "parent_id": str(link_state.get("parent_id")),
            "child_id": str(link_state.get("child_id")),
            "busy": bool(link_state.get("busy")),
            "broken": bool(link_state.get("broken")),
            "origin": _point(link_state.get("origin")),
        }
        for link_state in plane_link.states(doc, create=False).values()
    ]


def _snapshot(label):
    state = sc.sticky.get(STATE_KEY)
    if state is None:
        return
    doc = state["doc"]
    current = {str(obj.Id): obj for obj in doc.Objects if obj is not None}
    added_ids = sorted(set(current) - state["baseline_ids"])
    missing_ids = sorted(state["baseline_ids"] - set(current))
    tracked = sorted(state["tracked_ids"] | set(added_ids))
    records = [_object_data(current.get(object_id)) for object_id in tracked]
    _output(
        "SNAPSHOT {} undo_active={} redo_active={} added_since_start={} "
        "missing_since_start={} tracked_objects={} runtime={}".format(
            label,
            bool(doc.UndoActive),
            bool(doc.RedoActive),
            added_ids,
            missing_ids,
            records,
            _runtime_data(state),
        )
    )


def _event_record(label, event, old_obj=None, new_obj=None):
    state = sc.sticky.get(STATE_KEY)
    if state is None:
        return
    object_id = getattr(event, "ObjectId", None)
    record = {
        "event": label,
        "id": str(object_id) if object_id is not None else None,
        "undo": bool(state["doc"].UndoActive),
        "redo": bool(state["doc"].RedoActive),
        "object": _object_data(getattr(event, "TheObject", None)),
        "old": _object_data(old_obj),
        "new": _object_data(new_obj),
    }
    state["events"].append(record)
    for obj in (getattr(event, "TheObject", None), old_obj, new_obj):
        if obj is not None:
            state["event_ids"].add(str(obj.Id))
    if state["phase"] != "setup":
        state["tracked_ids"].update(state["event_ids"])
        _output("OBJECT_EVENT {}".format(record))


def _replace(sender, event):
    _event_record(
        "ReplaceRhinoObject",
        event,
        getattr(event, "OldRhinoObject", None),
        getattr(event, "NewRhinoObject", None),
    )


def _add(sender, event):
    _event_record("AddRhinoObject", event)


def _delete(sender, event):
    _event_record("DeleteRhinoObject", event)


def _undelete(sender, event):
    _event_record("UndeleteRhinoObject", event)


def _command_name(event):
    return (
        getattr(event, "CommandEnglishName", None)
        or getattr(event, "EnglishName", None)
        or getattr(event, "CommandName", None)
        or "<unknown>"
    )


def _begin_command(sender, event):
    state = sc.sticky.get(STATE_KEY)
    if state is None or state["phase"] == "setup":
        return
    _output(
        "BEGIN_COMMAND {} undo_active={} redo_active={}".format(
            _command_name(event),
            bool(state["doc"].UndoActive),
            bool(state["doc"].RedoActive),
        )
    )


def _activate_relationship_trace(state):
    active_states = list(plane_link.states(state["doc"], create=False).values())
    if not active_states:
        return False
    link_state = active_states[-1]
    state["tracked_ids"].update(
        (str(link_state["parent_id"]), str(link_state["child_id"]))
    )
    state["phase"] = "active"
    state["original_maintain"] = plane_link.maintain
    plane_link.maintain = _traced_maintain
    _snapshot("after_committed_setup")
    _output("RELATIONSHIP_RUNTIME {}".format(_runtime_data(state)))
    _output("ACTION: move the parent object with Rhino's Move command.")
    return True


def _end_command(sender, event):
    state = sc.sticky.get(STATE_KEY)
    if state is None:
        return
    if state["phase"] == "setup":
        _activate_relationship_trace(state)
        return
    name = _command_name(event)
    _output(
        "END_COMMAND {} undo_active={} redo_active={}".format(
            name,
            bool(state["doc"].UndoActive),
            bool(state["doc"].RedoActive),
        )
    )
    _snapshot("end_{}".format(name))
    if name.lower() == "move":
        _output(
            "ACTION: wait for CHILD_SOLVE, verify the child moved, then run Undo once."
        )
    elif name.lower() == "undo":
        state["undo_count"] += 1
        _output(
            "ACTION: Undo {} observed; continue undoing as needed, then run "
            "demos/stop_analytic_plane_link_undo_debug.py in Rhino.".format(
                state["undo_count"]
            )
        )


def _traced_maintain(doc, link_state):
    state = sc.sticky.get(STATE_KEY)
    before_child = utils.find_object(doc, link_state.get("child_id"))
    before = _object_data(before_child)
    result = state["original_maintain"](doc, link_state)
    after_child = utils.find_object(doc, link_state.get("child_id"))
    after = _object_data(after_child)
    state["tracked_ids"].update(
        value["id"] for value in (before, after) if value is not None
    )
    _output(
        "CHILD_SOLVE result={} before={} after={} state_child_id={}".format(
            bool(result),
            before,
            after,
            link_state.get("child_id"),
        )
    )
    _snapshot("after_child_solve")
    _output("ACTION: verify the child position, then run Undo once.")
    return result


def _unsubscribe():
    state = sc.sticky.pop(STATE_KEY, None)
    if state is None:
        return
    for event, handler in state["subscriptions"]:
        try:
            event -= handler
        except Exception:
            pass
    original_maintain = state.get("original_maintain")
    if original_maintain is not None:
        plane_link.maintain = original_maintain
    sc.sticky.pop(STOP_CALLBACK_KEY, None)


def stop_trace():
    _snapshot("manual_stop")
    _output("TRACE_COMPLETE: manual stop requested; stopping watcher.")
    _unsubscribe()
    watcher.send_quit(True)


def _subscribe(doc, baseline_ids=None):
    _unsubscribe()
    subscriptions = (
        (Rhino.RhinoDoc.ReplaceRhinoObject, _replace),
        (Rhino.RhinoDoc.AddRhinoObject, _add),
        (Rhino.RhinoDoc.DeleteRhinoObject, _delete),
        (Rhino.RhinoDoc.UndeleteRhinoObject, _undelete),
        (Rhino.Commands.Command.BeginCommand, _begin_command),
        (Rhino.Commands.Command.EndCommand, _end_command),
    )
    state = {
        "doc": doc,
        "phase": "setup",
        "events": [],
        "event_ids": set(),
        "tracked_ids": set(),
        "baseline_ids": (
            set(baseline_ids)
            if baseline_ids is not None
            else {str(obj.Id) for obj in doc.Objects if obj is not None}
        ),
        "undo_count": 0,
        "subscriptions": subscriptions,
        "original_maintain": None,
    }
    sc.sticky[STATE_KEY] = state
    for event, handler in subscriptions:
        event += handler
    sc.sticky[STOP_CALLBACK_KEY] = stop_trace
    return state


def RunDiagnostic(connection, parasite):
    doc = Rhino.RhinoDoc.ActiveDoc
    if doc is None:
        print("No active Rhino document.")
        return
    baseline_ids = {str(obj.Id) for obj in doc.Objects if obj is not None}
    _subscribe(doc, baseline_ids=baseline_ids)
    print(
        "DIAGNOSTIC_START baseline_object_count={}".format(
            len(baseline_ids)
        )
    )
    print(
        "ACTION: in Rhino run _-RunPythonScript and choose:\n"
        "{}\n"
        "Complete Add Link, move the parent, and Undo as many times as needed.\n"
        "Then run stop_analytic_plane_link_undo_debug.py the same way.".format(
            os.path.join(PROJECT_ROOT, "demos", "analytic_plane_link.py")
        )
    )
    parasite.flush()


if __name__ == "__main__":
    connection = SocketConnection()
    install_os_environment(connection)
    with OutputParasite(connection) as parasite:
        RunDiagnostic(connection, parasite)
