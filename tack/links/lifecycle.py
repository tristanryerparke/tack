"""Rhino command and document event handlers for Tack relationships."""

import Rhino
import scriptcontext as sc

from tack.core import documents
from tack.links import preferences, repository, runtime, solver, state

HANDLERS_KEY = "Tack.Link.Handlers"
_solving = False


def _command_name(event):
    return (
        getattr(event, "CommandEnglishName", None)
        or getattr(event, "EnglishName", None)
        or getattr(event, "CommandName", None)
        or "<unknown>"
    )


def _reconcile_runtime_with_metadata(doc):
    """Match runtime states to current object metadata after every command."""
    saved = {link["link_id"]: link for link in repository.reconcile_links(doc)}
    active = state.states(doc, create=False)
    if not active and not saved:
        return (), False
    if not active:
        active = state.states(doc)

    reconciled = False
    pending = []
    for link_id in list(active):
        if link_id not in saved:
            active.pop(link_id, None)
            reconciled = True

    for link_id, link in saved.items():
        link_state = active.get(link_id)
        if link_state is None:
            link_state = state.new_state(doc, link)
            if link_state is not None:
                active[link_id] = link_state
                pending.append(link_state)
                reconciled = True
            continue

        if link_state["link"] != link:
            link_state["link"] = link
            link_state["parent_id"] = link["parent_id"]
            link_state["child_id"] = link["child_id"]
            pending.append(link_state)
            reconciled = True

    if active:
        runtime.ensure_conduit(
            doc,
            preferences.display_enabled(doc),
        )
    else:
        runtime.remove_runtime(doc)
    return tuple(pending), reconciled


def begin_command_handler(sender, event):
    doc = Rhino.RhinoDoc.ActiveDoc
    if doc is None:
        return
    conduit = documents.try_get_value(doc, runtime.CONDUIT_KEY)
    if conduit is not None:
        conduit.command_began(_command_name(event))


def end_command_handler(sender, event):
    global _solving
    if _solving:
        return
    doc = Rhino.RhinoDoc.ActiveDoc
    if doc is None:
        return

    conduit = documents.try_get_value(doc, runtime.CONDUIT_KEY)
    if conduit is not None:
        conduit.command_ended()

    pending, reconciled = _reconcile_runtime_with_metadata(doc)
    active = state.states(doc, create=False)
    if not active and not reconciled:
        return

    if active:
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
    if not documents.has_nonempty_value(state.STATES_KEY):
        unsubscribe()


def subscribe():
    if sc.sticky.get(HANDLERS_KEY) is not None:
        return
    handlers = (
        begin_command_handler,
        end_command_handler,
        close_document_handler,
    )
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
