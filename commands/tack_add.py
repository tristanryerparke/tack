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
from tack.prompting import command_menu


def _short_id(object_id):
    return str(object_id).split("-", 1)[0]


def RunCommand(is_interactive):
    doc = Rhino.RhinoDoc.ActiveDoc
    if doc is None:
        return Result.Cancel

    handlers.unsubscribe()
    handlers.subscribe()

    picked = command_menu.pick_link(doc)
    if picked is None:
        return Result.Cancel

    parent_id, child_id, parent_anchor, child_anchor = picked
    link_id = metadata.write_link(
        doc,
        parent_id,
        child_id,
        parent_anchor,
        child_anchor,
    )
    if link_id is None:
        utils.debug("[Tack anchor] could not write Tack anchor metadata.")
        return Result.Failure

    if not runtime.start_runtime(doc, parent_id, child_id, link_id):
        utils.debug("[Tack anchor] could not start Tack relationship.")
        return Result.Failure
    utils.debug(
        "[Tack anchor] created link={} parent={} child={}".format(
            _short_id(link_id),
            _short_id(parent_id),
            _short_id(child_id),
        )
    )
    return Result.Success


if __name__ == "__main__":
    from tack.watcher import run_entrypoint

    run_entrypoint(lambda: RunCommand(True), utils.DEBUG)
