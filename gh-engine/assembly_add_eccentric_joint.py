"""Prompt for an edge-metadata eccentric-joint/crank-slider mate.

The mate source of truth is Rhino object id + Brep edge index metadata. The
generated GH document is rebuilt from these mate records.
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

from assembly.edge_refs import (
    EdgePromptCancelled,
    EdgeReferenceError,
    prompt_for_circular_brep_edge,
    require_different_object,
    require_same_object,
)
from assembly.prompts import PromptCancelled, pick_axis_by_two_points


def _reload_assembly_modules():
    import assembly.component_io as component_io
    import assembly.content_cache as content_cache
    import assembly.edge_refs as edge_refs
    import assembly.mate_records as mate_records
    import assembly.session as session_module
    import assembly.generate_definition as generate_definition

    importlib.reload(component_io)
    importlib.reload(content_cache)
    importlib.reload(edge_refs)
    importlib.reload(mate_records)
    importlib.reload(session_module)
    importlib.reload(generate_definition)
    return mate_records, session_module, generate_definition


def _point(values):
    return Rhino.Geometry.Point3d(float(values[0]), float(values[1]), float(values[2]))


def _distance(first, second):
    return _point(first).DistanceTo(_point(second))


def RunCommand(is_interactive):
    try:
        rotator_shaft_edge = prompt_for_circular_brep_edge(
            "Select circular/arc shaft edge(s) on eccentric cam/crank object, then Enter",
            role="rotator_shaft_edge",
        )
        shaft_axis = pick_axis_by_two_points(
            "Pick shaft axis start point",
            "Pick shaft axis end point",
            role="shaft_axis",
            source="two_points",
        )
        eccentric_pin_edge = prompt_for_circular_brep_edge(
            "Select circular/arc eccentric pin edge(s) on the same eccentric cam/crank object, then Enter",
            role="eccentric_pin_edge",
        )
        require_same_object(
            rotator_shaft_edge,
            eccentric_pin_edge,
            "Shaft edge and eccentric pin edge must belong to the same eccentric cam/crank Brep.",
        )

        rod_big_edge = prompt_for_circular_brep_edge(
            "Select circular/arc rod edge(s) that mate to the eccentric pin, then Enter",
            role="rod_big_edge",
        )
        require_different_object(
            eccentric_pin_edge,
            rod_big_edge,
            "Rod eccentric-end edge must be on a different Brep than the eccentric cam/crank.",
        )

        rod_small_edge = prompt_for_circular_brep_edge(
            "Select circular/arc rod edge(s) that mate to the piston wrist pin, then Enter",
            role="rod_small_edge",
        )
        require_same_object(
            rod_big_edge,
            rod_small_edge,
            "Both rod mate edges must belong to the same connecting rod Brep.",
        )

        piston_pin_edge = prompt_for_circular_brep_edge(
            "Select circular/arc piston wrist-pin edge(s) that mate to the rod, then Enter",
            role="piston_pin_edge",
        )
        require_different_object(
            rod_small_edge,
            piston_pin_edge,
            "Piston wrist-pin edge must be on a different Brep than the connecting rod.",
        )

        piston_axis = pick_axis_by_two_points(
            "Pick piston slide axis start point",
            "Pick piston slide axis end point",
            role="piston_axis",
            source="two_points",
        )

        rod_length = _distance(rod_big_edge["center"], rod_small_edge["center"])

        mate_records, session_module, generate_definition = _reload_assembly_modules()
        record = mate_records.eccentric_joint_record(
            rotator_shaft_edge=rotator_shaft_edge,
            shaft_axis=shaft_axis,
            eccentric_pin_edge=eccentric_pin_edge,
            rod_big_edge=rod_big_edge,
            rod_small_edge=rod_small_edge,
            piston_pin_edge=piston_pin_edge,
            piston_axis=piston_axis,
            rod_length=rod_length,
        )
        session = session_module.append_mate(record)
        session_module.recreate_session_document(session)
        generate_definition.rebuild_session_definition(session)
        print("Added eccentric joint mate {}".format(record["id"][:8]))
        print("Rod length from rod edge centers: {:.3f}".format(rod_length))
        print(session_module.session_summary(session))
        return Result.Success
    except (PromptCancelled, EdgePromptCancelled) as error:
        print("AssemblyGH eccentric joint cancelled: {}".format(error))
        return Result.Cancel
    except EdgeReferenceError as error:
        print("AssemblyGH eccentric joint invalid selection: {}".format(error))
        return Result.Failure
    except Exception:
        traceback.print_exc()
        return Result.Failure


if __name__ == "__main__":
    from tack.watcher import run_entrypoint

    run_entrypoint(lambda: RunCommand(True), True)
