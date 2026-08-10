import Rhino
import scriptcontext as sc

import tack.analysis.bbox as bbox_analysis
import tack.analysis.polyline_vertex as polyline_vertex_analysis
import tack.analysis.vertex as vertex_analysis
from tack import conduit
from tack import document_runtime
from tack import metadata
from tack import utils


_ANALYZERS = {
    bbox_analysis.ANCHOR_TYPE: bbox_analysis,
    polyline_vertex_analysis.ANCHOR_TYPE: polyline_vertex_analysis,
    vertex_analysis.ANCHOR_TYPE: vertex_analysis,
}


def states(doc, create=True):
    if create:
        return document_runtime.get_value(
            doc,
            utils.RUNTIME_KEY,
            lambda _: {},
        )
    return document_runtime.try_get_value(doc, utils.RUNTIME_KEY) or {}


def has_any_runtime():
    return document_runtime.has_nonempty_value(utils.RUNTIME_KEY)


def mark_display_dirty(state):
    display = state.get("display")
    if display is None:
        state["display"] = {"dirty": True}
    else:
        display["dirty"] = True


def mark_roles_dirty(state, object_ids, candidate_role=None):
    roles = [
        role
        for role in ("parent", "child")
        if any(
            utils.same_id(object_id, state[role + "_id"])
            for object_id in object_ids
        )
    ]
    if candidate_role is not None and candidate_role not in roles:
        roles.append(candidate_role)
    if roles:
        mark_display_dirty(state)
        dirty_roles = state.setdefault("dirty_roles", [])
        for role in roles:
            if role not in dirty_roles:
                dirty_roles.append(role)
    return roles


def mark_object_ids_dirty(doc, object_ids):
    link_ids = []
    for state in states(doc, create=False).values():
        matching_roles = mark_roles_dirty(state, object_ids)
        if matching_roles:
            pending_ids = state.setdefault("replacement_pending_ids", [])
            pending_roles = state.setdefault(
                "replacement_reconcile_roles",
                [],
            )
            for object_id in object_ids:
                if not any(
                    utils.same_id(object_id, pending_id)
                    for pending_id in pending_ids
                ):
                    pending_ids.append(str(object_id))
            for role in matching_roles:
                if role not in pending_roles:
                    pending_roles.append(role)
            link_ids.append(state["link_id"])
    return link_ids


def clear_replacement_pending(state, role):
    pending_roles = state.get("replacement_reconcile_roles", [])
    if role in pending_roles:
        pending_roles.remove(role)
    if not pending_roles:
        state.pop("replacement_reconcile_roles", None)
        state.pop("replacement_pending_ids", None)


def set_display_clean(state, parent_anchor, child_anchor):
    offset = Rhino.Geometry.Vector3d(*(state["link"].get("offset") or (0, 0, 0)))
    state["display"] = {
        "dirty": False,
        "parent_anchor": Rhino.Geometry.Point3d(parent_anchor),
        "child_anchor": Rhino.Geometry.Point3d(child_anchor),
        "setup_offset_length": offset.Length,
    }


def _disable_conduit_if_unused():
    if has_any_runtime():
        return
    active_conduit = sc.sticky.pop(utils.CONDUIT_KEY, None)
    if active_conduit is not None:
        active_conduit.Enabled = False


def stop_runtime(doc):
    document_runtime.remove_value(doc, utils.RUNTIME_KEY)
    document_runtime.remove_value(doc, utils.DISPLAY_ENABLED_KEY)
    _disable_conduit_if_unused()


def remove_document(doc):
    document_runtime.remove_document(doc)
    _disable_conduit_if_unused()


def _new_state(doc, saved_link):
    parent = utils.find_object(doc, saved_link["parent_id"])
    child = utils.find_object(doc, saved_link["child_id"])
    if parent is None or child is None:
        return None

    state = {
        "link_id": saved_link["link_id"],
        "parent_id": saved_link["parent_id"],
        "child_id": saved_link["child_id"],
        "busy": False,
        "broken": False,
        "link": saved_link,
    }
    resolved_anchors = {}
    for role, obj in (("parent", parent), ("child", child)):
        anchor = saved_link[role + "_anchor"]
        analyzer = _ANALYZERS.get(anchor["anchor_type"])
        if analyzer is None:
            return None
        resolved_anchor = analyzer.resolve(obj, anchor)
        if resolved_anchor is None:
            return None
        resolved_anchors[role] = resolved_anchor
        state[role + "_anchors"] = analyzer.anchors(obj)
    set_display_clean(
        state,
        resolved_anchors["parent"],
        resolved_anchors["child"],
    )
    return state


def state_for_link(doc, saved_link):
    link_id = saved_link["link_id"]
    active_states = states(doc)
    state = next(
        (
            value
            for saved_id, value in active_states.items()
            if utils.same_id(saved_id, link_id)
        ),
        None,
    )
    if state is None:
        state = _new_state(doc, saved_link)
        if state is None:
            return None
        active_states[link_id] = state
    else:
        state["link"] = saved_link
        state["parent_id"] = saved_link["parent_id"]
        state["child_id"] = saved_link["child_id"]
    return state


def _ensure_conduit():
    active_conduit = sc.sticky.get(utils.CONDUIT_KEY)
    if active_conduit is None:
        active_conduit = conduit.TackLinkConduit()
        sc.sticky[utils.CONDUIT_KEY] = active_conduit
    active_conduit.Enabled = True


def hide_display(doc):
    if not states(doc, create=False):
        return False
    document_runtime.set_value(doc, utils.DISPLAY_ENABLED_KEY, False)
    return True


def show_display(doc):
    if not states(doc, create=False):
        return False
    document_runtime.set_value(doc, utils.DISPLAY_ENABLED_KEY, True)
    _ensure_conduit()
    return True


def start_runtime(doc, parent_id, child_id, link_id, redraw=True):
    if doc is None:
        return False
    child = utils.find_object(doc, child_id)
    saved_link = metadata.read_link(child, link_id)
    if saved_link is None or not utils.same_id(saved_link["parent_id"], parent_id):
        return False
    if state_for_link(doc, saved_link) is None:
        return False

    _ensure_conduit()
    if utils.DEBUG:
        print(
            "[Tack anchor] runtime prepared link={} parent={} child={} debug={}".format(
                link_id,
                parent_id,
                child_id,
                utils.DEBUG,
            )
        )
    if redraw:
        doc.Views.Redraw()
    return True
