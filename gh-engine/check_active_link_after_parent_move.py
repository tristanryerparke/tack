"""Move the active TackGH parent and report whether Grasshopper auto-updated child.

This intentionally does *not* call ghdoc.NewSolution(True) before the first check.
It tells us whether the generated GH document's referenced params noticed the
Rhino object replacement by themselves.
"""

import os
import sys
import time
import traceback

PROJECT_ROOT = os.path.dirname(os.path.dirname(__file__))
GH_ENGINE_DIR = os.path.dirname(__file__)
for path in (PROJECT_ROOT, GH_ENGINE_DIR):
    if path not in sys.path:
        sys.path.insert(0, path)

import Rhino
import scriptcontext as sc
import System
from Rhino.Commands import Result

import add_tack_gh


def _active_item():
    links = sc.sticky.get(add_tack_gh.STICKY_KEY, {})
    if not links:
        return None
    return list(links.items())[-1]


def _relation_error(doc, state):
    parent_point = add_tack_gh.resolve_brep_vertex(
        doc,
        state["parent_id"],
        state["parent_index"],
    )
    child_point = add_tack_gh.resolve_brep_vertex(
        doc,
        state["child_id"],
        state["child_index"],
    )
    expected = Rhino.Geometry.Vector3d(*state["relation"])
    actual = child_point - parent_point
    return (actual - expected).Length, actual, expected


def _move_object(doc, object_id, vector):
    obj = doc.Objects.Find(System.Guid(str(object_id)))
    geometry = obj.Geometry.Duplicate()
    geometry.Transform(Rhino.Geometry.Transform.Translation(vector))
    return doc.Objects.Replace(System.Guid(str(object_id)), geometry)


def RunCommand(is_interactive):
    doc = Rhino.RhinoDoc.ActiveDoc
    if doc is None:
        return Result.Cancel
    item = _active_item()
    if item is None:
        print("[TackGH check] no active TackGH sticky link")
        return Result.Failure

    key, record = item
    state = record["state"]
    ghdoc = record["ghdoc"]
    before_solves = state.get("solve_count", 0)
    print("[TackGH check] testing link {} before_solves={}".format(key, before_solves))

    try:
        if not _move_object(doc, state["parent_id"], Rhino.Geometry.Vector3d(3, 0, 0)):
            print("[TackGH check] parent move failed")
            return Result.Failure
        doc.Views.Redraw()

        deadline = time.time() + 2.0
        while time.time() < deadline:
            Rhino.RhinoApp.Wait()
            error, actual, expected = _relation_error(doc, state)
            if error <= max(doc.ModelAbsoluteTolerance, 1e-6):
                print(
                    "[TackGH check] AUTO PASS error={:.6f} solves={} expected=({:.3f}, {:.3f}, {:.3f}) actual=({:.3f}, {:.3f}, {:.3f})".format(
                        error,
                        state.get("solve_count", 0),
                        expected.X,
                        expected.Y,
                        expected.Z,
                        actual.X,
                        actual.Y,
                        actual.Z,
                    )
                )
                return Result.Success

        auto_error, actual, expected = _relation_error(doc, state)
        print(
            "[TackGH check] AUTO MISS error={:.6f} solves={}; forcing one GH solution now".format(
                auto_error,
                state.get("solve_count", 0),
            )
        )
        ghdoc.NewSolution(True)
        forced_error, actual, expected = _relation_error(doc, state)
        print(
            "[TackGH check] FORCED error={:.6f} solves={} expected=({:.3f}, {:.3f}, {:.3f}) actual=({:.3f}, {:.3f}, {:.3f})".format(
                forced_error,
                state.get("solve_count", 0),
                expected.X,
                expected.Y,
                expected.Z,
                actual.X,
                actual.Y,
                actual.Z,
            )
        )
        return Result.Success if forced_error <= max(doc.ModelAbsoluteTolerance, 1e-6) else Result.Failure
    except Exception:
        traceback.print_exc()
        return Result.Failure


if __name__ == "__main__":
    from tack.watcher import run_entrypoint

    run_entrypoint(lambda: RunCommand(True), True)
