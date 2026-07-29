import Rhino
import System.Windows.Forms
import scriptcontext as sc

import analysis
import conduit
import metadata
import utils
from tack_frame_picker import vertex_locations


def break_link(state, reason):
    if utils.undo_or_redo(Rhino.RhinoDoc.ActiveDoc):
        if utils.DEBUG:
            print("[Tack coincident] suppressing break during undo/redo")
        return
    if state.get("broken"):
        return
    state["broken"] = True
    active_conduit = sc.sticky.get(utils.CONDUIT_KEY)
    if active_conduit is not None:
        active_conduit.Enabled = False
    message = (
        "The coincident link between objects\n"
        "{} (parent) --> {} (child)\n"
        "was broken.\n\n{}"
    ).format(state.get("parent_id"), state.get("child_id"), reason)
    System.Windows.Forms.MessageBox.Show(
        message,
        "Tack: coincident link broken",
        System.Windows.Forms.MessageBoxButtons.OK,
        System.Windows.Forms.MessageBoxIcon.Warning,
    )


def _restore_link(state):
    state["broken"] = False
    active_conduit = sc.sticky.get(utils.CONDUIT_KEY)
    if active_conduit is not None:
        active_conduit.Enabled = True


def _try_adopt_replacement(doc, state, role, candidate):
    if candidate is None:
        return False
    child = doc.Objects.Find(state["child_id"])
    link = metadata.read_link(child) if child is not None else None
    link = link or state.get("link")
    old_state = state.get(role + "_vertices")
    if link is None or old_state is None:
        return False

    old_points = old_state[1]
    new_type, new_points, new_index = analysis.replacement_vertex(
        candidate,
        link,
        role,
        max(doc.ModelAbsoluteTolerance, 1e-7),
    )
    if new_index is None:
        if utils.DEBUG:
            print(
                "[Tack coincident] replacement candidate rejected role={} id={} old_index={} old_count={} new_count={}".format(
                    role,
                    candidate.Id,
                    int(link[role + "_vertex"]["index"]),
                    len(old_points),
                    len(new_points),
                )
            )
        return False

    was_busy = state.get("busy", False)
    state["busy"] = True
    try:
        state[role + "_id"] = candidate.Id
        metadata.update_link(
            doc,
            state,
            link,
            role,
            new_type,
            new_index,
            new_points[new_index],
        )
        state[role + "_vertices"] = (new_type, new_points)
        _restore_link(state)
    finally:
        state["busy"] = was_busy
    if utils.DEBUG:
        print(
            "[Tack coincident] adopted replacement role={} id={}".format(
                role, candidate.Id
            )
        )
    return True


def remap_vertex(doc, state, link, role, old_points, new_obj, tolerance):
    old_vertex = link[role + "_vertex"]
    old_index = int(old_vertex["index"])
    new_type, new_points, new_index = analysis.remap_vertex(
        old_points,
        new_obj,
        old_vertex,
        tolerance,
    )
    if utils.DEBUG:
        print(
            "[Tack coincident] remap role={} topology_changed={} old_count={} new_count={} old_index={} new_index={} old_point={} new_point={}".format(
                role,
                len(old_points) != len(new_points),
                len(old_points),
                len(new_points),
                old_index,
                new_index,
                utils.debug_point(old_points[old_index]) if old_index < len(old_points) else "None",
                utils.debug_point(new_points[new_index]) if new_index is not None else "None",
            )
        )
    if new_index is None:
        break_link(
            state,
            "The {} vertex could not be matched after the topology change.".format(
                role
            ),
        )
        return False
    metadata.update_link(
        doc,
        state,
        link,
        role,
        new_type,
        new_index,
        new_points[new_index],
    )
    _restore_link(state)
    return True


def reconcile(doc, state, quiet=False, parent_obj=None, child_obj=None):
    if state is None or state.get("busy"):
        return None
    result = analysis.inspect_link(
        doc,
        state,
        parent_obj=parent_obj,
        child_obj=child_obj,
    )
    if utils.DEBUG:
        print(
            "[Tack coincident] reconcile quiet={} resolved={}".format(
                quiet, result is not None
            )
        )
    if result is None:
        if not quiet:
            print("Coincident vertex link could not be resolved.")
        return None
    if utils.DEBUG:
        print(
            "[Tack coincident] reconcile parent={} child={}".format(
                utils.debug_point(result["parent_point"]),
                utils.debug_point(result["child_point"]),
            )
        )
    if result["parent_point"].DistanceTo(result["child_point"]) <= max(
        doc.ModelAbsoluteTolerance, 1e-7
    ):
        return result
    if utils.undo_or_redo(doc):
        return result

    state["busy"] = True
    try:
        if not result["child"].Geometry.Transform(result["correction"]):
            print("Child geometry translation failed.")
            return result
        if not result["child"].CommitChanges():
            print("Child changes could not be committed.")
            return result
        print(
            "[Tack coincident] child updated parent={} child={}".format(
                result["parent"].Id,
                result["child"].Id,
            )
        )
    finally:
        state["busy"] = False
    return result


