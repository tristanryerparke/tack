import importlib

import Rhino
from Rhino.Commands import Result

import tack

importlib.reload(tack).reload()

from tack import handlers
from tack import metadata
from tack import runtime


def _clear_object_metadata(doc, object_id):
    obj = doc.Objects.Find(object_id)
    if obj is None:
        return

    attrs = obj.Attributes.Duplicate()
    changed = False
    for key in (
        metadata.LINK_KEY,
        metadata.CHILD_KEY,
    ):
        try:
            if attrs.UserDictionary.ContainsKey(key):
                attrs.UserDictionary.Remove(key)
                changed = True
        except Exception:
            pass
    if changed:
        doc.Objects.ModifyAttributes(object_id, attrs, True)


def RunCommand(is_interactive):
    doc = Rhino.RhinoDoc.ActiveDoc
    if doc is None:
        return Result.Cancel

    handlers.unsubscribe()
    runtime.stop_runtime()
    for obj in doc.Objects:
        if obj is not None:
            _clear_object_metadata(doc, obj.Id)

    doc.Views.Redraw()
    print("Tack anchor links cleared. Save the file to keep the cleanup.")
    return Result.Success


if __name__ == "__main__":
    import traceback

    from rhino_watcher import try_send_end_sync
    from rhino_watcher import try_send_quit_sync
    from rhino_watcher import websocket_output_if_available_sync

    try:
        with websocket_output_if_available_sync():
            result = RunCommand(True)
    except Exception:
        with websocket_output_if_available_sync():
            traceback.print_exc()
        try_send_quit_sync()
    else:
        if result == Result.Success:
            try_send_end_sync()
        else:
            try_send_quit_sync()
