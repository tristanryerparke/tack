import Rhino
import System.Windows.Forms

import tack.analysis.bbox as bbox_analysis
import tack.analysis.polyline_vertex as polyline_vertex_analysis
import tack.analysis.vertex as vertex_analysis
from tack import metadata
from tack import runtime
from tack import utils


_ANCHOR_ANALYZERS = {
    bbox_analysis.ANCHOR_TYPE: bbox_analysis,
    polyline_vertex_analysis.ANCHOR_TYPE: polyline_vertex_analysis,
    vertex_analysis.ANCHOR_TYPE: vertex_analysis,
}


def break_link(state, reason):
    if utils.undo_or_redo(Rhino.RhinoDoc.ActiveDoc):
        if utils.DEBUG:
            print("[Tack anchor] suppressing break during undo/redo")
        return
    if state.get("broken"):
        return
    state["broken"] = True
    state.pop("replacement_pending_ids", None)
    state.pop("replacement_reconcile_roles", None)
    message = (
        "The Tack link between objects\n"
        "{} (parent) --> {} (child)\n"
        "was broken.\n\n{}"
    ).format(state.get("parent_id"), state.get("child_id"), reason)
    System.Windows.Forms.MessageBox.Show(
        message,
        "Tack: anchor link broken",
        System.Windows.Forms.MessageBoxButtons.OK,
        System.Windows.Forms.MessageBoxIcon.Warning,
    )


def _restore_link(state):
    state["broken"] = False


def inspect_link(doc, state, parent_obj=None, child_obj=None):
    parent = parent_obj or utils.find_object(doc, state["parent_id"])
    child = child_obj or utils.find_object(doc, state["child_id"])
    link = (
        metadata.read_link(child, state["link_id"])
        if child is not None
        else None
    )
    link = link or state.get("link")
    if parent is None or child is None or link is None:
        return None

    parent_anchor_data = link["parent_anchor"]
    child_anchor_data = link["child_anchor"]
    parent_analyzer = _ANCHOR_ANALYZERS.get(
        parent_anchor_data["anchor_type"]
    )
    child_analyzer = _ANCHOR_ANALYZERS.get(
        child_anchor_data["anchor_type"]
    )
    if parent_analyzer is None or child_analyzer is None:
        return None
    try:
        parent_anchor = parent_analyzer.resolve(parent, parent_anchor_data)
        child_anchor = child_analyzer.resolve(child, child_anchor_data)
        offset = Rhino.Geometry.Vector3d(*(link.get("offset") or (0, 0, 0)))
    except Exception:
        return None
    if parent_anchor is None or child_anchor is None:
        return None
    return {
        "parent": parent,
        "child": child,
        "link": link,
        "parent_anchor": parent_anchor,
        "child_anchor": child_anchor,
        "target_child_anchor": parent_anchor + offset,
        "correction": Rhino.Geometry.Transform.Translation(
            parent_anchor + offset - child_anchor
        ),
    }


def _refresh_anchor_snapshots(state, result):
    for role in ("parent", "child"):
        anchor = result["link"][role + "_anchor"]
        analyzer = _ANCHOR_ANALYZERS.get(anchor["anchor_type"])
        if analyzer is not None:
            state[role + "_anchors"] = analyzer.anchors(result[role])


def _stored_link(doc, state, child_obj=None):
    child = child_obj or utils.find_object(doc, state["child_id"])
    link = (
        metadata.read_link(child, state["link_id"])
        if child is not None
        else None
    )
    return link or state.get("link")


def _adopt_candidate(
    doc,
    state,
    role,
    candidate,
    link,
):
    if candidate is None or link is None:
        return False

    tolerance = max(doc.ModelAbsoluteTolerance, 1e-7)
    anchor = link[role + "_anchor"]
    analyzer = _ANCHOR_ANALYZERS.get(anchor["anchor_type"])
    if analyzer is None:
        return False

    old_anchors = state.get(role + "_anchors")
    if old_anchors is None:
        return False
    new_anchors, new_index = analyzer.replacement_anchor(
        candidate,
        anchor,
        old_anchors,
        tolerance,
    )
    if (
        new_index is None
        and utils.same_id(candidate.Id, state[role + "_id"])
        and role in state.get("replacement_reconcile_roles", ())
        and len(new_anchors) == len(old_anchors)
    ):
        candidate_indexes = dict(new_anchors)
        saved_index = int(anchor["index"])
        if saved_index in candidate_indexes:
            new_index = saved_index
            if utils.DEBUG:
                print(
                    "[Tack anchor] accepting same-topology moved {} anchor index={}".format(
                        role,
                        saved_index,
                    )
                )

    if utils.DEBUG:
        old_index = int(anchor["index"])
        old_points = dict(old_anchors)
        new_points = dict(new_anchors)
        print(
            "[Tack anchor] resolve final candidate role={} anchor_type={} analysis_changed={} saved_count={} candidate_count={} saved_index={} candidate_index={} saved_anchor={} candidate_anchor={}".format(
                role,
                anchor["anchor_type"],
                len(old_anchors) != len(new_anchors),
                len(old_anchors),
                len(new_anchors),
                old_index,
                new_index,
                utils.debug_point(old_points.get(old_index)),
                utils.debug_point(new_points.get(new_index)),
            )
        )

    if new_index is None:
        return False

    was_busy = state.get("busy", False)
    state["busy"] = True
    try:
        state[role + "_id"] = candidate.Id
        new_anchor = dict(new_anchors)[new_index]
        metadata.update_anchor(
            doc,
            state,
            link,
            role,
            anchor["anchor_type"],
            new_index,
            new_anchor,
        )
        state[role + "_anchors"] = new_anchors
        runtime.clear_replacement_pending(state, role)
        _restore_link(state)
    finally:
        state["busy"] = was_busy
    if utils.DEBUG:
        print(
            "[Tack anchor] adopted replacement role={} id={}".format(
                role, state[role + "_id"]
            )
        )
    return True


