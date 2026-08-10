"""Prototype: resize a simple cylindrical through-hole without construction history.

Select one or more circular hole edges, then enter their new diameter.
Only simple, unsplit cylindrical through-holes are supported.
"""

import Rhino
import System.Drawing
from Rhino.Commands import Result


class HoleEdgeConduit(Rhino.Display.DisplayConduit):
    def __init__(self, edges):
        super(HoleEdgeConduit, self).__init__()
        self.edges = edges

    def DrawForeground(self, event):
        for edge in self.edges:
            event.Display.DrawCurve(edge, System.Drawing.Color.Yellow, 3)


class DiameterGetPoint(Rhino.Input.Custom.GetPoint):
    def __init__(self, circles):
        super(DiameterGetPoint, self).__init__()
        self.circles = circles
        self.plane = circles[0].Plane
        self.center = circles[0].Center
        self.DynamicDraw += self._draw

    def radius_at(self, point):
        return self.center.DistanceTo(self.plane.ClosestPoint(point))

    def _draw(self, sender, event):
        radius = self.radius_at(event.CurrentPoint)
        for circle in self.circles:
            event.Display.DrawCircle(
                Rhino.Geometry.Circle(circle.Plane, radius),
                System.Drawing.Color.Yellow,
                3,
            )


def _cylinder(face, tolerance):
    success, cylinder = face.TryGetCylinder(tolerance)
    if not success:
        return None

    base_circle = cylinder.CircleAt(0.0)
    origin = base_circle.Plane.Origin
    axis = base_circle.Plane.ZAxis
    heights = []
    for edge_index in face.AdjacentEdges():
        edge = face.Brep.Edges[edge_index]
        heights.extend(
            Rhino.Geometry.Vector3d.Multiply(axis, point - origin)
            for point in (edge.StartVertex.Location, edge.EndVertex.Location)
        )
    if not heights or max(heights) - min(heights) <= tolerance:
        print("Cylinder face has no usable axial span.")
        return None

    cylinder.Height1 = min(heights)
    cylinder.Height2 = max(heights)
    return cylinder


def _cylinder_face_for_edge(edge, tolerance):
    for face_index in edge.AdjacentFaces():
        face = edge.Brep.Faces[face_index]
        if _cylinder(face, tolerance) is not None:
            return face
    return None


def _remove_holes(brep, cylinder_face_indices, tolerance):
    loops = []
    for cylinder_face_index in cylinder_face_indices:
        adjacent = list(brep.Faces[cylinder_face_index].AdjacentFaces())
        if len(adjacent) != 2 or not all(
            brep.Faces[index].IsPlanar(tolerance) for index in adjacent
        ):
            print("Untrim requires each cylinder between two planar faces.")
            return None
        for face_index in adjacent:
            matching_loops = [
                loop for loop in brep.Faces[face_index].Loops
                if loop.LoopType == Rhino.Geometry.BrepLoopType.Inner
                and any(
                    trim.Edge is not None
                    and cylinder_face_index in trim.Edge.AdjacentFaces()
                    for trim in loop.Trims
                )
            ]
            if len(matching_loops) != 1:
                print("Could not identify the hole loop on face={}.".format(face_index))
                return None
            loops.append(matching_loops[0].ComponentIndex())

    result = brep.RemoveHoles(loops, tolerance)
    if result is None:
        print("RemoveHoles failed.")
    else:
        print(
            "Untrim: valid={} solid={} faces={}".format(
                result.IsValid, result.IsSolid, result.Faces.Count
            )
        )
    return result


def _tool(cylinder, radius, extension=0.0):
    cylinder.Radius = radius
    cylinder.Height1 -= extension
    cylinder.Height2 += extension
    tool = cylinder.ToBrep(True, True)
    print(
        "Tool: radius={} heights=[{}, {}] valid={}".format(
            radius,
            cylinder.Height1,
            cylinder.Height2,
            tool is not None and tool.IsValid,
        )
    )
    return tool


def _one(label, breps):
    count = 0 if breps is None else len(breps)
    if count != 1:
        print("{} returned {} Breps; expected one.".format(label, count))
        return None
    brep = breps[0]
    print(
        "{}: valid={} solid={} faces={}".format(
            label, brep.IsValid, brep.IsSolid, brep.Faces.Count
        )
    )
    return brep


def resize_holes(brep, faces, new_radius, tolerance):
    """Return *brep* with all selected cylindrical through-holes resized."""
    cylinders = []
    for face in faces:
        cylinder = _cylinder(face, tolerance)
        if cylinder is None:
            return None
        cylinders.append(cylinder)
        print(
            "Selected cylinder: face={} radius={} heights=[{}, {}] target radius={}".format(
                face.FaceIndex,
                cylinder.Radius,
                cylinder.Height1,
                cylinder.Height2,
                new_radius,
            )
        )
    if not cylinders or new_radius <= tolerance:
        return None

    untrimmed = _remove_holes(
        brep, {face.FaceIndex for face in faces}, tolerance
    )
    result = untrimmed
    for cylinder in cylinders:
        cutter = _tool(cylinder, new_radius, tolerance)
        result = None if result is None else _one(
            "Difference", Rhino.Geometry.Brep.CreateBooleanDifference(
                result, cutter, tolerance
            )
        )
    if result is not None:
        print("Merged coplanar faces={}".format(
            result.MergeCoplanarFaces(tolerance)
        ))
    return result


