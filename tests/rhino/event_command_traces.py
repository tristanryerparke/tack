import Rhino
import System
import rhinoscriptsyntax as rs
import scriptcontext as sc


STATE_KEY = "Tack.EventCommandTrace.State"
TEST_OBJECT_KEY = "Tack.EventCommandTrace.Object"


def _state():
    state = sc.sticky.get(STATE_KEY)
    assert state is not None, "Event trace is not set up"
    return state


def _box(minimum, maximum):
    x0, y0, z0 = minimum
    x1, y1, z1 = maximum
    return rs.AddBox(
        [
            (x0, y0, z0),
            (x1, y0, z0),
            (x1, y1, z0),
            (x0, y1, z0),
            (x0, y0, z1),
            (x1, y0, z1),
            (x1, y1, z1),
            (x0, y1, z1),
        ]
    )


def _mark(doc, object_id):
    obj = doc.Objects.Find(object_id)
    assert obj is not None
    attributes = obj.Attributes.Duplicate()
    attributes.UserDictionary.Set(TEST_OBJECT_KEY, True)
    assert doc.Objects.ModifyAttributes(obj.Id, attributes, True)


def _is_marked(obj):
    try:
        return bool(obj.Attributes.UserDictionary[TEST_OBJECT_KEY])
    except Exception:
        return False


def _delete_fixture_objects(doc, object_ids):
    ids = {str(object_id) for object_id in object_ids if object_id is not None}
    ids.update(
        str(obj.Id)
        for obj in doc.Objects
        if obj is not None and _is_marked(obj)
    )
    deleted = 0
    for value in ids:
        obj = doc.Objects.Find(System.Guid.Parse(value))
        if obj is not None and doc.Objects.Delete(obj.Id, True):
            deleted += 1
    return deleted


def _anchor(bbox_analysis, obj):
    return (
        bbox_analysis.ANCHOR_TYPE,
        bbox_analysis.CENTER_INDEX,
        dict(bbox_analysis.anchors(obj))[bbox_analysis.CENTER_INDEX],
    )


def _point(point):
    if point is None:
        return None
    return [round(point.X, 6), round(point.Y, 6), round(point.Z, 6)]


def _center(obj):
    if obj is None:
        return None
    try:
        bounding_box = obj.Geometry.GetBoundingBox(True)
    except Exception:
        return None
    return bounding_box.Center if bounding_box.IsValid else None


def _same_point(left, right, tolerance=1e-7):
    return left is not None and right is not None and left.DistanceTo(right) <= tolerance


def _next_sequence(state):
    state["sequence"] += 1
    return state["sequence"]


def _object_data(state, obj):
    if obj is None:
        return None
    metadata = state["metadata"]
    try:
        geometry = obj.Geometry
        vertices = getattr(geometry, "Vertices", None)
        return {
            "id": str(obj.Id),
            "geometry": type(geometry).__name__,
            "center": _point(_center(obj)),
            "vertex_count": int(vertices.Count) if vertices is not None else None,
            "child_link_ids": sorted(metadata.read_links(obj)),
            "parent_link_ids": sorted(metadata.read_parent_links(obj)),
        }
    except Exception as error:
        return {
            "id": str(getattr(obj, "Id", "unavailable")),
            "error": type(error).__name__,
        }


def _runtime_state_data(state):
    link_state = state["runtime"].states(state["doc"]).get(state["link_id"])
    if link_state is None:
        return None
    return {
        "parent_id": str(link_state.get("parent_id")),
        "child_id": str(link_state.get("child_id")),
        "busy": bool(link_state.get("busy")),
        "broken": bool(link_state.get("broken")),
        "pending_ids": list(link_state.get("replacement_pending_ids", ())),
        "reconcile_roles": list(
            link_state.get("replacement_reconcile_roles", ())
        ),
    }


