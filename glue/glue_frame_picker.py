import Rhino
import System
import System.Drawing
import rhinoscriptsyntax as rs


class FrameSelectionConduit(Rhino.Display.DisplayConduit):
    def __init__(self):
        super(FrameSelectionConduit, self).__init__()
        self.vertex = None
        self.vertex_color = System.Drawing.Color.Orange
        self.vertex_size = 14
        self.incident_edges = []
        self.edges = {}

    def set_vertex(self, point):
        self.vertex = Rhino.Geometry.Point3d(point)
        self.vertex_color = System.Drawing.Color.Orange
        self.vertex_size = 14

    def set_highlighted_vertex(self, point):
        self.vertex = Rhino.Geometry.Point3d(point)
        self.vertex_color = System.Drawing.Color.Cyan
        self.vertex_size = 18

    def set_incident_edges(self, edges):
        self.incident_edges = [
            (Rhino.Geometry.Point3d(endpoints[0]), Rhino.Geometry.Point3d(endpoints[1]))
            for endpoints in edges
        ]

    def set_edge(self, number, endpoints):
        endpoints = (
            Rhino.Geometry.Point3d(endpoints[0]),
            Rhino.Geometry.Point3d(endpoints[1]),
        )
        if number == 1:
            self.incident_edges = [
                candidate
                for candidate in self.incident_edges
                if not _same_segment(candidate, endpoints)
            ]
        self.edges[number] = endpoints

    def DrawForeground(self, event):
        if self.vertex is not None:
            event.Display.DrawPoint(
                self.vertex,
                Rhino.Display.PointStyle.X,
                self.vertex_size,
                self.vertex_color,
            )

        for endpoints in self.incident_edges:
            event.Display.DrawLine(
                endpoints[0],
                endpoints[1],
                System.Drawing.Color.FromArgb(110, 0, 220, 255),
                6,
            )

        for number, color in (
            (1, System.Drawing.Color.Red),
            (2, System.Drawing.Color.LimeGreen),
        ):
            endpoints = self.edges.get(number)
            if endpoints is not None:
                event.Display.DrawLine(endpoints[0], endpoints[1], color, 4)


def _same_segment(left, right, tolerance=1e-7):
    return (
        left[0].DistanceTo(right[0]) <= tolerance
        and left[1].DistanceTo(right[1]) <= tolerance
    ) or (
        left[0].DistanceTo(right[1]) <= tolerance
        and left[1].DistanceTo(right[0]) <= tolerance
    )


def _same_id(left, right):
    return str(left).lower() == str(right).lower()


def _point(value):
    return Rhino.Geometry.Point3d(value)


def _geometry(obj):
    geometry = obj.Geometry
    if hasattr(geometry, "Vertices"):
        return geometry
    return geometry.ToBrep(True)


def vertex_point(obj, vertex_type, vertex_index):
    geometry = _geometry(obj)
    if vertex_type == "BrepVertex":
        return _point(geometry.Vertices[int(vertex_index)].Location)
    if vertex_type == "MeshVertex":
        return _point(geometry.Vertices[int(vertex_index)])
    return None


def coincident_vertices(first_obj, second_obj, tolerance):
    first_geometry = _geometry(first_obj)
    second_geometry = _geometry(second_obj)
    first_type = (
        "MeshVertex"
        if isinstance(first_geometry, Rhino.Geometry.Mesh)
        else "BrepVertex"
    )
    second_type = (
        "MeshVertex"
        if isinstance(second_geometry, Rhino.Geometry.Mesh)
        else "BrepVertex"
    )
    matches = []
    for first_index in range(first_geometry.Vertices.Count):
        first_point = vertex_point(first_obj, first_type, first_index)
        for second_index in range(second_geometry.Vertices.Count):
            second_point = vertex_point(second_obj, second_type, second_index)
            if first_point.DistanceTo(second_point) <= tolerance:
                matches.append(
                    (
                        first_type,
                        first_index,
                        second_type,
                        second_index,
                        first_point,
                        second_point,
                    )
                )
    return matches