def _cylindrical_faces(brep, tolerance):
    return [
        face for face in brep.Faces if _cylinder(face, tolerance) is not None
    ]


def run_self_test():
    """Exercise growing then shrinking two through-holes in a 10-unit box."""
    tolerance = 0.01
    brep = Rhino.Geometry.Box(
        Rhino.Geometry.Plane.WorldXY,
        Rhino.Geometry.Interval(0, 10),
        Rhino.Geometry.Interval(0, 10),
        Rhino.Geometry.Interval(0, 10),
    ).ToBrep()
    for x in (3, 7):
        cutter = Rhino.Geometry.Cylinder(
            Rhino.Geometry.Circle(
                Rhino.Geometry.Plane(
                    Rhino.Geometry.Point3d(x, 5, -1),
                    Rhino.Geometry.Vector3d.ZAxis,
                ),
                2,
            ),
            12,
        ).ToBrep(True, True)
        brep = _one("Initial difference", Rhino.Geometry.Brep.CreateBooleanDifference(
            brep, cutter, tolerance
        ))
    assert brep is not None

    for radius in (3, 1):
        faces = _cylindrical_faces(brep, tolerance)
        brep = resize_holes(brep, faces, radius, tolerance)
        assert brep is not None and brep.IsSolid
        resized_faces = _cylindrical_faces(brep, tolerance)
        assert len(resized_faces) == 2
        assert all(
            abs(_cylinder(face, tolerance).Radius - radius) <= tolerance
            for face in resized_faces
        )

    print("Adjustable-hole self-test passed.")


def RunCommand(is_interactive):
    doc = Rhino.RhinoDoc.ActiveDoc
    picker = Rhino.Input.Custom.GetObject()
    picker.SetCommandPrompt("Select circular hole edges; press Enter when done")
    picker.GeometryFilter = Rhino.DocObjects.ObjectType.Curve
    picker.SubObjectSelect = True
    if picker.GetMultiple(1, 0) != Rhino.Input.GetResult.Object:
        return Result.Cancel

    objrefs = [picker.Object(index) for index in range(picker.ObjectCount)]
    object_id = objrefs[0].Object().Id
    faces = []
    edges = []
    edge_indices = []
    for objref in objrefs:
        if objref.Object().Id != object_id:
            print("Select hole edges from one Brep only.")
            return Result.Failure
        edge = objref.Edge()
        face = _cylinder_face_for_edge(
            edge, doc.ModelAbsoluteTolerance
        ) if edge else None
        if face is None:
            print("Select circular edges bordering cylindrical Brep faces.")
            return Result.Failure
        if all(face.FaceIndex != existing.FaceIndex for existing in faces):
            faces.append(face)
        edges.append(edge)
        edge_indices.append(edge.EdgeIndex)

    cylinders = [_cylinder(face, doc.ModelAbsoluteTolerance) for face in faces]
    conduit = HoleEdgeConduit(edges)
    conduit.Enabled = True
    doc.Views.Redraw()
    try:
        circles = [
            cylinder.CircleAt(cylinder.Height1) for cylinder in cylinders
        ]
        diameter = DiameterGetPoint(circles)
        diameter.SetCommandPrompt("Pick diameter; type an exact diameter")
        diameter.SetBasePoint(circles[0].Center, True)
        diameter.Constrain(circles[0].Plane, False)
        diameter.AcceptNumber(True, False)
        picked = diameter.Get()
        if picked == Rhino.Input.GetResult.Number:
            new_diameter = diameter.Number()
        elif picked == Rhino.Input.GetResult.Point:
            new_diameter = diameter.radius_at(diameter.Point()) * 2
        else:
            return Result.Cancel
        if new_diameter <= doc.ModelAbsoluteTolerance * 2:
            return Result.Cancel

        print(
            "Selected object={} edges={} faces={}. Requested diameter={}".format(
                object_id, edge_indices, [face.FaceIndex for face in faces], new_diameter
            )
        )
        result = resize_holes(
            faces[0].Brep,
            faces,
            new_diameter / 2,
            doc.ModelAbsoluteTolerance,
        )
        if result is None or not result.IsSolid:
            print("Could not resize those holes; this prototype supports simple planar through-holes.")
            return Result.Failure

        if not doc.Objects.Replace(object_id, result):
            return Result.Failure
        return Result.Success
    finally:
        conduit.Enabled = False
        doc.Views.Redraw()


if __name__ == "__main__":
    try:
        from rhino_watcher import try_send_end_sync
        from rhino_watcher import try_send_quit_sync
        from rhino_watcher import websocket_output_if_available_sync
    except ImportError:
        RunCommand(True)
    else:
        try:
            with websocket_output_if_available_sync():
                result = RunCommand(True)
        except Exception:
            with websocket_output_if_available_sync():
                import traceback
                traceback.print_exc()
            try_send_quit_sync()
        else:
            (try_send_end_sync if result == Result.Success else try_send_quit_sync)()
