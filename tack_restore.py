import importlib

import Rhino
from Rhino.Commands import Result

import tack

importlib.reload(tack).reload()

from tack import handlers
from tack import metadata
from tack import runtime


def RunCommand(is_interactive):
    doc = Rhino.RhinoDoc.ActiveDoc
    if doc is None:
        return Result.Cancel

    handlers.unsubscribe()
    runtime.stop_runtime()

    restored = 0
    for saved_link in metadata.all_links(doc):
        if runtime.start_runtime(
            saved_link["parent_id"],
            saved_link["child_id"],
            saved_link["link_id"],
        ):
            restored += 1
        else:
            print(
                "Could not restore Tack {}.".format(saved_link["link_id"])
            )

    handlers.subscribe()
    if restored:
        print("Restored {} Tack relationship(s).".format(restored))
        return Result.Success

    print("No saved Tack relationships found.")
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
