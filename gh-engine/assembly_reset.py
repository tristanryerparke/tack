"""Reset the active AssemblyGH session and remove its generated GH document."""

import os
import sys
import traceback

PROJECT_ROOT = os.path.dirname(os.path.dirname(__file__))
GH_ENGINE_DIR = os.path.dirname(__file__)
for path in (PROJECT_ROOT, GH_ENGINE_DIR):
    if path not in sys.path:
        sys.path.insert(0, path)

from Rhino.Commands import Result

from assembly.session import reset_session


def RunCommand(is_interactive):
    try:
        removed = reset_session(remove_document=True)
        print("AssemblyGH reset: removed active session={}".format(removed))
        return Result.Success
    except Exception:
        traceback.print_exc()
        return Result.Failure


if __name__ == "__main__":
    from tack.watcher import run_entrypoint

    run_entrypoint(lambda: RunCommand(True), True)
