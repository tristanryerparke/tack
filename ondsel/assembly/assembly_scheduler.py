"""Synchronous solve trigger for Ondsel assembly relationships.

Solves run inside the command that changed the parts (EndCommand), so the
resulting object transforms share that command's undo record. There is no
idle handler: every expire_document call solves immediately.
"""

import traceback

import scriptcontext as sc


LOG_PATH = "/tmp/ondsel_handler.log"
WATCHER_CONNECTION_KEY = "Ondsel.Assembly.WatcherConnection.v1"
_solving = False


def _log_line(text):
    try:
        with open(LOG_PATH, "a") as log:
            log.write(text.rstrip("\n") + "\n")
    except Exception:
        pass


def _send_terminal(text):
    connection = sc.sticky.get(WATCHER_CONNECTION_KEY)
    if connection is None:
        return
    try:
        connection.send_terminal(text)
    except Exception:
        sc.sticky.pop(WATCHER_CONNECTION_KEY, None)


def _debug(message):
    text = "[Ondsel assembly] " + str(message)
    print(text)
    _log_line(text)
    _send_terminal(text)


def _report_error():
    traceback.print_exc()
    text = traceback.format_exc()
    _log_line(text)
    _send_terminal(text)


def is_solving():
    return _solving


def disarm():
    """Compatibility no-op now that solves do not use RhinoApp.Idle."""


def expire_document(doc, reason=None):
    """Solve *doc* now, inside the current command's undo scope."""
    if doc is None:
        return
    if reason:
        _debug("solving now ({})".format(reason))
    solve_now(doc)


def drop_document(doc):
    """Compatibility no-op (no pending-work registry without idle)."""


def solve_now(doc):
    global _solving
    _solving = True
    try:
        from ondsel.assembly import assembly_model

        assembly_model = __import__("ondsel.assembly.assembly_model", fromlist=["*"])
        assembly_model._set_solving(doc, True)
        assembly_model.solve_and_propagate(doc)
        try:
            doc.Views.Redraw()
        except Exception:
            _report_error()
    finally:
        try:
            from ondsel.assembly import assembly_model
            assembly_model._set_solving(doc, False)
        except Exception:
            pass
        _solving = False
