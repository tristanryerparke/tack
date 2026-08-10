"""Deferred solver for Tack relationships at command boundaries.

Object handlers expire affected links; an always-subscribed
``Command.EndCommand`` handler coalesces and solves them after each command.
"""

import traceback
from contextlib import nullcontext

import Rhino
import scriptcontext as sc

from tack import document_runtime
from tack import link
from tack import metadata
from tack import runtime
from tack import utils


END_COMMAND_HANDLER_KEY = "Tack.AnchorLink.EndCommandHandler"
LEGACY_IDLE_HANDLER_KEY = "Tack.AnchorLink.IdleHandler"

# doc serial -> RhinoDoc, for documents with pending expirations.
_pending_docs = {}
_solving = False


def _websocket_output():
    try:
        from rhino_watcher import websocket_output_if_available_sync
    except ImportError:
        return nullcontext()
    return websocket_output_if_available_sync()


def _report_error():
    try:
        if utils.DEBUG:
            with _websocket_output():
                traceback.print_exc()
    except Exception:
        pass


def _schedule(doc):
    return document_runtime.get_value(
        doc,
        utils.SCHEDULE_KEY,
        lambda _: set(),
    )


def _register_doc(doc):
    _pending_docs[document_runtime.document_key(doc)] = doc


def arm():
    """Subscribe for as long as Tack's object handlers are active."""
    if sc.sticky.get(END_COMMAND_HANDLER_KEY) is None:
        handler = _on_end_command
        Rhino.Commands.Command.EndCommand += handler
        sc.sticky[END_COMMAND_HANDLER_KEY] = handler


def disarm():
    """Remove command and legacy idle subscriptions. Safe to call repeatedly."""
    for key, event in (
        (END_COMMAND_HANDLER_KEY, Rhino.Commands.Command.EndCommand),
        (LEGACY_IDLE_HANDLER_KEY, Rhino.RhinoApp.Idle),
    ):
        handler = sc.sticky.pop(key, None)
        if handler is not None:
            try:
                event -= handler
            except Exception:
                _report_error()


def expire_link_ids(doc, link_ids):
    """Mark relationships dirty and solve them at the next command end."""
    schedule = _schedule(doc)
    added = False
    for link_id in link_ids:
        if link_id not in schedule:
            schedule.add(link_id)
            added = True
    if added:
        _register_doc(doc)
        with _websocket_output():
            utils.debug(
                "[Tack solve] expired {} link(s); scheduled for command end.".format(
                    len(schedule)
                )
            )



def drop_document(doc):
    """Forget pending work for a document (called on close)."""
    _pending_docs.pop(document_runtime.document_key(doc), None)


def solve_now(doc):
    """Synchronously drain *doc*'s schedule. Test / correctness hook."""
    _drain(doc)


def _on_end_command(sender, args):
    if _solving or not _pending_docs:
        return
    for doc_key, doc in list(_pending_docs.items()):
        if doc is None:
            _pending_docs.pop(doc_key, None)
            continue
        try:
            _drain(doc)
        except Exception:
            _report_error()
        if not _schedule(doc):
            _pending_docs.pop(doc_key, None)


def _drain(doc):
    schedule = _schedule(doc)
    link_count = len(metadata.all_links(doc))
    # ponytail: bounded fallback for corrupt metadata; add graph diagnostics if
    # valid command event sequences ever need more than 16 cleanup passes.
    for _ in range(max(16, link_count + 1)):
        if not schedule:
            return
        _solve(doc)

    pending = tuple(schedule)
    schedule.clear()
    for link_id in pending:
        state = _runtime_state(doc, link_id)
        if state is not None:
            link.break_link(
                state,
                "The Tack dependency graph did not settle; check it for a cycle.",
            )


def _solve(doc):
    global _solving
    schedule = _schedule(doc)
    if not schedule or not runtime.states(doc, create=False):
        schedule.clear()
        return
    _solving = True
    try:
        pending = sorted(schedule, key=str)
        schedule.clear()
        saved_links = _saved_link_map(doc)
        for link_id in pending:
            _solve_one(doc, link_id, saved_links)
        try:
            doc.Views.Redraw()
        except Exception:
            _report_error()
    finally:
        _solving = False


def _saved_link_map(doc):
    result = {}
    for saved_link in metadata.all_links(doc):
        result[saved_link["link_id"]] = saved_link
    return result


def _solve_one(doc, link_id, saved_links):
    saved_link = _lookup(saved_links, link_id)
    state = _runtime_state(doc, link_id)
    if state is None:
        if saved_link is None:
            return
        state = runtime.state_for_link(doc, saved_link)
    elif saved_link is not None:
        state = runtime.state_for_link(doc, saved_link)
    if state is None:
        return
    if state.get("busy"):
        # Defer until the state is free and the next command ends.
        _schedule(doc).add(link_id)
        return
    runtime.mark_display_dirty(state)
    with _websocket_output():
        utils.debug("[Tack solve] maintaining link={}".format(link_id))
        link.maintain_link(
            doc,
            state,
            object_ids=(state.get("parent_id"), state.get("child_id")),
            quiet=True,
        )


def _runtime_state(doc, link_id):
    for saved_id, state in runtime.states(doc, create=False).items():
        if utils.same_id(saved_id, link_id):
            return state
    return None


def _lookup(saved_links, link_id):
    if link_id in saved_links:
        return saved_links[link_id]
    for key, value in saved_links.items():
        if utils.same_id(key, link_id):
            return value
    return None
