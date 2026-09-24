"""Runtime lifecycle and display state for active Tack Links."""

from dataclasses import replace

import scriptcontext as sc

from tack.core import documents, plugin_data
from tack.core.objects import same_id
from tack.links import preferences, repository, solver, state, transforms

CONDUIT_KEY = "Tack.Conduit"
DISPLAY_KEY = "Tack.Display"


def active_conduit():
    """Return the shared cross-document Tack conduit, if installed."""
    return sc.sticky.get(CONDUIT_KEY)


def states_for(doc):
    return state.states(doc, create=False) or None


def _display_state(doc, default_enabled=True):
    return documents.get_value(
        doc,
        DISPLAY_KEY,
        lambda _: {"enabled": bool(default_enabled)},
    )


def _user_setting(doc, name, default):
    value = plugin_data.setting(name)
    if value is not None:
        return value
    return _display_state(doc).get(name, default)


def _bool_setting(doc, name, default):
    value = _user_setting(doc, name, default)
    return value if isinstance(value, bool) else default


def _number_setting(doc, name, default):
    value = _user_setting(doc, name, default)
    return (
        float(value)
        if isinstance(value, (int, float)) and not isinstance(value, bool)
        else float(default)
    )


def _set_user_setting(doc, name, value):
    if not plugin_data.set_setting(name, value):
        _display_state(doc)[name] = value


def crosshair_size(doc):
    from tack.anchors import analytic_plane

    size = _number_setting(doc, plugin_data.CROSSHAIR_SIZE, analytic_plane.CROSSHAIR_SIZE)
    return max(analytic_plane.CROSSHAIR_SIZE_MIN, min(analytic_plane.CROSSHAIR_SIZE_MAX, size))


def set_crosshair_size(doc, size):
    from tack.anchors import analytic_plane

    size = max(
        analytic_plane.CROSSHAIR_SIZE_MIN,
        min(analytic_plane.CROSSHAIR_SIZE_MAX, int(size)),
    )
    _set_user_setting(doc, plugin_data.CROSSHAIR_SIZE, float(size))
    doc.Views.Redraw()
    return size


def crosshair_thickness(doc):
    from tack.anchors import analytic_plane

    thickness = _number_setting(
        doc,
        plugin_data.CROSSHAIR_THICKNESS,
        analytic_plane.CROSSHAIR_THICKNESS,
    )
    return max(
        analytic_plane.CROSSHAIR_THICKNESS_MIN,
        min(analytic_plane.CROSSHAIR_THICKNESS_MAX, thickness),
    )


def set_crosshair_thickness(doc, thickness):
    from tack.anchors import analytic_plane

    thickness = max(
        analytic_plane.CROSSHAIR_THICKNESS_MIN,
        min(analytic_plane.CROSSHAIR_THICKNESS_MAX, int(thickness)),
    )
    _set_user_setting(doc, plugin_data.CROSSHAIR_THICKNESS, float(thickness))
    doc.Views.Redraw()
    return thickness


def show_selected_tacks_only(doc):
    return _bool_setting(doc, plugin_data.SHOW_SELECTED_TACKS_ONLY, False)


def set_show_selected_tacks_only(doc, enabled):
    enabled = bool(enabled)
    _set_user_setting(doc, plugin_data.SHOW_SELECTED_TACKS_ONLY, enabled)
    doc.Views.Redraw()
    return enabled


def highlight_selected_objects(doc):
    return _bool_setting(doc, plugin_data.HIGHLIGHT_SELECTED_OBJECTS, True)


def set_highlight_selected_objects(doc, enabled):
    enabled = bool(enabled)
    _set_user_setting(doc, plugin_data.HIGHLIGHT_SELECTED_OBJECTS, enabled)
    doc.Views.Redraw()
    return enabled


def dynamic_previews_enabled(doc):
    return _bool_setting(doc, plugin_data.DYNAMIC_PREVIEWS_ENABLED, True)


def set_dynamic_previews_enabled(doc, enabled):
    enabled = bool(enabled)
    _set_user_setting(doc, plugin_data.DYNAMIC_PREVIEWS_ENABLED, enabled)
    doc.Views.Redraw()
    return enabled


def selected_link_ids(doc):
    return _display_state(doc).get("selected_link_ids", ())


def selected_object_id(doc):
    return _display_state(doc).get("selected_object_id")


def selected_tack_id(doc):
    return _display_state(doc).get("selected_tack_id")


def set_tree_selection(doc, object_id, link_ids):
    display_state = _display_state(doc)
    display_state["selected_object_id"] = object_id
    display_state["selected_link_ids"] = tuple(link_ids)
    display_state["selected_tack_id"] = None
    doc.Views.Redraw()


def set_tack_selection(doc, link_id):
    display_state = _display_state(doc)
    display_state["selected_object_id"] = None
    display_state["selected_link_ids"] = () if link_id is None else (link_id,)
    display_state["selected_tack_id"] = link_id
    doc.Views.Redraw()


def display_enabled(doc):
    display_state = documents.try_get_value(doc, DISPLAY_KEY)
    return preferences.display_enabled(doc) if display_state is None else bool(display_state["enabled"])


def set_display_enabled(doc, enabled):
    if not state.states(doc, create=False):
        return False
    enabled = bool(enabled)
    if not preferences.set_display_enabled(doc, enabled):
        return False
    _display_state(doc)["enabled"] = enabled
    doc.Views.Redraw()
    return True


