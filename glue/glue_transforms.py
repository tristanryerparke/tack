import Rhino
import System

from glue_debug import log
from glue_display import GlueConduit


def _world_spec(reference, vertex_type="", vertex_index=-1):
    return {
        "reference": reference,
        "vertex_type": vertex_type,
        "vertex_index": vertex_index,
        "orientation": "world",
        "x_axis": [1.0, 0.0, 0.0],
        "y_axis": [0.0, 1.0, 0.0],
    }


def _cplane_axes():
    try:
        view = Rhino.RhinoDoc.ActiveDoc.Views.ActiveView
        plane = view.ActiveViewport.ConstructionPlane()
        return (
            [plane.XAxis.X, plane.XAxis.Y, plane.XAxis.Z],
            [plane.YAxis.X, plane.YAxis.Y, plane.YAxis.Z],
        )
    except Exception:
        return [1.0, 0.0, 0.0], [0.0, 1.0, 0.0]


def _choose_vertex(object_id, label):
    getter = Rhino.Input.Custom.GetObject()
    getter.SetCommandPrompt("Select a vertex on the {}".format(label))
    getter.SubObjectSelect = True
    getter.GeometryFilter = (
        Rhino.DocObjects.ObjectType.BrepVertex
        | Rhino.DocObjects.ObjectType.MeshVertex
    )
    getter.EnablePreSelect(False, True)
    log("{} vertex picker started for {}".format(label, object_id))

    result = getter.Get()
    if result != Rhino.Input.GetResult.Object:
        return None

    obj_ref = getter.Object(0)
    component = obj_ref.GeometryComponentIndex
    if obj_ref.ObjectId != object_id:
        print("Select a vertex on the {}.".format(label))
        return None

    supported = (
        Rhino.Geometry.ComponentIndexType.BrepVertex,
        Rhino.Geometry.ComponentIndexType.MeshVertex,
    )
    if component.ComponentIndexType not in supported:
        print("Select a vertex on the {}.".format(label))
        return None

    name = System.Enum.GetName(
        Rhino.Geometry.ComponentIndexType,
        component.ComponentIndexType,
    )
    log(
        "{} vertex: type={}, index={}".format(
            label,
            name,
            component.Index,
        )
    )
    return name, int(component.Index)


def _edge_touches_vertex(obj, vertex_type, edge_index, vertex_index):
    geometry = obj.Geometry
    if vertex_type == "BrepVertex":
        if not hasattr(geometry, "Edges"):
            geometry = geometry.ToBrep(True)
        edge = geometry.Edges[int(edge_index)]
        return (
            edge.StartVertex.VertexIndex == vertex_index
            or edge.EndVertex.VertexIndex == vertex_index
        )
    if vertex_type == "MeshVertex":
        pair = geometry.TopologyEdges.GetTopologyVertices(int(edge_index))
        topology_index = geometry.TopologyVertices.TopologyVertexIndex(vertex_index)
        return pair.I == topology_index or pair.J == topology_index
    return False


def _choose_edge(obj, object_id, vertex_type, vertex_index, label, excluded=None):
    while True:
        getter = Rhino.Input.Custom.GetObject()
        getter.SetCommandPrompt("Select the {} edge".format(label))
        getter.SubObjectSelect = True
        getter.GeometryFilter = Rhino.DocObjects.ObjectType.EdgeFilter
        getter.EnablePreSelect(False, True)
        result = getter.Get()
        if result != Rhino.Input.GetResult.Object:
            return None

        obj_ref = getter.Object(0)
        component = obj_ref.GeometryComponentIndex
        if obj_ref.ObjectId != object_id:
            print("Select an edge on the selected vertex's object.")
            continue
        expected_type = (
            Rhino.Geometry.ComponentIndexType.BrepEdge
            if vertex_type == "BrepVertex"
            else Rhino.Geometry.ComponentIndexType.MeshEdge
        )
        if component.ComponentIndexType != expected_type:
            print("Select an adjoining edge on the selected object.")
            continue
        edge_index = int(component.Index)
        if excluded is not None and edge_index == excluded:
            print("Choose a different edge.")
            continue
        if not _edge_touches_vertex(obj, vertex_type, edge_index, vertex_index):
            print("Choose an edge adjoining the selected vertex.")
            continue
        return edge_index


def _choose_orientation(obj, object_id, spec, label):
    options = Rhino.Input.Custom.GetOption()
    options.SetCommandPrompt("Plane orientation for the {}".format(label))
    options.AcceptNothing(False)
    world_option = options.AddOption("World")
    cplane_option = options.AddOption("CPlane")
    edges_option = None
    if spec["reference"] == "vertex":
        edges_option = options.AddOption("Edges")

    result = options.Get()
    if result != Rhino.Input.GetResult.Option:
        return None

    option_index = options.OptionIndex()
    if option_index == world_option:
        spec["orientation"] = "world"
    elif option_index == cplane_option:
        spec["orientation"] = "cplane"
        spec["x_axis"], spec["y_axis"] = _cplane_axes()
    elif option_index == edges_option:
        first = _choose_edge(
            obj,
            object_id,
            spec["vertex_type"],
            spec["vertex_index"],
            "first X-axis",
        )
        if first is None:
            return None
        second = _choose_edge(
            obj,
            object_id,
            spec["vertex_type"],
            spec["vertex_index"],
            "second Y-axis",
            excluded=first,
        )
        if second is None:
            return None
        spec["orientation"] = "edges"
        spec["edge_1"] = first
        spec["edge_2"] = second
    else:
        return None

    plane = GlueConduit.reference_plane(obj, spec)
    if plane is None:
        print("Could not create the {} reference plane.".format(label))
        return None
    return spec, plane


def choose_reference_plane(object_id, label):
    doc = Rhino.RhinoDoc.ActiveDoc
    obj = doc.Objects.Find(object_id)
    if obj is None:
        return None

    options = Rhino.Input.Custom.GetOption()
    options.SetCommandPrompt("Define the {} reference plane".format(label))
    centroid_option = options.AddOption("Centroid")
    vertex_option = options.AddOption("Vertex")

    result = options.Get()
    if result != Rhino.Input.GetResult.Option:
        return None

    option_index = options.OptionIndex()
    if option_index == centroid_option:
        spec = _world_spec("centroid")
    elif option_index == vertex_option:
        selected = _choose_vertex(object_id, label)
        if selected is None:
            return None
        spec = _world_spec("vertex", selected[0], selected[1])
    else:
        return None

    return _choose_orientation(obj, object_id, spec, label)
