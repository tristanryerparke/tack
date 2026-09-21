"""Runtime lifecycle and display state for active Tack relationships."""

from tack.core import documents, plugin_data
from tack.links import preferences, repository, schema, solver, state

CONDUIT_KEY = "Tack.Link.Conduit"
DISPLAY_KEY = "Tack.Link.Display"


def _display_state(doc, default_enabled=True):
    return documents.get_value(
        doc,
        DISPLAY_KEY,
        lambda _: {
            "enabled": bool(default_enabled),
        },
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

    size = _number_setting(
        doc,
        plugin_data.CROSSHAIR_SIZE,
        analytic_plane.CROSSHAIR_SIZE,
    )
    return max(
        analytic_plane.CROSSHAIR_SIZE_MIN,
        min(analytic_plane.CROSSHAIR_SIZE_MAX, size),
    )


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
    return (
        preferences.display_enabled(doc)
        if display_state is None
        else bool(display_state["enabled"])
    )


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

    conduit = documents.try_get_value(doc, CONDUIT_KEY)
    if conduit is None:
        conduit = LinkedPlaneConduit(
            doc.RuntimeSerialNumber,
            state.states(doc),
            _display_state(doc, default_display_enabled),
        )
        conduit.Enabled = True
        documents.set_value(doc, CONDUIT_KEY, conduit)
    return conduit


def remove_runtime(doc):
    conduit = documents.remove_value(doc, CONDUIT_KEY)
    if conduit is not None:
        conduit.Enabled = False
        conduit.clear_preview()
    documents.remove_value(doc, state.STATES_KEY)
    documents.remove_value(doc, DISPLAY_KEY)


def install(doc, link, default_display_enabled=True):
    link_state = state.new_state(doc, link)
    if link_state is None:
        return None
    active = state.states(doc)
    for saved_link_id, saved_state in list(active.items()):
        if schema.same_object_pair(saved_state, link):
            active.pop(saved_link_id)
    active[link["link_id"]] = link_state
    saved_display_enabled = preferences.display_enabled(
        doc,
        default_display_enabled,
    )
    ensure_conduit(doc, saved_display_enabled)
    preferences.set_display_enabled(
        doc,
        _display_state(doc, saved_display_enabled)["enabled"],
    )
    from tack.links import lifecycle

    lifecycle.subscribe()
    doc.Views.Redraw()
    return link_state


def restore_document(doc, default_display_enabled=True):
    remove_runtime(doc)
    active = state.states(doc)
    for link in repository.all_links(doc):
        link_state = state.new_state(doc, link)
        if link_state is not None:
            active[link["link_id"]] = link_state
    if active:
        ensure_conduit(
            doc,
            preferences.display_enabled(doc, default_display_enabled),
        )
        from tack.links import lifecycle

        lifecycle.subscribe()
    elif not documents.has_nonempty_value(state.STATES_KEY):
        from tack.links import lifecycle

        lifecycle.unsubscribe()
    doc.Views.Redraw()
    return len(active)


def reset_inherit_transform(doc, link_id):
    """Restore an Inherit Only Tack's current transform to its original one."""
    link = repository.read_link(doc, link_id)
    if link is None or schema.link_mode(link) != "inherit_only":
        return False
    updated = dict(link)
    updated["current_transform"] = list(link["original_transform"])
    if not repository.save(doc, updated):
        return False
    link_state = next(
        (
            candidate
            for candidate in state.states(doc, create=False).values()
            if candidate["link_id"] == link_id
        ),
        None,
    )
    if link_state is None:
        return False
    link_state["link"] = updated
    return solver.maintain(doc, link_state)


def remove_links(doc, link_ids):
    """Remove one or more Tacks in one persisted relationship update."""
    requested = tuple(link_ids)
    if not repository.remove_many(doc, requested):
        return False

    active = state.states(doc, create=False)
    for saved_link_id in list(active):
        if any(saved_link_id == link_id for link_id in requested):
            active.pop(saved_link_id)
    if not active:
        remove_runtime(doc)
    doc.Views.Redraw()
    return True


def remove_link(doc, link_id):
    return remove_links(doc, (link_id,))


def clear_document(doc):
    remove_runtime(doc)
    metadata_cleared = repository.clear(doc)
    doc.Views.Redraw()
    return metadata_cleared
