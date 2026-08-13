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


def RunCommand(is_interactive):
    doc = Rhino.RhinoDoc.ActiveDoc
    if doc is None:
        return Result.Cancel

    utils.load_document_settings(doc)
    display_enabled = utils.saved_document_display_enabled(doc)

    handlers.unsubscribe()
    runtime.stop_runtime(doc)

    restored = 0
    for saved_link in metadata.all_links(doc):
        if runtime.start_runtime(
            doc,
            saved_link["parent_id"],
            saved_link["child_id"],
            saved_link["link_id"],
            redraw=False,
        ):
            restored += 1
        else:
            print(
                "Could not restore Tack {}.".format(saved_link["link_id"])
            )

    if restored and display_enabled is not None:
        if display_enabled:
            runtime.show_display(doc)
        else:
            runtime.hide_display(doc)

    handlers.subscribe()
    doc.Views.Redraw()
    if restored:
        print("Restored {} Tack relationship(s).".format(restored))
        return Result.Success

    print("No saved Tack relationships found.")
    return Result.Cancel


if __name__ == "__main__":
    from tack.watcher import run_entrypoint

    run_entrypoint(lambda: RunCommand(True), utils.DEBUG)
