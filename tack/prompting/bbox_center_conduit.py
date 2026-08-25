import Rhino
import System.Drawing


class BoundingBoxCenterConduit(Rhino.Display.DisplayConduit):
    def __init__(self, point):
        super(BoundingBoxCenterConduit, self).__init__()
        self.point = point

    def DrawForeground(self, event):
        event.Display.DrawPoint(
            self.point,
            Rhino.Display.PointStyle.Circle,
            3,
            System.Drawing.Color.Black,
        )
        event.Display.DrawPoint(
            self.point,
            Rhino.Display.PointStyle.Circle,
            2,
            System.Drawing.Color.White,
        )
