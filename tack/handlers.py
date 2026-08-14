import traceback

import Rhino

from tack import runtime
from tack import scheduler
from tack import utils
from tack import watcher


HANDLER_KEY = "Tack.AnchorLink.Handlers"


def _websocket_output():
    return watcher.output(utils.DEBUG)


def _quit_watcher():
    watcher.send_quit(utils.DEBUG)


def _report_handler_error():
    try:
        if utils.DEBUG:
            with _websocket_output():
                traceback.print_exc()
    finally:
        _quit_watcher()


def EndCommandHandler(sender, event):
    try:
        doc = Rhino.RhinoDoc.ActiveDoc
        if doc is None or scheduler.is_solving():
            return
        expired = runtime.mark_changed_links_dirty(doc)
        if expired:
            scheduler.expire_link_ids(doc, expired)
            with _websocket_output():
                utils.debug(
                    "[Tack anchor] EndCommand found {} changed link(s).".format(
                        len(expired)
                    )
                )
    except Exception:
        _report_handler_error()


def CloseDocumentHandler(sender, event):
    try:
        doc = getattr(event, "Document", None)
        if doc is not None:
            scheduler.drop_document(doc)
            runtime.remove_document(doc)
    except Exception:
        _report_handler_error()


def _unsubscribe(event, handler):
    try:
        event -= handler
    except Exception:
        _report_handler_error()


def subscribe():
    unsubscribe()
    import scriptcontext as sc

    handlers = (EndCommandHandler, CloseDocumentHandler)
    sc.sticky[HANDLER_KEY] = handlers
    Rhino.Commands.Command.EndCommand += EndCommandHandler
    Rhino.RhinoDoc.CloseDocument += CloseDocumentHandler


def unsubscribe():
    import scriptcontext as sc

    scheduler.disarm()

    stored_handlers = sc.sticky.pop(HANDLER_KEY, ())
    events = (
        Rhino.Commands.Command.EndCommand,
        Rhino.RhinoDoc.CloseDocument,
    )
    for handler, event in zip(stored_handlers, events):
        _unsubscribe(event, handler)