def _record_event(label, event, old_obj=None, new_obj=None):
    state = _state()
    if state["scenario"] is None:
        return
    doc = state["doc"]
    object_id = getattr(event, "ObjectId", None)
    if label == "AddRhinoObject" and object_id is not None:
        state["fixture_ids"].append(object_id)
    the_object = getattr(event, "TheObject", None)
    lookup = state["utils"].find_object(doc, object_id)
    entry = {
        "sequence": _next_sequence(state),
        "kind": "event",
        "scenario": state["scenario"],
        "event": label,
        "args_type": type(event).__name__,
        "undo_active": bool(getattr(doc, "UndoActive", False)),
        "redo_active": bool(getattr(doc, "RedoActive", False)),
        "object_id": str(object_id) if object_id is not None else None,
        "document_lookup": _object_data(state, lookup),
        "the_object": _object_data(state, the_object),
        "old_object": _object_data(state, old_obj),
        "new_object": _object_data(state, new_obj),
        "state_before_handler": _runtime_state_data(state),
    }
    state["trace"].append(entry)
    print(
        "TRACE {scenario} #{sequence} {event} id={object_id} "
        "undo={undo_active} lookup={lookup} the={the_id} old={old_id} new={new_id}".format(
            scenario=entry["scenario"],
            sequence=entry["sequence"],
            event=label,
            object_id=entry["object_id"],
            undo_active=entry["undo_active"],
            lookup=entry["document_lookup"] is not None,
            the_id=(entry["the_object"] or {}).get("id"),
            old_id=(entry["old_object"] or {}).get("id"),
            new_id=(entry["new_object"] or {}).get("id"),
        )
    )


def trace_replace(sender, event):
    _record_event(
        "ReplaceRhinoObject",
        event,
        old_obj=getattr(event, "OldRhinoObject", None),
        new_obj=getattr(event, "NewRhinoObject", None),
    )


def trace_add(sender, event):
    _record_event("AddRhinoObject", event)


def trace_delete(sender, event):
    _record_event("DeleteRhinoObject", event)


def trace_undelete(sender, event):
    _record_event("UndeleteRhinoObject", event)


def traced_maintain_link(*args, **kwargs):
    state = _state()
    link_state = args[1]
    child_before = state["utils"].find_object(
        state["doc"], link_state.get("child_id")
    )
    center_before = _center(child_before)
    broken_before = bool(link_state.get("broken"))
    pending_before = list(link_state.get("replacement_pending_ids", ()))
    reconcile_before = list(link_state.get("replacement_reconcile_roles", ()))
    before_inspection = state["link"].inspect_link(state["doc"], link_state)
    undo_or_redo_before = state["utils"].undo_or_redo(state["doc"])
    result = state["original_maintain_link"](*args, **kwargs)
    child_after = state["utils"].find_object(
        state["doc"], link_state.get("child_id")
    )
    center_after = _center(child_after)
    entry = {
        "sequence": _next_sequence(state),
        "kind": "maintain",
        "scenario": state["scenario"],
        "result": result is not None,
        "child_center_before": _point(center_before),
        "child_center_after": _point(center_after),
        "child_updated_by_tack": (
            center_before is not None
            and center_after is not None
            and not _same_point(center_before, center_after)
        ),
        "broken_before": broken_before,
        "broken_after": bool(link_state.get("broken")),
        "undo_or_redo_before": undo_or_redo_before,
        "target_child_anchor_before": _point(
            before_inspection["target_child_anchor"]
            if before_inspection is not None
            else None
        ),
        "correction_length_before": (
            round(
                before_inspection["target_child_anchor"].DistanceTo(
                    before_inspection["child_anchor"]
                ),
                6,
            )
            if before_inspection is not None
            else None
        ),
        "pending_before": pending_before,
        "pending_after": list(link_state.get("replacement_pending_ids", ())),
        "reconcile_before": reconcile_before,
        "reconcile_after": list(
            link_state.get("replacement_reconcile_roles", ())
        ),
        "state_after": _runtime_state_data(state),
    }
    state["trace"].append(entry)
    print(
        "MAINTAIN {scenario} #{sequence} result={result} "
        "child_updated={child_updated_by_tack} undo={undo_or_redo_before} "
        "correction={correction_length_before} broken={broken_before}->{broken_after} "
        "pending={pending_before}->{pending_after}".format(**entry)
    )
    return result


def traced_break_link(link_state, reason):
    state = _state()
    if state["utils"].undo_or_redo(state["doc"]) or link_state.get("broken"):
        return
    link_state["broken"] = True
    entry = {
        "sequence": _next_sequence(state),
        "kind": "break",
        "scenario": state["scenario"],
        "reason": reason,
        "state": _runtime_state_data(state),
    }
    state["trace"].append(entry)
    print("BREAK {scenario} #{sequence} reason={reason}".format(**entry))


