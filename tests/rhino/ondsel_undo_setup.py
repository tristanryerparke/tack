import sys

sys.modules.pop("common", None)

import Rhino

from common import rs
from common import run_step
from common import sc

PROJECT_ROOT = sc.sticky.get("PROJECT_ROOT") or "/Users/tristanryerparke/projects-local/tack"

from ondsel.assembly import assembly_common
from ondsel.assembly import assembly_model
from ondsel.assembly import assembly_scheduler


STATE_KEY = "Ondsel.IntegrationTest.UndoBundling"


def _circular_edge_index(doc, object_id):
    obj = doc.Objects.FindId(object_id)
    brep = (
        obj.Geometry
        if isinstance(obj.Geometry, Rhino.Geometry.Brep)
        else obj.Geometry.ToBrep()
    )
    for index in range(brep.Edges.Count):
        if (
            assembly_common.circle_from_edge(
                brep.Edges[index], doc.ModelAbsoluteTolerance
            )
            is not None
        ):
            return index
    return None


def _center(doc, object_id):
    from ondsel.assembly import assembly_common

    obj = doc.Objects.FindId(assembly_common.parse_guid(object_id))
    assert obj is not None, "Missing object {}".format(object_id)
    center = obj.Geometry.GetBoundingBox(True).Center
    return [center.X, center.Y, center.Z]


def setup():
    doc = sc.doc
    assert doc is not None, "Open a Rhino document before running this test"

    assembly_model.unsubscribe()
    assembly_model.subscribe()

    base_id = rs.AddCylinder((0, 0, 0), 5, 2)
    child_id = rs.AddCylinder((10, 0, 0), 5, 2)
    assert base_id and child_id, "Could not create the test cylinders"

    base_edge = _circular_edge_index(doc, base_id)
    child_edge = _circular_edge_index(doc, child_id)
    assert base_edge is not None and child_edge is not None, (
        "Cylinders expose no circular edges"
    )

    assert assembly_model.add_world_anchor(doc, doc.Objects.FindId(base_id))
    joint = assembly_model.add_revolute(
        doc,
        {"object_id": base_id, "edge_index": base_edge},
        {"object_id": child_id, "edge_index": child_edge},
    )
    assert joint is not None, "Could not add the revolute joint"

    # Initial solve: the world anchor holds the base, the revolute joint
    # snaps the child onto the base. This settles the assembly.
    assembly_scheduler.solve_now(doc)

    data = assembly_model.read_data(doc)
    world_anchor = next(
        c for c in data["constraints"] if c.get("type") == "world_anchor"
    )
    revolute = next(
        c for c in data["constraints"] if c.get("type") == "revolute"
    )
    live_base_id = world_anchor["part"]
    live_child_id = revolute["b"]["part"]
    assert revolute["a"]["part"] == live_base_id, (
        "Revolute parent should be the anchored base"
    )

    sc.sticky[STATE_KEY] = {
        "base_object_id": live_base_id,
        "child_object_id": live_child_id,
        "original_base": _center(doc, live_base_id),
        "original_child": _center(doc, live_child_id),
    }

    rs.UnselectAllObjects()
    assert rs.SelectObject(live_child_id), "Could not select the child cylinder"
    return {"child_selected": str(live_child_id)}


run_step("ondsel_undo_setup", setup)
