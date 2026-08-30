"""Runtime maintenance for parent/child analytic-plane relationships."""

import Rhino
import System.Drawing
import scriptcontext as sc

from tack import document_runtime
from tack import plane_link_metadata
from tack import plane_link_preview
from tack import three_point_plane
from tack import utils


RUNTIME_KEY = "Tack.AnalyticPlaneLink.Runtime"
LEGACY_PENDING_KEY = "Tack.AnalyticPlaneLink.Pending"
HANDLERS_KEY = "Tack.AnalyticPlaneLink.Handlers"
LEGACY_IDLE_HANDLER_KEY = "Tack.AnalyticPlaneLink.IdleHandler"
MARKER_CONDUIT_KEY = "Tack.AnalyticPlaneLink.OriginMarkerConduit"
MARKER_COLOR = System.Drawing.Color.Orange
MARKER_SIZE = 8
_solving = False


class OriginMarkerConduit(Rhino.Display.DisplayConduit):
    def DrawForeground(self, event):
        doc = event.RhinoDoc
        if doc is None:
            return
        for state in states(doc, create=False).values():
            origin = state.get("origin")
            if state.get("broken") or origin is None:
                continue
            event.Display.DrawPoint(
                origin,
                Rhino.Display.PointStyle.RoundDot,
                MARKER_SIZE,
                MARKER_COLOR,
            )


def states(doc, create=True):
    if create:
        return document_runtime.get_value(doc, RUNTIME_KEY, lambda _: {})
    return document_runtime.try_get_value(doc, RUNTIME_KEY) or {}


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
    parent_plane = three_point_plane.resolve_definition(
        doc,
        link["parent_plane"],
    )
    child_plane = three_point_plane.resolve_definition(
        doc,
        link["child_plane"],
    )
    if parent_plane is None or child_plane is None:
        return None
    state = {
        "link_id": link["link_id"],
        "parent_id": link["parent_id"],
        "child_id": link["child_id"],
        "link": link,
        "broken": False,
        "busy": False,
        "origin": Rhino.Geometry.Point3d(parent_plane.Origin),
    }
    _refresh_serials(doc, state)
    return state


def _ensure_marker_conduit():
    conduit = sc.sticky.get(MARKER_CONDUIT_KEY)
    if conduit is None:
        conduit = OriginMarkerConduit()
        sc.sticky[MARKER_CONDUIT_KEY] = conduit
    conduit.Enabled = True


def _disable_marker_if_unused():
    if document_runtime.has_nonempty_value(RUNTIME_KEY):
        return
    conduit = sc.sticky.pop(MARKER_CONDUIT_KEY, None)
    if conduit is not None:
        conduit.Enabled = False


def install(doc, link):
    state = _new_state(doc, link)
    if state is None:
        return None
    states(doc)[link["link_id"]] = state
    subscribe()
    _ensure_marker_conduit()
    doc.Views.Redraw()
    return state


def clear_document(doc):
    """Remove active and saved analytic-plane relationships from ``doc``."""
    unsubscribe()
    document_runtime.remove_value(doc, RUNTIME_KEY)
    document_runtime.remove_value(doc, LEGACY_PENDING_KEY)
    metadata_cleared = plane_link_metadata.clear(doc)
    if document_runtime.has_nonempty_value(RUNTIME_KEY):
        subscribe()
    else:
        _disable_marker_if_unused()
    doc.Views.Redraw()
    return metadata_cleared


def transform_object_in_place(doc, obj, transform):
    """Transform geometry while preserving the Rhino object's GUID."""
    if obj is None or obj.Geometry is None:
        return None
    object_id = obj.Id
    attributes = obj.Attributes.Duplicate()
    geometry = obj.Geometry.Duplicate()
    if geometry is None or not geometry.Transform(transform):
        return None
    if not doc.Objects.Replace(object_id, geometry, True):
        return None
    transformed = utils.find_object(doc, object_id)
    if transformed is None:
        return None
    if not doc.Objects.ModifyAttributes(object_id, attributes, True):
        return None
    return utils.find_object(doc, object_id)


def _planes_match(parent_plane, child_plane, inverted, tolerance):
    effective_child = (
        plane_link_preview.inverted_plane(child_plane)
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
    state["origin"] = None
    Rhino.UI.Dialogs.ShowMessage(
        "The analytic-plane relationship can no longer resolve both saved "
        "frames. The child will stop following the parent.",
        "Analytic plane relationship broken",
        Rhino.UI.ShowMessageButton.OK,
        Rhino.UI.ShowMessageIcon.Warning,
    )


def maintain(doc, state):
    if state.get("busy"):
        return False
    link = state["link"]
    parent = utils.find_object(doc, state["parent_id"])
    child = utils.find_object(doc, state["child_id"])
    if parent is None or child is None:
        _show_broken_alert(state)
        return False

    saved = plane_link_metadata.read_link(child, state["link_id"])
    if saved is not None:
        link = saved
        state["link"] = saved
    parent_plane = three_point_plane.resolve_definition(doc, link["parent_plane"])
    child_plane = three_point_plane.resolve_definition(doc, link["child_plane"])
    if parent_plane is None or child_plane is None:
        _show_broken_alert(state)
        return False

    state["broken"] = False
    state["origin"] = Rhino.Geometry.Point3d(parent_plane.Origin)
    tolerance = max(doc.ModelAbsoluteTolerance, 1e-7)
    if _planes_match(parent_plane, child_plane, link["inverted"], tolerance):
        _refresh_serials(doc, state)
        return True

    correction = plane_link_preview.plane_to_plane_transform(
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
    saved = {
        link["link_id"]: link
        for link in plane_link_metadata.all_links(doc)
    }
    for link_id in list(active):
        if link_id not in saved:
            active.pop(link_id, None)
    for link_id, link in saved.items():
        state = active.get(link_id)
        if state is None:
            state = _new_state(doc, link)
            if state is not None:
                active[link_id] = state
            continue
        state["link"] = link
        state["parent_id"] = link["parent_id"]
        state["child_id"] = link["child_id"]

    if active:
        _ensure_marker_conduit()
    else:
        _disable_marker_if_unused()


def EndCommandHandler(sender, event):
    global _solving
    if _solving:
        return
    doc = Rhino.RhinoDoc.ActiveDoc
    if doc is None:
        return

    is_undo_or_redo = _command_name(event).lower() in ("undo", "redo")
    if is_undo_or_redo:
        _synchronize_runtime_with_metadata(doc)

    changed = []
    for state in states(doc, create=False).values():
        if state.get("busy"):
            continue
        for role in ("parent", "child"):
            current = _object_serial(
                utils.find_object(doc, state[role + "_id"])
            )
            if current != state.get(role + "_runtime_serial"):
                changed.append(state)
                break

    if changed:
        _solving = True
        try:
            for state in changed:
                maintain(doc, state)
        finally:
            _solving = False

    if is_undo_or_redo:
        _synchronize_runtime_with_metadata(doc)
    doc.Views.Redraw()


def CloseDocumentHandler(sender, event):
    doc = getattr(event, "Document", None)
    if doc is None:
        return
    document_runtime.remove_value(doc, RUNTIME_KEY)
    document_runtime.remove_value(doc, LEGACY_PENDING_KEY)
    _disable_marker_if_unused()


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

    legacy_idle_handler = sc.sticky.pop(LEGACY_IDLE_HANDLER_KEY, None)
    if legacy_idle_handler is not None:
        try:
            Rhino.RhinoApp.Idle -= legacy_idle_handler
        except Exception:
            pass