def setup_trace():
    if sc.sticky.get(STATE_KEY) is not None:
        finish_trace()

    import importlib
    import tack

    importlib.reload(tack).reload()

    import tack.analysis.bbox as bbox_analysis
    from tack import handlers
    from tack import link
    from tack import metadata
    from tack import runtime
    from tack import utils

    doc = sc.doc
    assert doc is not None, "Open a Rhino document before running this test"

    handlers.unsubscribe()
    runtime.stop_runtime(doc)
    _delete_fixture_objects(doc, ())

    parent_id = _box((0, 0, 0), (10, 10, 10))
    child_id = _box((20, 0, 0), (30, 10, 10))
    cutter_id = _box((6, 0, 0), (20, 10, 10))
    assert parent_id is not None and child_id is not None and cutter_id is not None
    fixture_ids = [parent_id, child_id, cutter_id]
    for object_id in fixture_ids:
        _mark(doc, object_id)

    parent = doc.Objects.Find(parent_id)
    child = doc.Objects.Find(child_id)
    link_id = metadata.write_link(
        doc,
        parent_id,
        child_id,
        _anchor(bbox_analysis, parent),
        _anchor(bbox_analysis, child),
    )
    assert link_id is not None
    assert runtime.start_runtime(doc, parent_id, child_id, link_id)

    state = {
        "doc": doc,
        "handlers": handlers,
        "link": link,
        "metadata": metadata,
        "runtime": runtime,
        "utils": utils,
        "bbox_analysis": bbox_analysis,
        "link_id": link_id,
        "cutter_id": cutter_id,
        "fixture_ids": fixture_ids,
        "trace": [],
        "scenarios": [],
        "scenario": None,
        "active_scenario": None,
        "sequence": 0,
        "original_maintain_link": link.maintain_link,
        "original_break_link": link.break_link,
        "trace_handlers": (
            trace_replace,
            trace_add,
            trace_delete,
            trace_undelete,
        ),
    }
    sc.sticky[STATE_KEY] = state
    Rhino.RhinoDoc.ReplaceRhinoObject += trace_replace
    Rhino.RhinoDoc.AddRhinoObject += trace_add
    Rhino.RhinoDoc.DeleteRhinoObject += trace_delete
    Rhino.RhinoDoc.UndeleteRhinoObject += trace_undelete
    link.maintain_link = traced_maintain_link
    link.break_link = traced_break_link
    handlers.subscribe()
    print(
        "TRACE SETUP link={} parent={} child={} cutter={}".format(
            link_id, parent_id, child_id, cutter_id
        )
    )


def _current_objects(state):
    link_state = state["runtime"].states(state["doc"]).get(state["link_id"])
    if link_state is None:
        return None, None
    return (
        state["utils"].find_object(state["doc"], link_state.get("parent_id")),
        state["utils"].find_object(state["doc"], link_state.get("child_id")),
    )


def _begin_scenario(state, name):
    assert state["scenario"] is None, "Another trace scenario is active"
    parent_before, child_before = _current_objects(state)
    state["scenario"] = name
    state["active_scenario"] = {
        "name": name,
        "trace_start": len(state["trace"]),
        "parent_id_before": str(parent_before.Id) if parent_before else None,
        "parent_center_before": _point(_center(parent_before)),
        "child_center_before": _point(_center(child_before)),
    }
    print("SCENARIO {} START".format(name))


def _finish_scenario(state, command_result, created_ids):
    active = state["active_scenario"]
    assert active is not None, "No trace scenario is active"
    state["fixture_ids"].extend(created_ids)
    parent_after, child_after = _current_objects(state)
    link_state = state["runtime"].states(state["doc"]).get(state["link_id"])
    entries = state["trace"][active["trace_start"] :]
    summary = {
        "name": active["name"],
        "command_result": bool(command_result),
        "parent_id_before": active["parent_id_before"],
        "parent_id_after": str(parent_after.Id) if parent_after else None,
        "parent_center_before": active["parent_center_before"],
        "parent_center_after": _point(_center(parent_after)),
        "child_center_before": active["child_center_before"],
        "child_center_after": _point(_center(child_after)),
        "broken_after": bool(link_state.get("broken")) if link_state else None,
        "event_counts": {
            label: sum(
                1
                for entry in entries
                if entry["kind"] == "event" and entry["event"] == label
            )
            for label in (
                "ReplaceRhinoObject",
                "AddRhinoObject",
                "DeleteRhinoObject",
                "UndeleteRhinoObject",
            )
        },
        "child_update_count": sum(
            1
            for entry in entries
            if entry["kind"] == "maintain" and entry["child_updated_by_tack"]
        ),
        "entries": entries,
    }
    state["scenarios"].append(summary)
    state["scenario"] = None
    state["active_scenario"] = None
    print(
        "SCENARIO {name} END events={event_counts} child_updates={child_update_count} "
        "parent={parent_center_before}->{parent_center_after} "
        "child={child_center_before}->{child_center_after} broken={broken_after}".format(
            **summary
        )
    )
    assert summary["command_result"], summary
    return summary


