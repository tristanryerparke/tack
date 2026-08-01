import Rhino
import System.Drawing
import scriptcontext as sc

from tack import link
from tack import utils


class CoincidentLinkConduit(Rhino.Display.DisplayConduit):
    def DrawForeground(self, event):
        doc = Rhino.RhinoDoc.ActiveDoc
        state = sc.sticky.get(utils.RUNTIME_KEY)
        if doc is None or state is None:
            return
        result = link.inspect_link(doc, state)
        if result is None:
            return

        parent_point = result["parent_point"]
        child_point = result["child_point"]
        if parent_point.DistanceTo(child_point) <= 1e-7:
            event.Display.DrawPoint(
                parent_point,
                Rhino.Display.PointStyle.RoundControlPoint,
                6,
                System.Drawing.Color.Orange,
            )
            return

        event.Display.DrawLine(
            parent_point,
            child_point,
            System.Drawing.Color.Orange,
            3,
        )
        event.Display.DrawArrowHead(
            child_point,
            child_point - parent_point,
            System.Drawing.Color.Orange,
            32.0,
            0.0,
        )