def edge_endpoints(obj, edge_type, edge_index):
    geometry = _geometry(obj)
    index = int(edge_index)

    if edge_type == "BrepTrim":
        curve = geometry.Trims[index]
        return _point(curve.PointAtStart), _point(curve.PointAtEnd)

    if edge_type == "BrepEdge":
        edge = geometry.Edges[index]
        return _point(edge.StartVertex.Location), _point(edge.EndVertex.Location)

    if edge_type in ("MeshEdge", "MeshTopologyEdge"):
        pair = geometry.TopologyEdges.GetTopologyVertices(index)
        return (
            _point(geometry.TopologyVertices[pair.I]),
            _point(geometry.TopologyVertices[pair.J]),
        )

    if hasattr(geometry, "Edges") and 0 <= index < geometry.Edges.Count:
        edge = geometry.Edges[index]
        return _point(edge.StartVertex.Location), _point(edge.EndVertex.Location)
    if hasattr(geometry, "TopologyEdges") and 0 <= index < geometry.TopologyEdges.Count:
        pair = geometry.TopologyEdges.GetTopologyVertices(index)
        return (
            _point(geometry.TopologyVertices[pair.I]),
            _point(geometry.TopologyVertices[pair.J]),
        )
    return None


def _select_vertex(obj, label):
    getter = Rhino.Input.Custom.GetPoint()
    getter.SetCommandPrompt(
        "Click the {} vertex (nearest vertex will be used)".format(label)
    )
    getter.AcceptNothing(False)
    if getter.Get() != Rhino.Input.GetResult.Point:
        return None

    geometry = _geometry(obj)
    if geometry is None or not hasattr(geometry, "Vertices"):
        print("The {} object has no selectable vertices.".format(label))
        return None
    if geometry.Vertices.Count == 0:
        print("The {} object has no vertices.".format(label))
        return None

    vertex_type = (
        "MeshVertex"
        if isinstance(geometry, Rhino.Geometry.Mesh)
        else "BrepVertex"
    )
    clicked = getter.Point()
    nearest_index = min(
        range(geometry.Vertices.Count),
        key=lambda index: clicked.DistanceTo(
            vertex_point(obj, vertex_type, index)
        ),
    )
    nearest_point = vertex_point(obj, vertex_type, nearest_index)
    distance = clicked.DistanceTo(nearest_point)
    print(
        "{} vertex: type={}, index={}, snap_distance={:.6g}".format(
            label,
            vertex_type,
            nearest_index,
            distance,
        )
    )
    return vertex_type, int(nearest_index)


def _incident_edge_endpoints(obj, vertex_type, vertex_index):
    geometry = _geometry(obj)
    if vertex_type == "BrepVertex":
        return [
            edge_endpoints(obj, "BrepEdge", index)
            for index in range(geometry.Edges.Count)
            if geometry.Edges[index].StartVertex.VertexIndex == vertex_index
            or geometry.Edges[index].EndVertex.VertexIndex == vertex_index
        ]

    vertex = vertex_point(obj, vertex_type, vertex_index)
    if vertex is None or not hasattr(geometry, "TopologyEdges"):
        return []
    return [
        edge_endpoints(obj, "MeshTopologyEdge", index)
        for index in range(geometry.TopologyEdges.Count)
        if any(
            vertex.DistanceTo(point) <= 1e-7
            for point in edge_endpoints(obj, "MeshTopologyEdge", index)
        )
    ]


def _edge_component(obj, component):
    component_name = System.Enum.GetName(
        Rhino.Geometry.ComponentIndexType,
        component.ComponentIndexType,
    )
    index = int(component.Index)
    if component_name == "BrepTrim":
        trim = _geometry(obj).Trims[index]
        edge = trim.Edge
        if edge is not None:
            return "BrepEdge", int(edge.EdgeIndex)
    return component_name, index


