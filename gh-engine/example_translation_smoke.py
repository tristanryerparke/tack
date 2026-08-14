"""Example smoke test for the TackGH proof of concept.

This creates two boxes, builds the generated Grasshopper document without user
picks, moves the parent, solves the GH document, and verifies the child vertex
keeps the same point-to-point relation.
"""

import os
import sys
import traceback

PROJECT_ROOT = os.path.dirname(os.path.dirname(__file__))
GH_ENGINE_DIR = os.path.dirname(__file__)
for path in (PROJECT_ROOT, GH_ENGINE_DIR):
    if path not in sys.path:
        sys.path.insert(0, path)

import Rhino
import System
from Rhino.Commands import Result

import add_tack_gh


def _add_box(doc, x0, y0, z0, size=1.0):
    box = Rhino.Geometry.Box(
        Rhino.Geometry.Plane.WorldXY,
        Rhino.Geometry.Interval(x0, x0 + size),
        Rhino.Geometry.Interval(y0, y0 + size),
        Rhino.Geometry.Interval(z0, z0 + size),
    )
    return doc.Objects.AddBrep(box.ToBrep())


def _replace_moved(doc, object_id, vector):
    obj = doc.Objects.Find(System.Guid(str(object_id)))
    geometry = obj.Geometry.Duplicate()
    geometry.Transform(Rhino.Geometry.Transform.Translation(vector))
    return doc.Objects.Replace(System.Guid(str(object_id)), geometry)


def RunCommand(is_interactive):
    doc = Rhino.RhinoDoc.ActiveDoc
    if doc is None:
        return Result.Cancel

    try:
        parent_id = _add_box(doc, 0, 0, 0)
        child_id = _add_box(doc, 4, 0, 0)
        parent_index = 0
        child_index = 0

        parent_point = add_tack_gh.resolve_brep_vertex(doc, parent_id, parent_index)
        child_point = add_tack_gh.resolve_brep_vertex(doc, child_id, child_index)
        expected_relation = child_point - parent_point

        ghdoc, state, _ = add_tack_gh.create_tack_gh_link(
            doc,
            parent_id,
            child_id,
            parent_index,
            child_index,
            show_grasshopper=False,
            save_definition=True,
        )

        move_vector = Rhino.Geometry.Vector3d(10, 2, 0)
        if not _replace_moved(doc, parent_id, move_vector):
            print("[TackGH smoke] could not move parent")
            return Result.Failure

        ghdoc.NewSolution(True)

        moved_parent_point = add_tack_gh.resolve_brep_vertex(doc, parent_id, parent_index)
        moved_child_point = add_tack_gh.resolve_brep_vertex(doc, child_id, child_index)
        actual_relation = moved_child_point - moved_parent_point
        error = (actual_relation - expected_relation).Length

        print(
            "[TackGH smoke] expected_relation=({:.3f}, {:.3f}, {:.3f}) actual_relation=({:.3f}, {:.3f}, {:.3f}) error={:.6f} solves={}".format(
                expected_relation.X,
                expected_relation.Y,
                expected_relation.Z,
                actual_relation.X,
                actual_relation.Y,
                actual_relation.Z,
                error,
                state.get("solve_count"),
            )
        )
        if error > max(doc.ModelAbsoluteTolerance, 1e-6):
            return Result.Failure
        doc.Views.Redraw()
        return Result.Success
    except Exception:
        traceback.print_exc()
        return Result.Failure


if __name__ == "__main__":
    from tack.watcher import run_entrypoint

    run_entrypoint(lambda: RunCommand(True), True)