def ensure_conduit(doc, default_display_enabled=True):
    from tack.display.link_conduit import LinkedPlaneConduit

    conduit = active_conduit()
    if conduit is None:
        conduit = LinkedPlaneConduit()
        conduit.Enabled = True
        sc.sticky[CONDUIT_KEY] = conduit
    if doc is not None:
        _display_state(doc, default_display_enabled)
    return conduit


def remove_conduit():
    conduit = sc.sticky.pop(CONDUIT_KEY, None)
    if conduit is not None:
        conduit.Enabled = False
        conduit.clear_preview()


def deactivate_document(doc):
    """Remove display resources while retaining recent endpoint IDs for Undo."""
    conduit = active_conduit()
    if conduit is not None:
        conduit.forget_document(int(doc.RuntimeSerialNumber))
    documents.remove_value(doc, DISPLAY_KEY)
    if not state.has_active_states():
        remove_conduit()


def remove_runtime(doc):
    """Forget every temporary state for a closing document or full restore."""
    state.clear_states(doc)
    deactivate_document(doc)


def install(doc, link, default_display_enabled=True):
    """Start tracking one already-persisted Link in this Rhino session."""
    link_state = state.new_state(doc, link)
    if link_state is None:
        return None
    for saved_id, saved_state in list(state.states(doc).items()):
        if saved_id != link.link_id and (
            (
                same_id(saved_state.parent_id, link.parent_id)
                and same_id(saved_state.child_id, link.child_id)
            )
            or (
                same_id(saved_state.parent_id, link.child_id)
                and same_id(saved_state.child_id, link.parent_id)
            )
        ):
            state.remember_state(doc, saved_state)
    state.set_state(doc, link_state)
    saved_display_enabled = preferences.display_enabled(doc, default_display_enabled)
    ensure_conduit(doc, saved_display_enabled)
    preferences.set_display_enabled(doc, _display_state(doc, saved_display_enabled)["enabled"])
    from tack.links import lifecycle

    lifecycle.subscribe()
    doc.Views.Redraw()
    return link_state


def restore_document(doc, default_display_enabled=True):
    """Rebuild active states and the recovery log with one full document scan."""
    remove_runtime(doc)
    recovered = []
    parents, child_owners = repository.observed_metadata(doc.Objects)
    links = repository.active_observed_links(
        parents,
        child_owners,
        include_invalid=True,
    )
    for link_id, link in parents.items():
        if link_id not in links:
            state.remember_object_ids(doc, link.parent_id, link.child_id)
    for link_id, owner_ids in child_owners.items():
        if link_id not in parents:
            state.remember_object_ids(doc, *owner_ids)
    for link in links.values():
        link_state = state.new_state(doc, link)
        if link_state is None:
            if link.valid:
                repository.set_valid(doc, link.link_id, False, link.parent_id)
            state.remember_object_ids(doc, link.parent_id, link.child_id)
            continue
        if not link.valid:
            if not repository.set_valid(doc, link.link_id, True, link.parent_id):
                state.remember_object_ids(doc, link.parent_id, link.child_id)
                continue
            link_state = state.new_state(doc, replace(link, valid=True))
            if link_state is None:
                state.remember_object_ids(doc, link.parent_id, link.child_id)
                continue
            recovered.append(link_state)
        state.set_state(doc, link_state)

    active = state.states(doc, create=False)
    if active:
        ensure_conduit(doc, preferences.display_enabled(doc, default_display_enabled))
    from tack.links import lifecycle

    if state.has_tracked_states():
        lifecycle.subscribe()
    else:
        lifecycle.unsubscribe()
    if recovered:
        solver.maintain_changed_states(doc, recovered)
    doc.Views.Redraw()
    return len(active)


def resettable_links(doc):
    """Return active child-movable Tacks whose relationship has changed."""
    active_states = state.states(doc, create=False)
    return tuple(
        link
        for link in repository.all_links(doc)
        if link.allow_child_movement
        and link.link_id in active_states
        and not transforms.transform_data_matches(
            link.current_transform,
            link.original_transform,
        )
    )


def reset_transform(doc, link_id):
    link = repository.read_link(doc, link_id)
    if link is None or not link.allow_child_movement:
        return False
    if not repository.save(
        doc,
        replace(link, current_transform=list(link.original_transform)),
        replaced=(link,),
    ):
        return False
    link_state = state.states(doc, create=False).get(link_id)
    return link_state is not None and solver.maintain(doc, link_state)


def reset_all_transforms(doc):
    """Reset every deviated child-movable Tack in one undoable operation."""
    links = resettable_links(doc)
    if not links:
        return False
    undo_record = doc.BeginUndoRecord("Reset Moveable Tacks")
    try:
        results = [reset_transform(doc, link.link_id) for link in links]
    finally:
        if undo_record:
            doc.EndUndoRecord(undo_record)
    return all(results)


def remove_links(doc, link_ids):
    requested = tuple(link_ids)
    if not repository.remove_many(doc, requested):
        return False
    for link_id in requested:
        link_state = state.states(doc, create=False).get(link_id)
        if link_state is not None:
            state.remember_state(doc, link_state)
    if not state.states(doc, create=False):
        deactivate_document(doc)
    doc.Views.Redraw()
    return True


def remove_link(doc, link_id):
    return remove_links(doc, (link_id,))


def clear_document(doc):
    for link_state in list(state.states(doc, create=False).values()):
        state.remember_state(doc, link_state)
    deactivate_document(doc)
    metadata_cleared = repository.clear(doc)
    doc.Views.Redraw()
    return metadata_cleared