def _prepare_top_level_scenario(name):
    state = _state()
    _begin_scenario(state, name)
    print("{} prepared for top-level Rhino command".format(name))
    return state


def arm_move_parent():
    state = _prepare_top_level_scenario("move_parent")
    link_state = state["runtime"].states(state["doc"])[state["link_id"]]
    rs.UnselectAllObjects()
    assert rs.SelectObject(link_state["parent_id"])


def arm_undo_move():
    _prepare_top_level_scenario("undo_move")


def arm_move_parent_face():
    state = _prepare_top_level_scenario("move_parent_face")
    link_state = state["runtime"].states(state["doc"])[state["link_id"]]
    parent_obj = state["utils"].find_object(
        state["doc"], link_state["parent_id"]
    )
    assert parent_obj is not None
    face_index = max(
        range(parent_obj.Geometry.Faces.Count),
        key=lambda index: parent_obj.Geometry.Faces[index]
        .GetBoundingBox(True)
        .Center.X,
    )
    component = Rhino.Geometry.ComponentIndex(
        Rhino.Geometry.ComponentIndexType.BrepFace,
        face_index,
    )
    rs.UnselectAllObjects()
    assert parent_obj.SelectSubObject(component, True, True, True) > 0


def arm_boolean_difference_parent():
    state = _prepare_top_level_scenario("boolean_difference_parent")
    link_state = state["runtime"].states(state["doc"])[state["link_id"]]
    rs.UnselectAllObjects()
    return {
        "parent_id": str(link_state["parent_id"]),
        "cutter_id": str(state["cutter_id"]),
    }


def collect_deferred_scenario():
    state = _state()
    assert state["scenario"] is not None, "No top-level scenario is active"
    parent, _ = _current_objects(state)
    if parent is not None:
        parent.UnselectAllSubObjects()
    # Deferred solving (tack.scheduler) drains on RhinoApp.Idle, which does
    # not fire while the watcher holds the UI thread between steps. Pump it
    # here so each scenario captures its own maintain calls.
    from tack import scheduler

    scheduler.solve_now(state["doc"])
    return _finish_scenario(state, True, [])


def finish_trace():
    state = sc.sticky.pop(STATE_KEY, None)
    if state is None:
        return None
    state["scenario"] = None
    result = {
        "name": "four_command_event_trace",
        "link_id": state["link_id"],
        "scenarios": state["scenarios"],
    }
    handlers = state["handlers"]
    runtime = state["runtime"]
    handlers.unsubscribe()
    trace_handlers = state.get("trace_handlers")
    if trace_handlers is None:
        old_globals = getattr(state["link"].maintain_link, "__globals__", {})
        trace_handlers = tuple(
            old_globals.get(name)
            for name in (
                "trace_replace",
                "trace_add",
                "trace_delete",
                "trace_undelete",
            )
        )
    for event, handler in zip(
        (
            Rhino.RhinoDoc.ReplaceRhinoObject,
            Rhino.RhinoDoc.AddRhinoObject,
            Rhino.RhinoDoc.DeleteRhinoObject,
            Rhino.RhinoDoc.UndeleteRhinoObject,
        ),
        trace_handlers,
    ):
        if handler is None:
            continue
        try:
            event -= handler
        except ValueError:
            pass
    state["link"].maintain_link = state["original_maintain_link"]
    state["link"].break_link = state["original_break_link"]
    runtime.stop_runtime(state["doc"])
    deleted = _delete_fixture_objects(state["doc"], state["fixture_ids"])
    restored = 0
    for saved_link in state["metadata"].all_links(state["doc"]):
        if runtime.start_runtime(
            state["doc"],
            saved_link["parent_id"],
            saved_link["child_id"],
            saved_link["link_id"],
        ):
            restored += 1
    handlers.subscribe()
    state["doc"].Views.Redraw()
    print("TRACE CLEANUP deleted={} restored={}".format(deleted, restored))
    return result
