import traceback

import Rhino
import scriptcontext as sc

from ondsel.assembly import assembly_common

IDLE_HANDLER_KEY = "Ondsel.Assembly.IdleHandler.v1"
_pending_docs = {}
_solving = False


def _debug(message):
    text = "[Ondsel assembly] " + str(message)
    print(text)
    try:
        from tack import watcher

        with watcher.output(True):
            print(text)
    except Exception:
        pass


def _report_error():
    traceback.print_exc()
    try:
        from tack import watcher

        with watcher.output(True):
            traceback.print_exc()
    except Exception:
        pass


def is_solving():
    return _solving


def _ensure_armed():
    if sc.sticky.get(IDLE_HANDLER_KEY) is None:
        handler = _on_idle
        Rhino.RhinoApp.Idle += handler
        sc.sticky[IDLE_HANDLER_KEY] = handler


def disarm():
    handler = sc.sticky.pop(IDLE_HANDLER_KEY, None)
    if handler is not None:
        try:
            Rhino.RhinoApp.Idle -= handler
        except Exception:
            _report_error()


def expire_document(doc, reason=None):
    if doc is None:
        return
    key = int(doc.RuntimeSerialNumber)
    _pending_docs[key] = doc
    _ensure_armed()
    if reason:
        _debug("scheduled solve on idle ({})".format(reason))


def drop_document(doc):
    if doc is None:
        return
    _pending_docs.pop(int(doc.RuntimeSerialNumber), None)


def solve_now(doc):
    _solve(doc)


def _on_idle(sender, args):
    if _solving or not _pending_docs:
        return
    for key, doc in list(_pending_docs.items()):
        if doc is None:
            _pending_docs.pop(key, None)
            continue
        try:
            _solve(doc)
        except Exception:
            _report_error()
        _pending_docs.pop(key, None)
    if not _pending_docs:
        disarm()


def _solve(doc):
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
