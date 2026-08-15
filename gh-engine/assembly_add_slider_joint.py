"""Add a Fusion-style slider joint between a body feature and a fixed axis."""

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

from assembly.edge_refs import EdgePromptCancelled, EdgeReferenceError, prompt_for_circular_brep_edge
from assembly.prompts import PromptCancelled, pick_axis_by_two_points


def _reload_assembly_modules():
    importlib.invalidate_caches()
    import assembly.features as features
    import assembly.bodies as bodies
    import assembly.component_io as component_io
    import assembly.content_cache as content_cache
    import assembly.joint_records as joint_records
    import assembly.session as session_module
    import assembly.generate_definition as generate_definition

    importlib.reload(features)
    importlib.reload(bodies)
    importlib.reload(component_io)
    importlib.reload(content_cache)
    importlib.reload(joint_records)
    importlib.reload(session_module)
    importlib.reload(generate_definition)
    return joint_records, session_module, generate_definition


def RunCommand(is_interactive):
    try:
        edge = prompt_for_circular_brep_edge(
            "Select circular/arc edge(s) on sliding body, then Enter",
            role="slider_body",
        )
        axis = pick_axis_by_two_points(
            "Pick fixed slider axis start point",
            "Pick fixed slider axis end point",
            role="fixed_slider_axis",
            source="two_points",
        )
        joint_records, session_module, generate_definition = _reload_assembly_modules()
        record = joint_records.slider_joint_record(body_edge=edge, axis=axis)
        session = session_module.append_joint(record)
        session_module.recreate_session_document(session)
        generate_definition.rebuild_session_definition(session)
        print("Added slider joint {}".format(record["id"][:8]))
        print(session_module.session_summary(session))
        return Result.Success
    except (PromptCancelled, EdgePromptCancelled) as error:
        print("AssemblyGH slider joint cancelled: {}".format(error))
        return Result.Cancel
    except EdgeReferenceError as error:
        print("AssemblyGH slider joint invalid selection: {}".format(error))
        return Result.Failure
    except Exception:
        traceback.print_exc()
        return Result.Failure


if __name__ == "__main__":
    from tack.watcher import run_entrypoint

    run_entrypoint(lambda: RunCommand(True), True)
