import Rhino
import System.Drawing


class ObjectHighlightConduit(Rhino.Display.DisplayConduit):
    def __init__(self, object_id):
        super(ObjectHighlightConduit, self).__init__()
        self.object_id = object_id

    def DrawForeground(self, event):
        doc = Rhino.RhinoDoc.ActiveDoc
        obj = doc.Objects.Find(self.object_id) if doc is not None else None
        if obj is None:
            return
        geometry = obj.Geometry
        if isinstance(geometry, Rhino.Geometry.Mesh):
            event.Display.DrawMeshWires(
                geometry,
                System.Drawing.Color.LightPink,
                3,
            )
            return
        if not isinstance(geometry, Rhino.Geometry.Brep):
            try:
                geometry = geometry.ToBrep(True)
            except Exception:
                return
        if geometry is not None:
            event.Display.DrawBrepWires(
                geometry,
                System.Drawing.Color.LightPink,
                3,
            )


class PlanePreviewConduit(Rhino.Display.DisplayConduit):
    def __init__(self, obj):
        super(PlanePreviewConduit, self).__init__()
        self.plane = None
        self.points = []
        bbox = obj.Geometry.GetBoundingBox(True)
        self.axis_length = max(bbox.Diagonal.Length * 0.2, 1.0)

    def update(self, plane, points=()):
        self.plane = plane
        self.points = list(points)

    def DrawForeground(self, event):
        if self.plane is None:
            return
        origin = self.plane.Origin
        for axis, color in (
            (self.plane.XAxis, System.Drawing.Color.Red),
            (self.plane.YAxis, System.Drawing.Color.LimeGreen),
            (self.plane.ZAxis, System.Drawing.Color.DodgerBlue),
        ):
            event.Display.DrawLine(
                origin,
                origin + axis * self.axis_length,
                color,
                3,
            )
        for point in self.points:
            event.Display.DrawPoint(
                point,
                Rhino.Display.PointStyle.X,
                14,
                System.Drawing.Color.Orange,
            )


class GlueConduit(Rhino.Display.DisplayConduit):
    def __init__(self, state):
        super(GlueConduit, self).__init__()
        self.state = state

    @staticmethod
    def centroid(obj):
        geometry = obj.Geometry
        for calculator in (
            Rhino.Geometry.VolumeMassProperties.Compute,
            Rhino.Geometry.AreaMassProperties.Compute,
        ):
            try:
                properties = calculator(geometry)
                if properties is not None:
                    return properties.Centroid
            except Exception:
                pass
        return geometry.GetBoundingBox(True).Center

    @staticmethod
    def vertex_point(obj, vertex_type, index):
        geometry = obj.Geometry
        if vertex_type == "BrepVertex":
            if not hasattr(geometry, "Vertices"):
                geometry = geometry.ToBrep(True)
            return geometry.Vertices[int(index)].Location
        if vertex_type == "MeshVertex":
            return Rhino.Geometry.Point3d(geometry.Vertices[int(index)])
        return None

    @classmethod
    def reference_point(cls, obj, spec):
        if spec["reference"] == "centroid":
            return cls.centroid(obj)
        return cls.vertex_point(obj, spec["vertex_type"], spec["vertex_index"])

    @classmethod
    def edge_vector(cls, obj, spec, edge_index):
        geometry = obj.Geometry
        origin = cls.reference_point(obj, spec)
        if origin is None:
            return None
        if spec["vertex_type"] == "BrepVertex":
            if not hasattr(geometry, "Edges"):
                geometry = geometry.ToBrep(True)
            edge = geometry.Edges[int(edge_index)]
            origin_index = int(spec["vertex_index"])
            start = edge.StartVertex
            end = edge.EndVertex
            if start.VertexIndex == origin_index:
                return end.Location - origin
            if end.VertexIndex == origin_index:
                return start.Location - origin
            return None
        if spec["vertex_type"] == "MeshVertex":
            pair = geometry.TopologyEdges.GetTopologyVertices(int(edge_index))
            topology_index = geometry.TopologyVertices.TopologyVertexIndex(
                int(spec["vertex_index"])
            )
            other = pair.J if pair.I == topology_index else pair.I
            return geometry.TopologyVertices[other] - origin
        return None

    @staticmethod
    def plane_at_point(spec, point):
        return Rhino.Geometry.Plane(
            point,
            Rhino.Geometry.Vector3d(*spec["x_axis"]),
            Rhino.Geometry.Vector3d(*spec["y_axis"]),
        )

    @classmethod
    def reference_plane(cls, obj, spec):
        point = cls.reference_point(obj, spec)
        if point is None:
            return None

        if spec["orientation"] != "edges":
            return cls.plane_at_point(spec, point)

        x_axis = cls.edge_vector(obj, spec, spec["edge_1"])
        y_axis = cls.edge_vector(obj, spec, spec["edge_2"])
        if x_axis is None or y_axis is None:
            return None
        if not x_axis.Unitize():
            return None
        y_axis = y_axis - x_axis * (x_axis * y_axis)
        if not y_axis.Unitize():
            return None
        return Rhino.Geometry.Plane(point, x_axis, y_axis)

    @staticmethod
    def plane_data(plane):
        return {
            "origin": [plane.Origin.X, plane.Origin.Y, plane.Origin.Z],
            "x_axis": [plane.XAxis.X, plane.XAxis.Y, plane.XAxis.Z],
            "y_axis": [plane.YAxis.X, plane.YAxis.Y, plane.YAxis.Z],
        }

    @staticmethod
    def plane_from_data(data):
        return Rhino.Geometry.Plane(
            Rhino.Geometry.Point3d(*data["origin"]),
            Rhino.Geometry.Vector3d(*data["x_axis"]),
            Rhino.Geometry.Vector3d(*data["y_axis"]),
        )

    @staticmethod
    def transform_data(xform):
        return [
            xform.M00, xform.M01, xform.M02, xform.M03,
            xform.M10, xform.M11, xform.M12, xform.M13,
            xform.M20, xform.M21, xform.M22, xform.M23,
            xform.M30, xform.M31, xform.M32, xform.M33,
        ]

    @staticmethod
    def transform_from_data(values):
        xform = Rhino.Geometry.Transform.Identity
        for row in range(4):
            for column in range(4):
                setattr(xform, "M{}{}".format(row, column), values[row * 4 + column])
        return xform

    def DrawForeground(self, event):
        doc = Rhino.RhinoDoc.ActiveDoc
        if doc is None:
            return

        for relationship in list(self.state["relationships"].values()):
            if relationship["document_serial"] != doc.RuntimeSerialNumber:
                continue

            child = doc.Objects.Find(relationship["follower_id"])
            parent = doc.Objects.Find(relationship["driver_id"])
            if child is None or parent is None:
                continue

            child_point = self.reference_point(child, relationship["child_spec"])
            parent_point = self.reference_point(parent, relationship["parent_spec"])
            if child_point is None or parent_point is None:
                continue
            event.Display.DrawPoint(
                child_point,
                Rhino.Display.PointStyle.X,
                10,
                System.Drawing.Color.DodgerBlue,
            )
            event.Display.DrawPoint(
                parent_point,
                Rhino.Display.PointStyle.X,
                10,
                System.Drawing.Color.OrangeRed,
            )
            event.Display.DrawDottedLine(
                child_point,
                parent_point,
                System.Drawing.Color.Gold,
            )
