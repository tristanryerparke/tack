import importlib
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import Rhino
from Rhino.Commands import Result

import tack

importlib.reload(tack).reload()


BREP_EDGE_COMPONENT_TYPE = Rhino.Geometry.ComponentIndexType.BrepEdge
BREP_TRIM_COMPONENT_TYPE = Rhino.Geometry.ComponentIndexType.BrepTrim


def _brep_from_rhino_object(rhino_object):
    if rhino_object is None:
        return None
    geometry = rhino_object.Geometry
    if isinstance(geometry, Rhino.Geometry.Brep):
        return geometry
    if hasattr(geometry, "ToBrep"):
        return geometry.ToBrep()
    return None


def _brep_edge_only_filter(rhino_object, geometry, component_index):
    """Accept one selectable trim for each topological BrepEdge."""
    component_type = component_index.ComponentIndexType
    if component_type == BREP_EDGE_COMPONENT_TYPE:
        return True
    if isinstance(geometry, Rhino.Geometry.BrepEdge):
        return True
    if component_type != BREP_TRIM_COMPONENT_TYPE:
        return False

    brep = _brep_from_rhino_object(rhino_object)
    trim_index = component_index.Index
    if brep is None or trim_index < 0 or trim_index >= brep.Trims.Count:
        return False

    trim = brep.Trims[trim_index]
    edge = trim.Edge
    if edge is None:
        return False

    trim_indices = list(edge.TrimIndices())
    return bool(trim_indices) and trim.TrimIndex == trim_indices[0]


def _edge_parameter(edge, pick_point):
    closest = edge.ClosestPoint(pick_point)
    if isinstance(closest, tuple):
        ok, parameter = closest
        if ok:
            return parameter
        return None
    if closest:
        return closest
    return None


def _data_from_obj_ref(obj_ref):
    edge = obj_ref.Edge()
    brep = obj_ref.Brep()
    rhino_object = obj_ref.Object()

    if edge is None or brep is None or rhino_object is None:
        return None

    pick_point = obj_ref.SelectionPoint()
    component_index = obj_ref.GeometryComponentIndex

    return {
        "object_id": obj_ref.ObjectId,
        "rhino_object": rhino_object,
        "brep": brep,
        "edge": edge,
        "edge_index": edge.EdgeIndex,
        "component_index": component_index,
        "component_index_type": component_index.ComponentIndexType,
        "component_index_index": component_index.Index,
        "pick_point": pick_point,
        "edge_parameter": _edge_parameter(edge, pick_point),
        "edge_domain": edge.Domain,
        "edge_length": edge.GetLength(),
        "adjacent_face_indices": list(edge.AdjacentFaces()),
    }


def _unique_edge_data(getter):
    edge_data = []
    seen = set()
    for index in range(getter.ObjectCount):
        data = _data_from_obj_ref(getter.Object(index))
        if data is None:
            continue

        key = (data["object_id"], data["edge_index"])
        if key in seen:
            continue

        seen.add(key)
        edge_data.append(data)
    return edge_data


def prompt_for_one_brep_edge_then_done(prompt="Select one Brep edge"):
    """Select one Brep edge and keep it highlighted until Done/Enter."""
    getter = Rhino.Input.Custom.GetObject()
    getter.SetCommandPrompt(prompt)
    getter.SetPressEnterWhenDonePrompt("Press Enter when done")
    getter.GeometryFilter = Rhino.DocObjects.ObjectType.EdgeFilter
    getter.SetCustomGeometryFilter(_brep_edge_only_filter)
    getter.SubObjectSelect = True
    getter.ChooseOneQuestion = False
    getter.AlreadySelectedObjectSelect = True
    getter.EnablePreSelect(True, True)
    getter.EnablePostSelect(True)

    # minimumNumber=1, maximumNumber=0 keeps Rhino in the same GetObject
    # session after the first edge, so the selected edge stays highlighted
    # while Rhino asks for Done/Enter.
    result = getter.GetMultiple(1, 0)
    if result != Rhino.Input.GetResult.Object:
        return None

    edge_data = _unique_edge_data(getter)
    if len(edge_data) != 1:
        print("Select exactly one Brep edge; got {}.".format(len(edge_data)))
        return None

    return edge_data[0]


def _print_edge_data(index, data):
    print("Edge {}:".format(index + 1))
    print("  object_id: {}".format(data["object_id"]))
    print("  edge_index: {}".format(data["edge_index"]))
    print("  component_index: {}".format(data["component_index"]))
    print("  component_index_type: {}".format(data["component_index_type"]))
    print("  component_index_index: {}".format(data["component_index_index"]))
    print("  pick_point: {}".format(data["pick_point"]))
    print("  edge_parameter: {}".format(data["edge_parameter"]))
    print("  edge_domain: {}".format(data["edge_domain"]))
    print("  edge_length: {}".format(data["edge_length"]))
    print("  adjacent_face_indices: {}".format(data["adjacent_face_indices"]))


def RunCommand(is_interactive):
    edge = prompt_for_one_brep_edge_then_done()
    if edge is None:
        print("No Brep edge accepted.")
        return Result.Cancel

    print("Accepted Brep edge:")
    _print_edge_data(0, edge)
    return Result.Success


if __name__ == "__main__":
    from tack.watcher import run_entrypoint

    # This example is intended to be run by rhino-watch, so always enable
    # the watcher connection and send a done/quit lifecycle message.
    run_entrypoint(lambda: RunCommand(True), True)
