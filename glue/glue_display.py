import Rhino
import System.Drawing


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
        if vertex_type == "SubDVertex":
            return geometry.Vertices[int(index)].SurfacePoint()
        return None

    @classmethod
    def reference_point(cls, obj, relationship, fallback=True):
        if relationship.get("reference") != "vertex":
            return cls.centroid(obj)

        try:
            point = cls.vertex_point(
                obj,
                relationship["vertex_type"],
                relationship["vertex_index"],
            )
            if point is not None:
                return point
        except Exception:
            pass
        return cls.centroid(obj) if fallback else None

    @classmethod
    def frame_vertex_indices(cls, obj, relationship):
        vertex_type = relationship.get("vertex_type")
        index = int(relationship.get("vertex_index", -1))
        if vertex_type == "BrepVertex":
            geometry = obj.Geometry
            if not hasattr(geometry, "Vertices"):
                geometry = geometry.ToBrep(True)
            vertex = geometry.Vertices[index]
            neighbors = []
            edge_indices = vertex.EdgeIndices
            if callable(edge_indices):
                edge_indices = edge_indices()
            for edge_index in edge_indices:
                edge = geometry.Edges[edge_index]
                start_index = edge.StartVertex.VertexIndex
                end_index = edge.EndVertex.VertexIndex
                neighbor = end_index if start_index == index else start_index
                if neighbor not in neighbors:
                    neighbors.append(neighbor)
            return tuple(neighbors[:2]) if len(neighbors) >= 2 else None
        if vertex_type == "MeshVertex":
            neighbors = []
            faces = obj.Geometry.Faces
            for face_index in range(faces.Count):
                face = faces[face_index]
                indices = [face.A, face.B, face.C]
                if face.IsQuad:
                    indices.append(face.D)
                if index not in indices:
                    continue
                for neighbor in indices:
                    if neighbor != index and neighbor not in neighbors:
                        neighbors.append(neighbor)
            return tuple(neighbors[:2]) if len(neighbors) >= 2 else None
        return None

    @classmethod
    def reference_frame(cls, obj, relationship):
        indices = (
            relationship.get("frame_index_1"),
            relationship.get("frame_index_2"),
        )
        if None in indices or -1 in indices:
            return None
        origin = cls.vertex_point(
            obj,
            relationship["vertex_type"],
            relationship["vertex_index"],
        )
        point_1 = cls.vertex_point(obj, relationship["vertex_type"], indices[0])
        point_2 = cls.vertex_point(obj, relationship["vertex_type"], indices[1])
        if origin is None or point_1 is None or point_2 is None:
            return None
        axis_1 = point_1 - origin
        axis_2 = point_2 - origin
        if axis_1.Length <= 1e-9 or axis_2.Length <= 1e-9:
            return None
        if Rhino.Geometry.Vector3d.CrossProduct(axis_1, axis_2).Length <= 1e-9:
            return None
        return Rhino.Geometry.Plane(origin, axis_1, axis_2)

    def DrawForeground(self, event):
        doc = Rhino.RhinoDoc.ActiveDoc
        if doc is None:
            return

        for relationship in list(self.state["relationships"].values()):
            if relationship["document_serial"] != doc.RuntimeSerialNumber:
                continue

            follower = doc.Objects.Find(relationship["follower_id"])
            driver = doc.Objects.Find(relationship["driver_id"])
            if follower is None or driver is None:
                continue

            child_centroid = self.centroid(follower)
            parent_reference = self.reference_point(driver, relationship)
            event.Display.DrawPoint(
                child_centroid,
                Rhino.Display.PointStyle.X,
                10,
                System.Drawing.Color.DodgerBlue,
            )
            event.Display.DrawPoint(
                parent_reference,
                Rhino.Display.PointStyle.X,
                10,
                System.Drawing.Color.OrangeRed,
            )
            event.Display.DrawDottedLine(
                child_centroid,
                parent_reference,
                System.Drawing.Color.Gold,
            )
