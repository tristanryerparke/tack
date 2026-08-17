"""Synchronous solver queue for Tack relationships.

Event handlers in :mod:`tack.handlers` *expire* relationships here, and the
same command then drains the per-document schedule synchronously.
"""

import traceback

from tack import document_runtime
from tack import link
from tack import metadata
from tack import runtime
from tack import utils
from tack import watcher


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


def is_solving():
    return _solving


def disarm():
    """Compatibility no-op now that solves do not use RhinoApp.Idle."""


def expire_link_ids(doc, link_ids):
    """Mark relationships dirty so the current command can drain them."""
    schedule = _schedule(doc)
    added = False
    for link_id in link_ids:
        if link_id not in schedule:
            schedule.add(link_id)
            added = True
    if added:
        with _websocket_output():
            utils.debug(
                "[Tack solve] expired {} link(s); scheduled for EndCommand.".format(
                    len(schedule)
                )
            )


def drop_document(doc):
    """Forget pending work for a document (called on close)."""
    document_runtime.remove_value(doc, utils.SCHEDULE_KEY)


def solve_now(doc):
    """Synchronously drain *doc*'s schedule."""
    _solve(doc)


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
        _schedule(doc).add(link_id)
        return
    runtime.mark_display_dirty(state)
    try:
        with _websocket_output():
            utils.debug("[Tack solve] maintaining link={}".format(link_id))
            link.maintain_link(
                doc,
                state,
                quiet=True,
            )
    finally:
        runtime.refresh_object_runtime_serials(doc, state)


def _runtime_state(doc, link_id):
    for saved_id, state in runtime.states(doc, create=False).items():
        if utils.same_id(saved_id, link_id):
            return state
    return None