def check_update(
    doc,
    state,
    object_ids=None,
    event=None,
    quiet=True,
    parent_obj=None,
    child_obj=None,
):
    if doc is None or state is None or state.get("busy"):
        return None

    object_ids = list(object_ids or [])
    candidate = analysis.event_object(doc, event)
    if candidate is None:
        for object_id in object_ids:
            candidate = doc.Objects.Find(object_id)
            if candidate is not None:
                break
    role = metadata.candidate_role(state, candidate) if candidate is not None else None
    if role is not None and (
        state.get("broken")
        or not utils.same_id(candidate.Id, state[role + "_id"])
    ):
        _try_adopt_replacement(doc, state, role, candidate)
    elif candidate is None:
        for saved_candidate in metadata.candidates(doc, state):
            saved_role = metadata.candidate_role(state, saved_candidate)
            if saved_role is not None and (
                state.get("broken")
                or not utils.same_id(
                    saved_candidate.Id, state[saved_role + "_id"]
                )
            ):
                if _try_adopt_replacement(
                    doc, state, saved_role, saved_candidate
                ):
                    break

    parent = doc.Objects.Find(state["parent_id"])
    child = doc.Objects.Find(state["child_id"])
    if parent is None or child is None:
        missing_role = "parent" if parent is None else "child"
        if (
            candidate is not None
            and role in (None, missing_role)
            and (
                state.get("broken")
                or not utils.same_id(
                    candidate.Id, state[missing_role + "_id"]
                )
            )
        ):
            _try_adopt_replacement(doc, state, missing_role, candidate)
        parent = doc.Objects.Find(state["parent_id"])
        child = doc.Objects.Find(state["child_id"])

    if parent is None or child is None:
        for candidate in metadata.candidates(doc, state):
            candidate_role = metadata.candidate_role(state, candidate)
            if candidate_role is not None and (
                state.get("broken")
                or not utils.same_id(
                    candidate.Id, state[candidate_role + "_id"]
                )
            ):
                _try_adopt_replacement(doc, state, candidate_role, candidate)
            parent = doc.Objects.Find(state["parent_id"])
            child = doc.Objects.Find(state["child_id"])
            if parent is not None and child is not None:
                break

    if parent is None or child is None:
        if (
            not utils.undo_or_redo(doc)
            and any(
                utils.same_id(object_id, state["parent_id"])
                or utils.same_id(object_id, state["child_id"])
                for object_id in object_ids
            )
        ):
            break_link(
                state,
                "A linked object could not be recovered from callback data or saved metadata.",
            )
        return None

    result = reconcile(
        doc,
        state,
        quiet=quiet,
        parent_obj=parent_obj,
        child_obj=child_obj,
    )
    if result is not None:
        _restore_link(state)
    elif role is not None:
        break_link(
            state,
            "The linked objects no longer expose usable vertex data.",
        )
    return result


def stop_runtime():
    active_conduit = sc.sticky.pop(utils.CONDUIT_KEY, None)
    if active_conduit is not None:
        active_conduit.Enabled = False
    sc.sticky.pop(utils.RUNTIME_KEY, None)


def start_runtime(parent_id, child_id):
    stop_runtime()
    doc = Rhino.RhinoDoc.ActiveDoc
    parent = doc.Objects.Find(parent_id)
    child = doc.Objects.Find(child_id)
    if parent is None or child is None:
        return False

    link = metadata.read_link(child)
    if link is None:
        return False
    state = {
        "parent_id": parent_id,
        "child_id": child_id,
        "busy": False,
        "broken": False,
        "replacement_pending_ids": [],
        "link": link,
    }
    for role, obj in (("parent", parent), ("child", child)):
        state[role + "_vertices"] = vertex_locations(obj)
    sc.sticky[utils.RUNTIME_KEY] = state

    active_conduit = conduit.CoincidentLinkConduit()
    active_conduit.Enabled = True
    sc.sticky[utils.CONDUIT_KEY] = active_conduit
    if utils.DEBUG:
        print(
            "[Tack coincident] runtime started parent={} child={} debug={}".format(
                parent_id,
                child_id,
                utils.DEBUG,
            )
        )
    doc.Views.Redraw()
    return True