def _candidate(doc, event, event_name, object_ids):
    # Replacement reconciliation runs after the event, so do not try to
    # recover an old object by ID. Only use an object explicitly supplied by
    # the event; command-end reconciliation discovers replacements through metadata.
    if event_name == "DeleteRhinoObject":
        return None
    return utils.event_object(doc, event, object_ids=())


def _adopt_event_candidate(doc, state, candidate, parent_obj, child_obj):
    # Same-ID replacements still need anchor validation even when advanced
    # reconciliation is disabled. Only different-ID candidates require the
    # advanced replacement path.
    if candidate is None:
        return None, parent_obj, child_obj
    role = metadata.candidate_role(state, candidate)
    same_id = role is not None and utils.same_id(
        candidate.Id,
        state[role + "_id"],
    )
    if role is None or (
        not state.get("broken")
        and same_id
        and role not in state.get("replacement_reconcile_roles", ())
    ):
        return role, parent_obj, child_obj
    if not utils.ADVANCED_RECONCILIATION and not same_id:
        return role, parent_obj, child_obj

    link = _stored_link(doc, state, child_obj=child_obj)
    if not _adopt_candidate(doc, state, role, candidate, link):
        return role, parent_obj, child_obj
    if role == "parent":
        parent_obj = candidate
    else:
        child_obj = candidate
    return role, parent_obj, child_obj


def event_may_affect_link(
    doc,
    state,
    event,
    event_name,
    object_ids,
):
    if any(
        utils.same_id(object_id, state[role + "_id"])
        for object_id in object_ids
        for role in ("parent", "child")
    ):
        return True

    if not utils.ADVANCED_RECONCILIATION:
        return False
    candidate = _candidate(doc, event, event_name, object_ids)
    return metadata.candidate_role(state, candidate) is not None


