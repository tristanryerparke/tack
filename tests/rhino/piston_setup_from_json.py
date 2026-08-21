import json
import os
import sys

sys.modules.pop("common", None)

import Rhino
from Rhino.Geometry import Point3d, Vector3d

from common import run_step
from common import sc

PROJECT_ROOT = sc.sticky.get("PROJECT_ROOT") or "/Users/tristanryerparke/projects-local/tack"

from ondsel.assembly import assembly_common
from ondsel.assembly import assembly_model
from ondsel.assembly import assembly_scheduler


def _brep(rhino_object):
    geometry = rhino_object.Geometry
    if isinstance(geometry, Rhino.Geometry.Brep):
        return geometry
    return geometry.ToBrep()


def _find_object(doc, object_id):
    rhino_object = doc.Objects.FindId(assembly_common.parse_guid(object_id))
    assert rhino_object is not None, "Missing object {}".format(object_id)
    return rhino_object


def _revolute_side(doc, side):
    rhino_object = _find_object(doc, side["object_id"])
    brep = _brep(rhino_object)
    edge_index = int(side["edge_index"])
    assert 0 <= edge_index < brep.Edges.Count, "Edge {} out of range".format(edge_index)
    assert (
        assembly_common.circle_from_edge(
            brep.Edges[edge_index], doc.ModelAbsoluteTolerance
        )
        is not None
    ), "Recorded edge {} on {} is not circular".format(edge_index, side["object_id"])
    return {
        "object_id": assembly_common.parse_guid(side["object_id"]),
        "edge_index": edge_index,
    }


def _plane_record(doc, rhino_object, edge_index):
    brep = _brep(rhino_object)
    edge = brep.Edges[int(edge_index)]
    circle = assembly_common.circle_from_edge(edge, doc.ModelAbsoluteTolerance)
    assert circle is not None, "Edge {} is not circular".format(edge_index)
    plane = circle.Plane
    return {
        "edge_index": int(edge_index),
        "radius": circle.Radius,
        "origin": [plane.Origin.X, plane.Origin.Y, plane.Origin.Z],
        "normal": [plane.Normal.X, plane.Normal.Y, plane.Normal.Z],
    }


def _current_planes(doc, records):
    by_object = {}
    for record in records:
        if record["type"] == "anchor":
            by_object.setdefault(record["object_id"], {"roles": [], "planes": []})[
                "roles"
            ].append("anchor")
        elif record["type"] == "revolute":
            for role in ("a", "b"):
                side = record[role]
                entry = by_object.setdefault(
                    side["object_id"], {"roles": [], "planes": []}
                )
                entry["roles"].append("revolute_" + role)
                entry["planes"].append(
                    _plane_record(
                        doc,
                        _find_object(doc, side["object_id"]),
                        side["edge_index"],
                    )
                )
        elif record["type"] == "slider":
            entry = by_object.setdefault(
                record["object_id"], {"roles": [], "planes": []}
            )
            entry["roles"].append("slider")
            rhino_object = _find_object(doc, record["object_id"])
            for edge_index in record["edge_indexes"]:
                entry["planes"].append(
                    _plane_record(doc, rhino_object, edge_index)
                )

    result = []
    for object_id, entry in by_object.items():
        result.append(
            {
                "object_id": object_id,
                "name": _find_object(doc, object_id).Name,
                "roles": entry["roles"],
                "planes": entry["planes"],
            }
        )
    return result


def _apply_anchor(doc, record):
    rhino_object = _find_object(doc, record["object_id"])
    assert assembly_model.add_world_anchor(doc, rhino_object), "Anchor failed"
    assembly_scheduler.solve_now(doc)


def _apply_revolute(doc, record):
    joint = assembly_model.add_revolute(
        doc,
        _revolute_side(doc, record["a"]),
        _revolute_side(doc, record["b"]),
    )
    assert joint is not None, "Revolute {} failed".format(record)
    assembly_scheduler.solve_now(doc)


def _apply_slider(doc, record):
    rhino_object = _find_object(doc, record["object_id"])
    brep = _brep(rhino_object)
    circles = []
    for edge_index in record["edge_indexes"]:
        circle = assembly_common.circle_from_edge(
            brep.Edges[int(edge_index)], doc.ModelAbsoluteTolerance
        )
        assert circle is not None, "Slider edge {} not circular".format(edge_index)
        circles.append(circle)

    part_direction = circles[1].Center - circles[0].Center
    assert part_direction.Unitize() and not part_direction.IsTiny(), (
        "Slider edge centers are not distinct"
    )
    world_origin = Point3d(*record["world_axis_origin"])
    world_direction = Vector3d(*record["world_axis_direction"])

    assembly_model._set_command_busy(doc, True)
    try:
        assembly_model.prealign_slider_child(
            doc,
            rhino_object,
            circles[0].Center,
            part_direction,
            world_origin,
            world_direction,
        )
        part = assembly_model.add_slider_axis(
            doc,
            rhino_object,
            world_origin,
            world_direction,
            world_origin,
            world_direction,
        )
    finally:
        assembly_model._set_command_busy(doc, False)
    assert part is not None, "Slider failed"
    assembly_scheduler.solve_now(doc)


def setup():
    doc = sc.doc
    assert doc is not None, "Open a Rhino document before running this test"

    json_path = os.environ.get("PISTON_SETUP_JSON")
    assert json_path, "PISTON_SETUP_JSON environment variable is not set"
    with open(json_path) as handle:
        records = json.load(handle)["records"]
    assert records, "Setup JSON has no records"

    assembly_model.unsubscribe()
    assembly_model.clear(doc)
    assembly_model.subscribe()

    for record in records:
        if record["type"] == "anchor":
            _apply_anchor(doc, record)
        elif record["type"] == "revolute":
            _apply_revolute(doc, record)
        elif record["type"] == "slider":
            _apply_slider(doc, record)
        else:
            raise AssertionError("Unknown record type {}".format(record["type"]))

    data = assembly_model.read_data(doc)
    return {
        "part_count": len(data["parts"]),
        "constraint_count": len(data["constraints"]),
        "constraint_types": sorted(c["type"] for c in data["constraints"]),
        "part_ids": sorted(key[:8] for key in data["parts"]),
        "plane_records": {"parts": _current_planes(doc, records)},
    }


run_step("piston_setup_from_json", setup, send_done=True)
