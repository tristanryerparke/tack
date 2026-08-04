import importlib
import os
import sys
import traceback

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import Rhino
from Rhino.Commands import Result

import tack

importlib.reload(tack).reload()

from tack import handlers
from tack import metadata
from tack import runtime
from tack import utils


def _clear_object_metadata(doc, object_id):
    obj = doc.Objects.Find(object_id)
    if obj is None:
        return

    attrs = obj.Attributes.Duplicate()
    changed = False
    for key in (
        metadata.LINKS_KEY,
        metadata.PARENT_LINKS_KEY,
    ):
        try:
            if attrs.UserDictionary.ContainsKey(key):
                attrs.UserDictionary.Remove(key)
                changed = True
        except Exception:
            pass
    if changed:
        doc.Objects.ModifyAttributes(object_id, attrs, True)


def RunCommand(is_interactive, no_metadata=False):
    doc = Rhino.RhinoDoc.ActiveDoc
    if doc is None:
        return Result.Cancel

    handlers.unsubscribe()
    runtime.stop_runtime(doc)
    if not no_metadata:
        for obj in doc.Objects:
            if obj is not None:
                _clear_object_metadata(doc, obj.Id)

    if runtime.has_any_runtime():
        handlers.subscribe()
    doc.Views.Redraw()
    if no_metadata:
        print("Tack runtime cleared. Saved anchor links were preserved.")
    else:
        print("Tack anchor links cleared. Save the file to keep the cleanup.")
    return Result.Success


if __name__ == "__main__":
    def run():
        return RunCommand(
            True,
            no_metadata="--no_metadata" in sys.argv[1:],
        )

    if not utils.DEBUG:
        run()
    else:
        try:
            from rhino_watcher import try_send_end_sync
            from rhino_watcher import try_send_quit_sync
            from rhino_watcher import websocket_output_if_available_sync
        except ImportError:
            run()
        else:
            try:
                with websocket_output_if_available_sync():
                    result = run()
            except Exception:
                with websocket_output_if_available_sync():
                    traceback.print_exc()
                try_send_quit_sync()
            else:
                if result == Result.Success:
                    try_send_end_sync()
                else:
                    try_send_quit_sync()
