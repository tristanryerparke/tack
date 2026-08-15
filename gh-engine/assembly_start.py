"""Start or reuse an AssemblyGH generated Grasshopper session.

Do not run from the agent automatically. Run in Rhino when ready:

    uv run rhino-watch gh-engine/assembly_start.py --debug
"""

import os
import sys
import traceback

PROJECT_ROOT = os.path.dirname(os.path.dirname(__file__))
GH_ENGINE_DIR = os.path.dirname(__file__)
for path in (PROJECT_ROOT, GH_ENGINE_DIR):
    if path not in sys.path:
        sys.path.insert(0, path)

import importlib

import Rhino
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
    import assembly.generate_definition as generate_definition

    importlib.reload(features)
    importlib.reload(bodies)
    importlib.reload(component_io)
    importlib.reload(content_cache)
    importlib.reload(joint_records)
    importlib.reload(mate_records)
    importlib.reload(session_module)
    importlib.reload(generate_definition)
    return session_module, generate_definition


def _show_grasshopper_window():
    Rhino.RhinoApp.RunScript("_-Grasshopper _Window _Show _Enter", False)


def RunCommand(is_interactive):
    try:
        _show_grasshopper_window()
        session_module, generate_definition = _reload_assembly_modules()
        session = session_module.get_or_create_session(name="AssemblyGH POC")
        if session.get("mates") or session.get("joints"):
            session_module.recreate_session_document(session)
        generate_definition.rebuild_session_definition(session)
        shown = session_module.show_session_document(session)
        print("AssemblyGH visible canvas document={}".format(shown))
        print(session_module.session_summary(session))
        return Result.Success
    except Exception:
        traceback.print_exc()
        return Result.Failure


if __name__ == "__main__":
    from tack.watcher import run_entrypoint

    run_entrypoint(lambda: RunCommand(True), True)