def maintain_link(
    doc,
    state,
    event=None,
    event_name=None,
    parent_obj=None,
    child_obj=None,
    object_ids=None,
    quiet=True,
):
    if doc is None or state is None or state.get("busy"):
        return None

    object_ids = list(object_ids or utils.event_object_ids(event))
    dirty_roles = set(state.pop("dirty_roles", ()))

    pending_failed_roles = set()
    for pending_role in tuple(
        state.get("replacement_reconcile_roles", ())
    ):
        pending_id = state.get(pending_role + "_id")
        pending_candidate = utils.find_object(doc, pending_id)
        if pending_candidate is None:
            continue
        candidate_role, parent_obj, child_obj = _adopt_event_candidate(
            doc,
            state,
            pending_candidate,
            parent_obj,
            child_obj,
        )
        if (
            candidate_role == pending_role
            and pending_role
            in state.get("replacement_reconcile_roles", ())
        ):
            pending_failed_roles.add(pending_role)

    related = any(
        utils.same_id(object_id, state[role + "_id"])
        for object_id in object_ids
        for role in ("parent", "child")
    )
    candidate = _candidate(doc, event, event_name, object_ids)
    candidate_role, parent_obj, child_obj = _adopt_event_candidate(
        doc,
        state,
        candidate,
        parent_obj,
        child_obj,
    )
    related = related or candidate_role is not None

    if not related:
        return None

    parent = parent_obj or utils.find_object(doc, state["parent_id"])
    child = child_obj or utils.find_object(doc, state["child_id"])

    if pending_failed_roles:
        for failed_role in pending_failed_roles:
            if (
                utils.find_object(doc, state[failed_role + "_id"])
                is not None
            ):
                runtime.clear_replacement_pending(state, failed_role)
                break_link(
                    state,
                    "The linked {} anchor could not be uniquely reconciled after the object was replaced.".format(
                        failed_role
                    ),
                )
                return None

    if parent is None or child is None:
        missing_role = "parent" if parent is None else "child"
        candidate = _candidate(doc, event, event_name, object_ids)
        candidate_role, parent_obj, child_obj = _adopt_event_candidate(
            doc,
            state,
            candidate,
            parent_obj,
            child_obj,
        )
        parent = parent_obj or utils.find_object(doc, state["parent_id"])
        child = child_obj or utils.find_object(doc, state["child_id"])

        # Advanced reconciliation scans metadata-bearing replacement objects;
        # without it, basic reconciliation can only continue with the stored
        # object IDs.
        if (
            utils.ADVANCED_RECONCILIATION
            and (parent is None or child is None)
        ):
            for candidate in metadata.candidates(doc, state):
                candidate_role, parent_obj, child_obj = _adopt_event_candidate(
                    doc,
                    state,
                    candidate,
                    parent_obj,
                    child_obj,
                )
                parent = parent_obj or utils.find_object(doc, state["parent_id"])
                child = child_obj or utils.find_object(doc, state["child_id"])
                if parent is not None and child is not None:
                    break

        if parent is None or child is None:
            # AddRhinoObject fires while a document is still being populated;
            # the other linked object may arrive in a later callback.
            if (
                related
                and event_name != "AddRhinoObject"
                and not utils.undo_or_redo(doc)
            ):
                break_link(
                    state,
                    "A linked {} object could not be recovered from callback data or saved metadata.".format(
                        missing_role
                    ),
                )
            return None

    result = inspect_link(
        doc,
        state,
        parent_obj=parent,
        child_obj=child,
    )
    if result is None:
        if not quiet:
            utils.debug("[Tack anchor] anchors could not be resolved.")
        if related and event_name != "AddRhinoObject" and not utils.undo_or_redo(doc):
            break_link(
                state,
                "The linked objects no longer expose usable anchor data.",
            )
        return None

    _refresh_anchor_snapshots(state, result)

    tolerance = max(doc.ModelAbsoluteTolerance, 1e-7)
    child_was_moved = (
        result["target_child_anchor"].DistanceTo(result["child_anchor"])
        > tolerance
    )
    if (
        utils.ALLOW_CHILD_MOVEMENT
        and "child" in dirty_roles
        and "parent" not in dirty_roles
        and child_was_moved
    ):
        result["link"]["offset"] = [
            result["child_anchor"].X - result["parent_anchor"].X,
            result["child_anchor"].Y - result["parent_anchor"].Y,
            result["child_anchor"].Z - result["parent_anchor"].Z,
        ]
        if not metadata.save_link(doc, state, result["link"]):
            break_link(
                state,
                "The Tack offset could not be saved after the child moved.",
            )
            return result
        runtime.set_display_clean(
            state,
            result["parent_anchor"],
            result["child_anchor"],
        )
        utils.debug(
            "[Tack anchor] child movement accepted; updated offset={}".format(
                result["link"]["offset"]
            )
        )
        return result

    if utils.DEBUG:
        print(
            "[Tack anchor] maintain parent={} child={}".format(
                utils.debug_point(result["parent_anchor"]),
                utils.debug_point(result["child_anchor"]),
            )
        )

    if result["target_child_anchor"].DistanceTo(result["child_anchor"]) <= max(
        doc.ModelAbsoluteTolerance, 1e-7
    ):
        runtime.set_display_clean(
            state,
            result["parent_anchor"],
            result["child_anchor"],
        )
        _restore_link(state)
        return result
    if utils.undo_or_redo(doc):
        runtime.set_display_clean(
            state,
            result["parent_anchor"],
            result["child_anchor"],
        )
        _restore_link(state)
        return result

    state["busy"] = True
    try:
        transformed_child_id = doc.Objects.Transform(
            result["child"].Id,
            result["correction"],
            True,
        )
        transformed_child = utils.find_object(doc, transformed_child_id)
        if transformed_child is None:
            utils.debug("[Tack anchor] child transformation failed.")
            return result

        # Rhino replaces the object when transforming through the object table,
        # including for locked objects. Events raised by that replacement are
        # suppressed while busy, so update the runtime relationship directly.
        state["child_id"] = transformed_child.Id
        result["child"] = transformed_child

        if not metadata.save_link(doc, state, result["link"]):
            break_link(
                state,
                "Link metadata could not be restored after moving the child.",
            )
            return result
        _refresh_anchor_snapshots(state, result)
        runtime.set_display_clean(
            state,
            result["parent_anchor"],
            result["target_child_anchor"],
        )
        utils.debug(
            "[Tack anchor] child updated parent={} child={}".format(
                result["parent"].Id,
                result["child"].Id,
            )
        )
    finally:
        state["busy"] = False
    _restore_link(state)
    return result
