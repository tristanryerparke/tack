"""Grasshopper-style deferred solver for Tack relationships.

Event handlers in :mod:`tack.handlers` only *expire* relationships here
(the analogue of Grasshopper's ``IGH_Param.ExpireSolution``).  This module
owns the single idle pump that drains the expired set and re-solves each
relationship once -- the analogue of Grasshopper's
``GH_Document.NewSolution`` driven by ``ScheduleSolution``.

GH properties this preserves:

* **Coalescing** -- a relationship expired by many events in one batch is
  solved exactly once.
* **Re-entrancy** -- expirations raised while a solve is running queue for
  the next idle tick instead of re-entering the solver.
* **Cheap idle** -- the ``RhinoApp.Idle`` handler is armed only while work is
  pending and disarms itself once the schedule drains.
* **Per-document** -- each document has its own schedule; closing a document
  drops its pending work.
"""

import traceback

import Rhino
import scriptcontext as sc

from tack import document_runtime
from tack import link
from tack import metadata
from tack import runtime
from tack import utils
from tack import watcher


IDLE_HANDLER_KEY = "Tack.AnchorLink.IdleHandler"

# doc serial -> RhinoDoc, for documents with pending expirations.
_pending_docs = {}
_solving = False


def _websocket_output():
    return watcher.output(utils.DEBUG)


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


def _ensure_armed():
    if sc.sticky.get(IDLE_HANDLER_KEY) is None:
        handler = _on_idle
        Rhino.RhinoApp.Idle += handler
        sc.sticky[IDLE_HANDLER_KEY] = handler


def is_solving():
    return _solving


def disarm():
    """Remove the idle subscription if armed. Safe to call repeatedly."""
    handler = sc.sticky.pop(IDLE_HANDLER_KEY, None)
    if handler is not None:
        try:
            Rhino.RhinoApp.Idle -= handler
        except Exception:
            _report_error()


def expire_link_ids(doc, link_ids):
    """Mark relationships dirty and schedule a solve at the next idle tick."""
    schedule = _schedule(doc)
    added = False
    for link_id in link_ids:
        if link_id not in schedule:
            schedule.add(link_id)
            added = True
    if added:
        _register_doc(doc)
        _ensure_armed()
        with _websocket_output():
            utils.debug(
                "[Tack solve] expired {} link(s); scheduled for idle.".format(
                    len(schedule)
                )
            )



def drop_document(doc):
    """Forget pending work for a document (called on close)."""
    _pending_docs.pop(document_runtime.document_key(doc), None)


def solve_now(doc):
    """Synchronously drain *doc*'s schedule. Test / correctness hook."""
    _solve(doc)


def _on_idle(sender, args):
    if _solving or not _pending_docs:
        return
    for doc_key, doc in list(_pending_docs.items()):
        if doc is None:
            _pending_docs.pop(doc_key, None)
            continue
        try:
            _solve(doc)
        except Exception:
            _report_error()
        if not _schedule(doc):
            _pending_docs.pop(doc_key, None)
    if not _pending_docs:
        disarm()


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
        for link_id in pending:
            _solve_one(doc, link_id)
        try:
            doc.Views.Redraw()
        except Exception:
            _report_error()
    finally:
        _solving = False


def _solve_one(doc, link_id):
    state = _runtime_state(doc, link_id)
    if state is None:
        return
    child = utils.find_object(doc, state.get("child_id"))
    saved_link = metadata.read_link(child, link_id)
    if saved_link is not None:
        state = runtime.state_for_link(doc, saved_link)
    if state is None:
        return
    if state.get("busy"):
        # Defer until the state is free; re-arm for the next tick.
        _schedule(doc).add(link_id)
        _ensure_armed()
        return
    runtime.mark_display_dirty(state)
    try:
        with _websocket_output():
            utils.debug("[Tack solve] maintaining link={}".format(link_id))
            link.maintain_link(
                doc,
                state,
                object_ids=(state.get("parent_id"), state.get("child_id")),
                quiet=True,
            )
    finally:
        runtime.refresh_object_runtime_serials(doc, state)


def _runtime_state(doc, link_id):
    for saved_id, state in runtime.states(doc, create=False).items():
        if utils.same_id(saved_id, link_id):
            return state
    return None
