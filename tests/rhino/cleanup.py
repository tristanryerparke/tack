import sys

sys.modules.pop("common", None)

from common import STATE_KEY
from common import pause
from common import rs
from common import run_step
from common import sc
from common import tack_modules


def cleanup():
    handlers, _, runtime, _, _ = tack_modules()
    handlers.unsubscribe()
    runtime.stop_runtime()

    doc = sc.doc
    state = sc.sticky.pop(STATE_KEY, {})
    for object_id in (state.get("parent_id"), state.get("child_id")):
        if object_id is not None and doc.Objects.Find(object_id) is not None:
            rs.DeleteObject(object_id)
    doc.Views.Redraw()
    pause("fixture removed")


run_step("cleanup_coincident_pair", cleanup)
