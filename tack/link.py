import Rhino
import System.Windows.Forms

import tack.analysis.bbox as bbox_analysis
import tack.analysis.vertex as vertex_analysis
from tack import metadata
from tack import utils


_ANCHOR_ANALYZERS = {
    bbox_analysis.ANCHOR_TYPE: bbox_analysis,
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


def _stored_link(doc, state, child_obj=None, old_obj=None, role=None):
    child = child_obj or utils.find_object(doc, state["child_id"])
    link = (
        metadata.read_link(child, state["link_id"])
        if child is not None
        else None
    )
    if role == "child" and old_obj is not None:
        link = metadata.read_link(old_obj, state["link_id"]) or link
    return link or state.get("link")


def _adopt_candidate(
    doc,
    state,
    role,
    candidate,
    link,
    old_obj=None,
    replacement_id=None,
):
    if candidate is None or link is None:
        return False

    tolerance = max(doc.ModelAbsoluteTolerance, 1e-7)
    anchor = link[role + "_anchor"]
    analyzer = _ANCHOR_ANALYZERS.get(anchor["anchor_type"])
    if analyzer is None:
        return False

    if old_obj is None:
        old_anchors = state.get(role + "_anchors")
        if old_anchors is None:
            return False
        new_anchors, new_index = analyzer.replacement_anchor(
            candidate,
            anchor,
            tolerance,
        )
    else:
        old_anchors = analyzer.anchors(old_obj)
        state[role + "_anchors"] = old_anchors
        new_anchors, new_index = analyzer.remap_anchor(
            old_obj,
            candidate,
            anchor,
            tolerance,
        )

    if utils.DEBUG:
        old_index = int(anchor["index"])
        old_points = dict(old_anchors)
        new_points = dict(new_anchors)
        print(
            "[Tack anchor] remap role={} anchor_type={} analysis_changed={} old_count={} new_count={} old_index={} new_index={} old_anchor={} new_anchor={}".format(
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
        state[role + "_id"] = replacement_id or candidate.Id
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
    candidate = None
    if event_name != "DeleteRhinoObject":
        candidate = utils.event_object(doc, event, object_ids)
    if candidate is not None:
        return candidate
    for object_id in object_ids:
        candidate = utils.find_object(doc, object_id)
        if candidate is not None:
            return candidate
    return None


def _adopt_event_candidate(doc, state, candidate, parent_obj, child_obj):
    if candidate is None:
        return None, parent_obj, child_obj
    role = metadata.candidate_role(state, candidate)
    if role is None or (
        not state.get("broken")
        and utils.same_id(candidate.Id, state[role + "_id"])
    ):
        return role, parent_obj, child_obj

    link = _stored_link(doc, state, child_obj=child_obj)
    if not _adopt_candidate(doc, state, role, candidate, link):
        return role, parent_obj, child_obj
    if role == "parent":
        parent_obj = candidate
    else:
        child_obj = candidate
    return role, parent_obj, child_obj


def ignore_replacement_followup(state, event_name, object_ids):
    if event_name not in ("AddRhinoObject", "DeleteRhinoObject"):
        return False
    pending = state.get("replacement_pending_ids", [])
    if not any(str(object_id) in pending for object_id in object_ids):
        return False
    # The Add event is the first point at which Rhino has installed the
    # replacement in the document. Use it to correct the real child object.
    if event_name == "AddRhinoObject" and state.get("replacement_reconcile_roles"):
        return False
    if event_name == "AddRhinoObject":
        state.pop("replacement_pending_ids", None)
    return True


def event_may_affect_link(
    doc,
    state,
    event,
    event_name,
    object_ids,
    old_obj=None,
    new_obj=None,
):
    if old_obj is not None and new_obj is not None:
        return any(
            utils.same_id(old_obj.Id, state[role + "_id"])
            for role in ("parent", "child")
        )

    pending = state.get("replacement_pending_ids", [])
    if any(
        utils.same_id(object_id, state[role + "_id"])
        or str(object_id) in pending
        for object_id in object_ids
        for role in ("parent", "child")
    ):
        return True

    candidate = _candidate(doc, event, event_name, object_ids)
    return metadata.candidate_role(state, candidate) is not None


def maintain_link(
    doc,
    state,
    event=None,
    event_name=None,
    parent_obj=None,
    child_obj=None,
    old_obj=None,
    new_obj=None,
    object_ids=None,
    quiet=True,
):
    if doc is None or state is None or state.get("busy"):
        return None

    object_ids = list(object_ids or utils.event_object_ids(event))
    if ignore_replacement_followup(state, event_name, object_ids):
        return None

    reconcile_roles = ()
    if event_name == "AddRhinoObject" and state.get("replacement_reconcile_roles"):
        reconcile_roles = tuple(state.pop("replacement_reconcile_roles"))
        state.pop("replacement_pending_ids", None)

    related = any(
        utils.same_id(object_id, state[role + "_id"])
        for object_id in object_ids
        for role in ("parent", "child")
    )
    role = None

    if old_obj is not None and new_obj is not None:
        if utils.same_id(old_obj.Id, state["parent_id"]):
            role = "parent"
        elif utils.same_id(old_obj.Id, state["child_id"]):
            role = "child"
        if role is None:
            return None

        related = True
        state["replacement_pending_ids"] = [
            str(old_obj.Id),
            str(new_obj.Id),
        ]
        replacement_id = (
            new_obj.Id if utils.usable_object_id(new_obj.Id) else old_obj.Id
        )
        replacement_link = _stored_link(
            doc,
            state,
            child_obj=child_obj,
            old_obj=old_obj,
            role=role,
        )
        if replacement_link is None or not _adopt_candidate(
            doc,
            state,
            role,
            new_obj,
            replacement_link,
            old_obj=old_obj,
            replacement_id=replacement_id,
        ):
            break_link(
                state,
                "The {} anchor could not be matched after the geometry change.".format(
                    role
                ),
            )
            return None
        pending_roles = state.setdefault("replacement_reconcile_roles", [])
        if role not in pending_roles:
            pending_roles.append(role)
        if role == "parent":
            parent_obj = new_obj
        else:
            child_obj = new_obj
    else:
        candidate = _candidate(doc, event, event_name, object_ids)
        candidate_role, parent_obj, child_obj = _adopt_event_candidate(
            doc,
            state,
            candidate,
            parent_obj,
            child_obj,
        )
        role = role or candidate_role
        related = related or candidate_role is not None
        if event_name == "AddRhinoObject" and candidate_role is not None:
            state.pop("replacement_pending_ids", None)

    if not related:
        return None

    parent = parent_obj or utils.find_object(doc, state["parent_id"])
    child = child_obj or utils.find_object(doc, state["child_id"])

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
        role = role or candidate_role
        parent = parent_obj or utils.find_object(doc, state["parent_id"])
        child = child_obj or utils.find_object(doc, state["child_id"])

        if parent is None or child is None:
            for candidate in metadata.candidates(doc, state):
                candidate_role, parent_obj, child_obj = _adopt_event_candidate(
                    doc,
                    state,
                    candidate,
                    parent_obj,
                    child_obj,
                )
                role = role or candidate_role
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

    if reconcile_roles and not metadata.save_link(doc, state, state["link"]):
        break_link(
            state,
            "Replacement metadata could not be saved on both linked objects.",
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
            print("Tack anchors could not be resolved.")
        if related and event_name != "AddRhinoObject" and not utils.undo_or_redo(doc):
            break_link(
                state,
                "The linked objects no longer expose usable anchor data.",
            )
        return None

    if utils.DEBUG:
        print(
            "[Tack anchor] maintain parent={} child={}".format(
                utils.debug_point(result["parent_anchor"]),
                utils.debug_point(result["child_anchor"]),
            )
        )

    if event_name == "ReplaceRhinoObject" and role in state.get(
        "replacement_reconcile_roles", ()
    ):
        # ReplaceRhinoObject fires before Rhino installs the replacement. Defer
        # the correction until AddRhinoObject can modify the document's final
        # object instead of this transient replacement.
        return result

    if result["target_child_anchor"].DistanceTo(result["child_anchor"]) <= max(
        doc.ModelAbsoluteTolerance, 1e-7
    ):
        _restore_link(state)
        return result
    if utils.undo_or_redo(doc):
        _restore_link(state)
        return result

    state["busy"] = True
    try:
        if not result["child"].Geometry.Transform(result["correction"]):
            print("Child geometry translation failed.")
            return result
        if not result["child"].CommitChanges():
            print("Child changes could not be committed.")
            return result
        print("Child position updated by tack")
        if utils.DEBUG:
            print(
                "[Tack anchor] child updated parent={} child={}".format(
                    result["parent"].Id,
                    result["child"].Id,
                )
            )
    finally:
        state["busy"] = False
    _restore_link(state)
    return result
