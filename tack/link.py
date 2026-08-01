import Rhino
import System.Windows.Forms
import scriptcontext as sc

from tack import analysis
from tack import metadata
from tack import utils


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


def inspect_link(doc, state, parent_obj=None, child_obj=None):
    parent = parent_obj or doc.Objects.Find(state["parent_id"])
    child = child_obj or doc.Objects.Find(state["child_id"])
    link = metadata.read_link(child) if child is not None else None
    link = link or state.get("link")
    if parent is None or child is None or link is None:
        return None

    parent_vertex = link["parent_vertex"]
    child_vertex = link["child_vertex"]
    try:
        parent_point = utils.get_vertex_from_brep(parent, parent_vertex["index"])
        child_point = utils.get_vertex_from_brep(child, child_vertex["index"])
        offset = Rhino.Geometry.Vector3d(*(link.get("offset") or (0, 0, 0)))
    except Exception:
        return None
    if parent_point is None or child_point is None:
        return None
    return {
        "parent": parent,
        "child": child,
        "link": link,
        "parent_point": parent_point,
        "child_point": child_point,
        "target_child_point": parent_point + offset,
        "correction": Rhino.Geometry.Transform.Translation(
            parent_point + offset - child_point
        ),
    }


def _stored_link(doc, state, child_obj=None, old_obj=None, role=None):
    child = child_obj or doc.Objects.Find(state["child_id"])
    link = metadata.read_link(child) if child is not None else None
    if role == "child" and old_obj is not None:
        link = metadata.read_link(old_obj) or link
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
    if old_obj is None:
        old_state = state.get(role + "_vertices")
        if old_state is None:
            return False
        old_points = old_state
        new_type, new_points, new_index = analysis.replacement_vertex(
            candidate,
            link,
            role,
            tolerance,
        )
    else:
        old_points = utils.vertices_as_points(old_obj)
        state[role + "_vertices"] = old_points
        new_type, new_points, new_index = analysis.remap_vertex(
            old_obj,
            candidate,
            link[role + "_vertex"],
            tolerance,
        )

    if utils.DEBUG:
        old_index = int(link[role + "_vertex"]["index"])
        print(
            "[Tack coincident] remap role={} topology_changed={} old_count={} new_count={} old_index={} new_index={} old_point={} new_point={}".format(
                role,
                len(old_points) != len(new_points),
                len(old_points),
                len(new_points),
                old_index,
                new_index,
                utils.debug_point(old_points[old_index]) if 0 <= old_index < len(old_points) else "None",
                utils.debug_point(new_points[new_index]) if new_index is not None else "None",
            )
        )

    if new_index is None:
        return False

    was_busy = state.get("busy", False)
    state["busy"] = True
    try:
        state[role + "_id"] = replacement_id or candidate.Id
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
        candidate = doc.Objects.Find(object_id)
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

    if event_name == "AddRhinoObject" and state.get("replacement_reconcile_roles"):
        state.pop("replacement_pending_ids", None)
        state.pop("replacement_reconcile_roles", None)

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
                "The {} vertex could not be matched after the topology change.".format(
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

    parent = parent_obj or doc.Objects.Find(state["parent_id"])
    child = child_obj or doc.Objects.Find(state["child_id"])

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
        parent = parent_obj or doc.Objects.Find(state["parent_id"])
        child = child_obj or doc.Objects.Find(state["child_id"])

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
                parent = parent_obj or doc.Objects.Find(state["parent_id"])
                child = child_obj or doc.Objects.Find(state["child_id"])
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
            print("Coincident vertex link could not be resolved.")
        if related and event_name != "AddRhinoObject" and not utils.undo_or_redo(doc):
            break_link(
                state,
                "The linked objects no longer expose usable vertex data.",
            )
        return None

    if utils.DEBUG:
        print(
            "[Tack coincident] maintain parent={} child={}".format(
                utils.debug_point(result["parent_point"]),
                utils.debug_point(result["child_point"]),
            )
        )

    if event_name == "ReplaceRhinoObject" and role in state.get(
        "replacement_reconcile_roles", ()
    ):
        # ReplaceRhinoObject fires before Rhino installs the replacement. Defer
        # the correction until AddRhinoObject can modify the document's final
        # object instead of this transient replacement.
        return result

    if result["target_child_point"].DistanceTo(result["child_point"]) <= max(
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
        metadata.update_child_anchor(
            doc,
            state,
            result["link"],
            result["target_child_point"],
        )
        if utils.DEBUG:
            print(
                "[Tack coincident] child updated parent={} child={}".format(
                    result["parent"].Id,
                    result["child"].Id,
                )
            )
    finally:
        state["busy"] = False
    _restore_link(state)
    return result
