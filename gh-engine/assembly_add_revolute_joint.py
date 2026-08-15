"""Add a Fusion-style revolute joint between two circular Brep edge features."""

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

from assembly.edge_refs import EdgePromptCancelled, EdgeReferenceError, prompt_for_circular_brep_edge, require_different_object


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
        edge_a = prompt_for_circular_brep_edge(
            "Select circular/arc edge(s) for revolute joint body A, then Enter",
            role="revolute_a",
        )
        edge_b = prompt_for_circular_brep_edge(
            "Select circular/arc edge(s) for revolute joint body B, then Enter",
            role="revolute_b",
        )
        require_different_object(edge_a, edge_b, "A revolute body-to-body joint needs two different Breps.")

        joint_records, session_module, generate_definition = _reload_assembly_modules()
        record = joint_records.revolute_joint_record(edge_a=edge_a, edge_b=edge_b)
        session = session_module.append_joint(record)
        session_module.recreate_session_document(session)
        generate_definition.rebuild_session_definition(session)
        print("Added revolute joint {}".format(record["id"][:8]))
        print(session_module.session_summary(session))
        return Result.Success
    except EdgePromptCancelled as error:
        print("AssemblyGH revolute joint cancelled: {}".format(error))
        return Result.Cancel
    except EdgeReferenceError as error:
        print("AssemblyGH revolute joint invalid selection: {}".format(error))
        return Result.Failure
    except Exception:
        traceback.print_exc()
        return Result.Failure


if __name__ == "__main__":
    from tack.watcher import run_entrypoint

    run_entrypoint(lambda: RunCommand(True), True)