def _select_edge(obj, object_id, prompt, excluded=None):
    while True:
        getter = Rhino.Input.Custom.GetObject()
        getter.SetCommandPrompt(prompt)
        getter.SubObjectSelect = True
        getter.GeometryFilter = Rhino.DocObjects.ObjectType.EdgeFilter
        getter.EnablePreSelect(False, True)

        if getter.Get() != Rhino.Input.GetResult.Object:
            return None

        reference = getter.Object(0)
        component = reference.GeometryComponentIndex
        actual_type = System.Enum.GetName(
            Rhino.Geometry.ComponentIndexType,
            component.ComponentIndexType,
        )
        print(
            "edge candidate: object={}, type={}, index={}".format(
                reference.ObjectId,
                actual_type,
                component.Index,
            )
        )
        if not _same_id(reference.ObjectId, object_id):
            print("Select an edge on the target object.")
            continue

        edge_type, edge_index = _edge_component(obj, component)
        if (edge_type, edge_index) == excluded:
            print("Select a different edge.")
            continue
        if edge_endpoints(obj, edge_type, edge_index) is None:
            print("Could not resolve the selected edge geometry.")
            continue
        return edge_type, edge_index


def _lock_objects_except(doc, allowed_ids):
    allowed_ids = {str(object_id).lower() for object_id in allowed_ids}
    changed = []
    for obj in doc.Objects:
        if obj is None or str(obj.Id).lower() in allowed_ids:
            continue
        if not rs.IsObjectLocked(obj.Id):
            if rs.LockObject(obj.Id):
                changed.append(obj.Id)
    return changed


def _lock_other_objects(doc, target_id):
    return _lock_objects_except(doc, [target_id])


def _unlock_changed(ids):
    for object_id in ids:
        rs.UnlockObject(object_id)


def frame_from_spec(obj, spec):
    origin = vertex_point(
        obj,
        spec["vertex_type"],
        spec["vertex_index"],
    )
    endpoints_1 = edge_endpoints(
        obj,
        spec["edge_1_type"],
        spec["edge_1"],
    )
    endpoints_2 = edge_endpoints(
        obj,
        spec["edge_2_type"],
        spec["edge_2"],
    )
    if origin is None or endpoints_1 is None or endpoints_2 is None:
        return None

    x_axis = endpoints_1[1] - endpoints_1[0]
    y_axis = endpoints_2[1] - endpoints_2[0]
    if not x_axis.Unitize():
        return None
    y_axis = y_axis - x_axis * (x_axis * y_axis)
    if not y_axis.Unitize():
        return None
    return Rhino.Geometry.Plane(origin, x_axis, y_axis)


def pick_parent_frame(object_id):
    return pick_frame(object_id, "parent")


def pick_frame(object_id, label):
    doc = Rhino.RhinoDoc.ActiveDoc
    obj = doc.Objects.Find(object_id)
    if obj is None:
        return None

    conduit = FrameSelectionConduit()
    conduit.Enabled = True
    locked_by_picker = _lock_other_objects(doc, object_id)
    try:
        selected = _select_vertex(obj, label)
        if selected is None:
            return None
        vertex_type, vertex_index = selected
        conduit.set_vertex(vertex_point(obj, vertex_type, vertex_index))
        conduit.set_incident_edges(
            _incident_edge_endpoints(obj, vertex_type, vertex_index)
        )
        doc.Views.Redraw()

        first = _select_edge(
            obj,
            object_id,
            "Select the first edge (red / X axis) on the {}".format(label),
        )
        if first is None:
            return None
        conduit.set_edge(1, edge_endpoints(obj, first[0], first[1]))
        doc.Views.Redraw()

        second = _select_edge(
            obj,
            object_id,
            "Select the second edge (green / Y axis) on the {}".format(label),
            excluded=first,
        )
        if second is None:
            return None
        conduit.set_edge(2, edge_endpoints(obj, second[0], second[1]))
        doc.Views.Redraw()

        spec = {
            "vertex_type": vertex_type,
            "vertex_index": vertex_index,
            "edge_1_type": first[0],
            "edge_1": first[1],
            "edge_2_type": second[0],
            "edge_2": second[1],
        }
        plane = frame_from_spec(obj, spec)
        if plane is None:
            print("The selected edges cannot define a plane.")
            return None
        return spec, plane
    finally:
        _unlock_changed(locked_by_picker)
        conduit.Enabled = False
        doc.Views.Redraw()
