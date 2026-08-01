import importlib

import Rhino
import System
from Rhino.Commands import Result

import tack

importlib.reload(tack).reload()

from tack import handlers
from tack import metadata
from tack import runtime
from tack import utils


def RunCommand(is_interactive):
    doc = Rhino.RhinoDoc.ActiveDoc
    if doc is None:
        return Result.Cancel

    handlers.unsubscribe()
    runtime.stop_runtime()
    for child in doc.Objects:
        if child is None:
            continue
        anchor_link = metadata.read_link(child)
        if anchor_link is None:
            continue
        try:
            parent_id = System.Guid.Parse(str(anchor_link["parent_id"]))
        except Exception:
            continue

        parent = doc.Objects.Find(parent_id)
        if parent is None:
            print("Saved parent {} no longer exists.".format(parent_id))
            continue

        stored_child_id = metadata.read_child_id(parent)
        if stored_child_id is None:
            print("Parent {} has no saved child GUID.".format(parent.Id))
            continue
        if not utils.same_id(stored_child_id, child.Id):
            print("Parent/child metadata mismatch; relationship skipped.")
            continue

        if runtime.start_runtime(parent.Id, child.Id):
            handlers.subscribe()
            print("Tack anchor relationship restored.")
            return Result.Success

    print("No saved Tack relationship found.")
    return Result.Cancel


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
