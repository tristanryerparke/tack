"""Rhino command and document event handlers for active Tack Links."""

import Rhino
import scriptcontext as sc

from tack.core import documents
from tack.core.objects import find_object, object_key
from tack.links import preferences, repository, runtime, solver, state

HANDLERS_KEY = "Tack.Handlers"
_solving = False


def _command_name(event):
    return (
        getattr(event, "CommandEnglishName", None)
        or getattr(event, "EnglishName", None)
        or getattr(event, "CommandName", None)
        or "<unknown>"
    )


def _observed_links(doc):
    """Read only endpoints with an active or cached Tack state."""
    objects = state.candidate_objects(doc)
    parents, _ = repository.observed_metadata(objects.values())
    for link in parents.values():
        for object_id in (link.parent_id, link.child_id):
            obj = find_object(doc, object_id)
            if obj is not None:
                objects[object_key(obj.Id)] = obj
    parents, child_owners = repository.observed_metadata(objects.values())
    return repository.active_observed_links(parents, child_owners)


def _reconcile_runtime_with_metadata(doc):
    """Match LinkStates to recently changed object metadata without a full scan."""
    saved = _observed_links(doc)
    active = state.states(doc, create=False)
    for link_id, link_state in list(active.items()):
        if link_id not in saved:
            state.cache_state(doc, link_state)

    pending = []
    for link in saved.values():
        link_state = active.get(link.link_id)
        if link_state is None or (
            link_state.parent_id != link.parent_id or link_state.child_id != link.child_id
        ):
            link_state = state.new_state(doc, link)
            if link_state is not None:
                state.set_state(doc, link_state)
        if link_state is not None:
            pending.append(link_state)

    state.keep_invalid_for_undo(doc)
    if state.states(doc, create=False):
        runtime.ensure_conduit(doc, preferences.display_enabled(doc))
    else:
        runtime.deactivate_document(doc)
    return tuple(pending)


def begin_command_handler(sender, event):
    doc = Rhino.RhinoDoc.ActiveDoc
    if doc is None:
        return
    conduit = runtime.active_conduit()
    if conduit is not None:
        conduit.command_began(_command_name(event))


def end_command_handler(sender, event):
    global _solving
    if _solving:
        return
    doc = Rhino.RhinoDoc.ActiveDoc
    if doc is None:
        return

    conduit = runtime.active_conduit()
    if conduit is not None:
        conduit.command_ended()

    pending = _reconcile_runtime_with_metadata(doc)
    if not state.states(doc, create=False):
        if not state.has_tracked_states():
            unsubscribe()
        return

    _solving = True
    try:
        solver.maintain_changed_states(doc, pending)
    finally:
        _solving = False
    from tack.ui import panel

    panel.refresh(doc)
    doc.Views.Redraw()


def close_document_handler(sender, event):
    doc = getattr(event, "Document", None)
    if doc is None:
        return
    runtime.remove_runtime(doc)
    documents.remove_document(doc)
    from tack.ui import panel

    panel.forget(doc)
    if not state.has_tracked_states():
        unsubscribe()


def subscribe():
    if sc.sticky.get(HANDLERS_KEY) is not None:
        return
    handlers = (begin_command_handler, end_command_handler, close_document_handler)
    Rhino.Commands.Command.BeginCommand += begin_command_handler
    Rhino.Commands.Command.EndCommand += end_command_handler
    Rhino.RhinoDoc.CloseDocument += close_document_handler
    sc.sticky[HANDLERS_KEY] = handlers


def unsubscribe():
    handlers = sc.sticky.pop(HANDLERS_KEY, ())
    events = (
        Rhino.Commands.Command.BeginCommand,
        Rhino.Commands.Command.EndCommand,
        Rhino.RhinoDoc.CloseDocument,
    )
    for handler, event in zip(handlers, events):
        try:
            event -= handler
        except Exception:  # noqa: BLE001, S110 - teardown must never raise
            pass
