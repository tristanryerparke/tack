"""Runtime lifecycle for parent/child analytic-plane Tack relationships."""

import Rhino
import scriptcontext as sc

from tack import analytic_plane
from tack import display
from tack import document_runtime
from tack import plane_link_metadata
from tack import utils


STATES_KEY = "Tack.PlaneLinks.States"
CONDUIT_KEY = "Tack.PlaneLinks.Conduit"
DISPLAY_KEY = "Tack.PlaneLinks.Display"
HANDLERS_KEY = "Tack.PlaneLinks.Handlers"
_solving = False


def states(doc, create=True):
    if create:
        return document_runtime.get_value(doc, STATES_KEY, lambda _: {})
    return document_runtime.try_get_value(doc, STATES_KEY) or {}


def _display_state(doc, default_enabled=True):
    return document_runtime.get_value(
        doc,
        DISPLAY_KEY,
        lambda _: {
            "enabled": bool(default_enabled),
        },
    )


def _plugin():
    try:
        from RhinoCodePlatform.Rhino3D.Projects.Plugin import ProjectPlugin
    except ImportError:
        return None
    return ProjectPlugin


def crosshair_size(doc):
    plugin = _plugin()
    if plugin is not None:
        size = plugin.CrosshairSize
    else:
        size = _display_state(doc).get(
            "crosshair_size",
            analytic_plane.CROSSHAIR_SIZE,
        )
    return max(
        analytic_plane.CROSSHAIR_SIZE_MIN,
        min(analytic_plane.CROSSHAIR_SIZE_MAX, float(size)),
    )


def set_crosshair_size(doc, size):
    size = max(
        analytic_plane.CROSSHAIR_SIZE_MIN,
        min(analytic_plane.CROSSHAIR_SIZE_MAX, int(size)),
    )
    plugin = _plugin()
    if plugin is not None:
        plugin.SaveCrosshairSize(size)
    else:
        _display_state(doc)["crosshair_size"] = float(size)
    doc.Views.Redraw()
    return size


def crosshair_thickness(doc):
    plugin = _plugin()
    if plugin is not None:
        thickness = plugin.CrosshairThickness
    else:
        thickness = _display_state(doc).get(
            "crosshair_thickness",
            analytic_plane.CROSSHAIR_THICKNESS,
        )
    return max(
        analytic_plane.CROSSHAIR_THICKNESS_MIN,
        min(analytic_plane.CROSSHAIR_THICKNESS_MAX, float(thickness)),
    )


def set_crosshair_thickness(doc, thickness):
    thickness = max(
        analytic_plane.CROSSHAIR_THICKNESS_MIN,
        min(analytic_plane.CROSSHAIR_THICKNESS_MAX, int(thickness)),
    )
    plugin = _plugin()
    if plugin is not None:
        plugin.SaveCrosshairThickness(thickness)
    else:
        _display_state(doc)["crosshair_thickness"] = float(thickness)
    doc.Views.Redraw()
    return thickness


def display_enabled(doc):
    state = document_runtime.try_get_value(doc, DISPLAY_KEY)
    return (
        plane_link_metadata.display_enabled(doc)
        if state is None
        else bool(state["enabled"])
    )


def set_display_enabled(doc, enabled):
    if not states(doc, create=False):
        return False
    enabled = bool(enabled)
    if not plane_link_metadata.set_display_enabled(doc, enabled):
        return False
    _display_state(doc)["enabled"] = enabled
    doc.Views.Redraw()
    return True


def _object_serial(obj):
    return None if obj is None else int(obj.RuntimeSerialNumber)


def _refresh_serials(doc, state):
    for role in ("parent", "child"):
        state[role + "_runtime_serial"] = _object_serial(
            utils.find_object(doc, state[role + "_id"])
        )


