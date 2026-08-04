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
from tack import utils


def RunCommand(is_interactive):
    doc = Rhino.RhinoDoc.ActiveDoc
    if doc is None:
        return Result.Cancel

    handlers.unsubscribe()
    print("Tack handlers paused.")
    return Result.Success


if __name__ == "__main__":
    if not utils.DEBUG:
        RunCommand(True)
    else:
        try:
            from rhino_watcher import try_send_end_sync
            from rhino_watcher import try_send_quit_sync
            from rhino_watcher import websocket_output_if_available_sync
        except ImportError:
            RunCommand(True)
        else:
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
