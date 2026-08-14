"""Reset the TackGH proof-of-concept runtime.

Run with:

    uv run rhino-watch gh-engine/reset_tack_gh.py --debug

This clears what `gh-engine/add_tack_gh.py` and the GH POC tests add at runtime:
- sticky-tracked generated GH documents
- orphaned generated/test GH documents identifiable by TackGH group titles
- GH SolutionEnd callbacks
- hidden EndCommand/CloseDocument/Idle handlers
- TackGH display conduit
- TackGH sticky records

It does not delete or restore Rhino model geometry.
"""

import importlib
import os
import sys
import traceback

PROJECT_ROOT = os.path.dirname(os.path.dirname(__file__))
GH_ENGINE_DIR = os.path.dirname(__file__)
for path in (PROJECT_ROOT, GH_ENGINE_DIR):
    if path not in sys.path:
        sys.path.insert(0, path)

import Rhino
from Rhino.Commands import Result

import add_tack_gh

add_tack_gh = importlib.reload(add_tack_gh)


def RunCommand(is_interactive):
    doc = Rhino.RhinoDoc.ActiveDoc
    try:
        add_tack_gh.reset_tack_gh(doc, hide_grasshopper=True)
        return Result.Success
    except Exception:
        traceback.print_exc()
        return Result.Failure


if __name__ == "__main__":
    from tack.watcher import run_entrypoint

    run_entrypoint(lambda: RunCommand(True), True)