def _new_state(doc, link):
    parent = utils.find_object(doc, link["parent_id"])
    child = utils.find_object(doc, link["child_id"])
    if parent is None or child is None:
        return None
    parent_plane = analytic_plane.resolve_definition(doc, link["parent_plane"])
    child_plane = analytic_plane.resolve_definition(doc, link["child_plane"])
    if parent_plane is None or child_plane is None:
        return None
    state = {
        "link_id": link["link_id"],
        "parent_id": link["parent_id"],
        "child_id": link["child_id"],
        "link": link,
        "plane": Rhino.Geometry.Plane(parent_plane),
        "broken": False,
        "busy": False,
        "dynamic_preview_active": False,
    }
    _refresh_serials(doc, state)
    return state


def _ensure_conduit(doc, default_display_enabled=True):
    conduit = document_runtime.try_get_value(doc, CONDUIT_KEY)
    if conduit is None:
        conduit = display.LinkedPlaneConduit(
            doc.RuntimeSerialNumber,
            states(doc),
            _display_state(doc, default_display_enabled),
        )
        conduit.Enabled = True
        document_runtime.set_value(doc, CONDUIT_KEY, conduit)
    return conduit


def _remove_runtime(doc):
    conduit = document_runtime.remove_value(doc, CONDUIT_KEY)
    if conduit is not None:
        conduit.Enabled = False
        conduit.clear_preview()
    document_runtime.remove_value(doc, STATES_KEY)
    document_runtime.remove_value(doc, DISPLAY_KEY)


def install(doc, link, default_display_enabled=True):
    state = _new_state(doc, link)
    if state is None:
        return None
    states(doc)[link["link_id"]] = state
    saved_display_enabled = plane_link_metadata.display_enabled(
        doc,
        default_display_enabled,
    )
    _ensure_conduit(doc, saved_display_enabled)
    plane_link_metadata.set_display_enabled(
        doc,
        _display_state(doc, saved_display_enabled)["enabled"],
    )
    subscribe()
    doc.Views.Redraw()
    return state


def restore_document(doc, default_display_enabled=True):
    _remove_runtime(doc)
    active = states(doc)
    for link in plane_link_metadata.all_links(doc):
        state = _new_state(doc, link)
        if state is not None:
            active[link["link_id"]] = state
    if active:
        _ensure_conduit(
            doc,
            plane_link_metadata.display_enabled(doc, default_display_enabled),
        )
        subscribe()
    elif not document_runtime.has_nonempty_value(STATES_KEY):
        unsubscribe()
    doc.Views.Redraw()
    return len(active)


def clear_document(doc):
    _remove_runtime(doc)
    metadata_cleared = plane_link_metadata.clear(doc)
    if not document_runtime.has_nonempty_value(STATES_KEY):
        unsubscribe()
    doc.Views.Redraw()
    return metadata_cleared


def transform_object_in_place(doc, obj, transform):
    if obj is None or obj.Geometry is None:
        return None
    object_id = obj.Id
    attributes = obj.Attributes.Duplicate()
    geometry = obj.Geometry.Duplicate()
    if geometry is None or not geometry.Transform(transform):
        return None
    if not doc.Objects.Replace(object_id, geometry, True):
        return None
    if not doc.Objects.ModifyAttributes(object_id, attributes, True):
        return None
    return utils.find_object(doc, object_id)


def _planes_match(parent_plane, child_plane, inverted, tolerance):
    effective_child = (
        display.inverted_plane(child_plane)
        if inverted
        else child_plane
    )
    return (
        parent_plane.Origin.DistanceTo(effective_child.Origin) <= tolerance
        and parent_plane.XAxis * effective_child.XAxis >= 1.0 - tolerance
        and parent_plane.YAxis * effective_child.YAxis >= 1.0 - tolerance
    )


def _show_broken_alert(state):
    if state.get("broken"):
        return
    state["broken"] = True
    state["plane"] = None
    Rhino.UI.Dialogs.ShowMessage(
        "A Tack relationship can no longer resolve both saved planes. "
        "The child will stop following the parent.",
        "Tack relationship broken",
        Rhino.UI.ShowMessageButton.OK,
        Rhino.UI.ShowMessageIcon.Warning,
    )


