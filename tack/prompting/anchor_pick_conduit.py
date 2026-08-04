import Rhino
import System.Drawing


class AnchorPickConduit(Rhino.Display.DisplayConduit):
    def __init__(self, points, state, wire_segments=None):
        super(AnchorPickConduit, self).__init__()
        self.points = points
        self.state = state
        self.wire_segments = list(wire_segments or ())

    def DrawForeground(self, event):
        for start, end in self.wire_segments:
            event.Display.DrawLine(
                start,
                end,
                System.Drawing.Color.Cyan,
                2,
            )

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
                6 if index == hover_index else 4,
                color,
            )
