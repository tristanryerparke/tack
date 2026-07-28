import Rhino
import System.Drawing
import scriptcontext as sc
from Rhino.Commands import Result

L = 10.0
W = 10.0
H = 10.0

RESULT_KEY = "PickBoxVertex.Result"


class BoxConduit(Rhino.Display.DisplayConduit):
    def __init__(self, box, vertices):
        super(BoxConduit, self).__init__()
        self.box = box
        self.vertices = vertices

    def CalculateBoundingBox(self, event):
        bounding_box = self.box.GetBoundingBox(True)
        if bounding_box.IsValid:
            diagonal = bounding_box.Diagonal
            bounding_box.Inflate(
                max(diagonal.X * 0.5, 1.0),
                max(diagonal.Y * 0.5, 1.0),
                max(diagonal.Z * 0.5, 1.0),
            )
            event.IncludeBoundingBox(bounding_box)

    def CalculateBoundingBoxZoomExtents(self, event):
        self.CalculateBoundingBox(event)

    def DrawForeground(self, event):
        event.Display.DrawBrepWires(self.box, System.Drawing.Color.Cyan, 2)
        for point in self.vertices:
            event.Display.DrawPoint(
                point,
                Rhino.Display.PointStyle.X,
                10,
                System.Drawing.Color.Cyan,
            )


def RunCommand(is_interactive):
    box = Rhino.Geometry.Box(
        Rhino.Geometry.Plane.WorldXY,
        Rhino.Geometry.Interval(0, L),
        Rhino.Geometry.Interval(0, W),
        Rhino.Geometry.Interval(0, H),
    )
    vertices = list(box.GetCorners())
    conduit = BoxConduit(box.ToBrep(), vertices)
    conduit.Enabled = True
    Rhino.RhinoDoc.ActiveDoc.Views.Redraw()

    getter = Rhino.Input.Custom.GetPoint()
    getter.SetCommandPrompt("Pick a vertex of the box")
    getter.AcceptNothing(False)
    getter.AddConstructionPoints(vertices)
    getter.AddSnapPoints(vertices)
    getter.FullFrameRedrawDuringGet = True
    try:
        if getter.Get() != Rhino.Input.GetResult.Point:
            return Result.Cancel

        clicked = getter.Point()
        index = min(
            range(len(vertices)),
            key=lambda i: clicked.DistanceTo(vertices[i]),
        )
        result = {"index": index, "point": vertices[index]}
        sc.sticky[RESULT_KEY] = result
        print("Picked box vertex index: {}".format(index))
        return Result.Success
    finally:
        conduit.Enabled = False
        Rhino.RhinoDoc.ActiveDoc.Views.Redraw()


if __name__ == "__main__":
    RunCommand(True)
