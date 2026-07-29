import Rhino
import System.Drawing
import scriptcontext as sc
from Rhino.Commands import Result

L = 10.0
W = 10.0
H = 10.0

RESULT_KEY = "PickBoxEdge.Result"


class BoxEdgeConduit(Rhino.Display.DisplayConduit):
    def __init__(self, brep, edges, state):
        super(BoxEdgeConduit, self).__init__()
        self.brep = brep
        self.edges = edges
        self.state = state

    def CalculateBoundingBox(self, event):
        bounding_box = self.brep.GetBoundingBox(True)
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
        event.Display.DrawBrepWires(self.brep, System.Drawing.Color.Cyan, 2)
        index = self.state["hover"]
        if index < 0:
            return

        edge = self.edges[index]
        event.Display.DrawLine(
            edge.From,
            edge.To,
            System.Drawing.Color.Yellow,
            6,
        )


class BoxEdgeGetPoint(Rhino.Input.Custom.GetPoint):
    def __init__(self, edges, state):
        super(BoxEdgeGetPoint, self).__init__()
        self.edges = edges
        self.state = state

    def _hit_test(self, event):
        picker = Rhino.Input.Custom.PickContext()
        picker.View = event.Viewport.ParentView
        picker.PickStyle = Rhino.Input.Custom.PickStyle.PointPick
        picker.SetPickTransform(
            event.Viewport.GetPickTransform(event.WindowPoint)
        )

        best = None
        try:
            for index, edge in enumerate(self.edges):
                hit, parameter, depth, distance = picker.PickFrustumTest(edge)
                if not hit:
                    continue

                candidate = (distance, -depth, index, parameter)
                if best is None or candidate < best:
                    best = candidate
        finally:
            picker.Dispose()

        return None if best is None else best[2]

    def OnMouseMove(self, event):
        self.state["hover"] = self._hit_test(event)
        if self.state["hover"] is None:
            self.state["hover"] = -1
        Rhino.RhinoDoc.ActiveDoc.Views.Redraw()
        super(BoxEdgeGetPoint, self).OnMouseMove(event)

    def OnMouseDown(self, event):
        if event.RightButtonDown:
            super(BoxEdgeGetPoint, self).OnMouseDown(event)
            return
        if not event.LeftButtonDown:
            return

        index = self._hit_test(event)
        if index is None:
            return

        self.state["result"] = {"index": index, "edge": self.edges[index]}
        sc.sticky[RESULT_KEY] = self.state["result"]
        super(BoxEdgeGetPoint, self).OnMouseDown(event)


def pick_edge():
    box = Rhino.Geometry.Box(
        Rhino.Geometry.Plane.WorldXY,
        Rhino.Geometry.Interval(0, L),
        Rhino.Geometry.Interval(0, W),
        Rhino.Geometry.Interval(0, H),
    )
    brep = box.ToBrep()
    edges = [
        Rhino.Geometry.Line(edge.StartVertex.Location, edge.EndVertex.Location)
        for edge in brep.Edges
    ]
    state = {"hover": -1, "result": None}
    conduit = BoxEdgeConduit(brep, edges, state)
    conduit.Enabled = True
    Rhino.RhinoDoc.ActiveDoc.Views.Redraw()

    getter = BoxEdgeGetPoint(edges, state)
    getter.SetCommandPrompt("Pick an edge of the box")
    getter.AcceptNothing(False)
    getter.FullFrameRedrawDuringGet = True
    try:
        if getter.Get() != Rhino.Input.GetResult.Point:
            return None

        result = state["result"]
        if result is None and state["hover"] >= 0:
            result = {"index": state["hover"], "edge": edges[state["hover"]]}
            sc.sticky[RESULT_KEY] = result
        return None if result is None else result["index"]
    finally:
        conduit.Enabled = False
        Rhino.RhinoDoc.ActiveDoc.Views.Redraw()


def RunCommand(is_interactive):
    index = pick_edge()
    if index is None:
        return Result.Cancel
    print("Picked box edge index: {}".format(index))
    return Result.Success


if __name__ == "__main__":
    RunCommand(True)
