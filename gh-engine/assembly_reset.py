"""Reset the active AssemblyGH session and remove its generated GH document."""

import importlib
import os
import sys
import traceback

PROJECT_ROOT = os.path.dirname(os.path.dirname(__file__))
GH_ENGINE_DIR = os.path.dirname(__file__)
for path in (PROJECT_ROOT, GH_ENGINE_DIR):
    if path not in sys.path:
        sys.path.insert(0, path)

from Rhino.Commands import Result


def _reload_assembly_modules():
    importlib.invalidate_caches()
    import assembly.features as features
    import assembly.bodies as bodies
    import assembly.component_io as component_io
    import assembly.content_cache as content_cache
    import assembly.joint_records as joint_records
    import assembly.mate_records as mate_records
    import assembly.session as session_module

    importlib.reload(features)
    importlib.reload(bodies)
    importlib.reload(component_io)
    importlib.reload(content_cache)
    importlib.reload(joint_records)
    importlib.reload(mate_records)
    importlib.reload(session_module)
    return session_module


def RunCommand(is_interactive):
    try:
        session_module = _reload_assembly_modules()
        active_session = session_module.get_active_session(False)
        removed_saved = []
        if active_session is not None:
            removed_saved.extend(session_module._delete_session_files(active_session))
        removed = session_module.reset_session(remove_document=True, remove_metadata=False)
        removed_saved.extend(session_module.clear_saved_sessions())
        removed_saved = sorted(set(removed_saved))
        print("AssemblyGH reset: removed active session={}".format(removed))
        if removed_saved:
            print("AssemblyGH reset: removed saved generated session file(s):")
            for path in removed_saved:
                print("  {}".format(path))
        else:
            print("AssemblyGH reset: no saved generated session files found")
        return Result.Success
    except Exception:
        traceback.print_exc()
        return Result.Failure


if __name__ == "__main__":
    from tack.watcher import run_entrypoint

    run_entrypoint(lambda: RunCommand(True), True)
