import Rhino
import System.Drawing


class VertexPickConduit(Rhino.Display.DisplayConduit):
    def __init__(self, points, state):
        super(VertexPickConduit, self).__init__()
        self.points = points
        self.state = state

    def DrawForeground(self, event):
        hover_index = self.state["hover"]
        for index, point in enumerate(self.points):
            color = (
                System.Drawing.Color.Yellow
                if index == hover_index
                else System.Drawing.Color.Cyan
            )
            event.Display.DrawPoint(
                point,
                Rhino.Display.PointStyle.X,
                8 if index == hover_index else 4,
                color,
            )