def maintain(doc, state):
    if state.get("busy"):
        return False
    parent = utils.find_object(doc, state["parent_id"])
    child = utils.find_object(doc, state["child_id"])
    if parent is None or child is None:
        _show_broken_alert(state)
        return False

    saved = plane_link_metadata.read_link(doc, state["link_id"])
    if saved is not None:
        state["link"] = saved
    link = state["link"]
    parent_plane = analytic_plane.resolve_definition(doc, link["parent_plane"])
    child_plane = analytic_plane.resolve_definition(doc, link["child_plane"])
    if parent_plane is None or child_plane is None:
        _show_broken_alert(state)
        return False

    state["broken"] = False
    state["plane"] = Rhino.Geometry.Plane(parent_plane)
    tolerance = max(doc.ModelAbsoluteTolerance, 1e-7)
    if _planes_match(parent_plane, child_plane, link["inverted"], tolerance):
        _refresh_serials(doc, state)
        return True

    correction = display.plane_to_plane_transform(
        parent_plane,
        child_plane,
        link["inverted"],
    )
    state["busy"] = True
    try:
        transformed = transform_object_in_place(doc, child, correction)
        if transformed is None or not utils.same_id(transformed.Id, child.Id):
            _show_broken_alert(state)
            return False
        _refresh_serials(doc, state)
        doc.Views.Redraw()
        return True
    finally:
        state["busy"] = False


def _command_name(event):
    return (
        getattr(event, "CommandEnglishName", None)
        or getattr(event, "EnglishName", None)
        or getattr(event, "CommandName", None)
        or "<unknown>"
    )


def _synchronize_runtime_with_metadata(doc):
    active = states(doc)
    saved = {link["link_id"]: link for link in plane_link_metadata.all_links(doc)}
    for link_id in list(active):
        if link_id not in saved:
            active.pop(link_id, None)
    for link_id, link in saved.items():
        state = _new_state(doc, link)
        if state is not None:
            active[link_id] = state
    if active:
        _ensure_conduit(doc)
    else:
        _remove_runtime(doc)


def _changed_states(doc):
    changed = []
    for state in states(doc, create=False).values():
        if state.get("busy"):
            continue
        for role in ("parent", "child"):
            current = _object_serial(utils.find_object(doc, state[role + "_id"]))
            if current != state.get(role + "_runtime_serial"):
                changed.append(state)
                break
    return changed


def _maintain_changed_states(doc):
    """Settle parent-to-child chains within one native command completion."""
    max_passes = len(states(doc, create=False)) + 1
    for _ in range(max_passes):
        changed = _changed_states(doc)
        if not changed:
            return
        for state in changed:
            maintain(doc, state)


def EndCommandHandler(sender, event):
    global _solving
    if _solving:
        return
    doc = Rhino.RhinoDoc.ActiveDoc
    if doc is None:
        return

    conduit = document_runtime.try_get_value(doc, CONDUIT_KEY)
    if conduit is not None:
        conduit.command_ended()

    is_undo_or_redo = _command_name(event).lower() in ("undo", "redo")
    if is_undo_or_redo:
        _synchronize_runtime_with_metadata(doc)
        doc.Views.Redraw()
        return

    _solving = True
    try:
        _maintain_changed_states(doc)
    finally:
        _solving = False
    doc.Views.Redraw()


def CloseDocumentHandler(sender, event):
    doc = getattr(event, "Document", None)
    if doc is None:
        return
    _remove_runtime(doc)
    document_runtime.remove_document(doc)
    if not document_runtime.has_nonempty_value(STATES_KEY):
        unsubscribe()


def subscribe():
    if sc.sticky.get(HANDLERS_KEY) is not None:
        return
    handlers = (EndCommandHandler, CloseDocumentHandler)
    Rhino.Commands.Command.EndCommand += EndCommandHandler
    Rhino.RhinoDoc.CloseDocument += CloseDocumentHandler
    sc.sticky[HANDLERS_KEY] = handlers


def unsubscribe():
    handlers = sc.sticky.pop(HANDLERS_KEY, ())
    events = (Rhino.Commands.Command.EndCommand, Rhino.RhinoDoc.CloseDocument)
    for handler, event in zip(handlers, events):
        try:
            event -= handler
        except Exception:
            pass
