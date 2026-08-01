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
        event.Display.DrawPoint(
            parent_point,
            Rhino.Display.PointStyle.RoundSimple,
            5,
            System.Drawing.Color.OrangeRed,
        )
        event.Display.DrawPoint(
            child_point,
            Rhino.Display.PointStyle.RoundSimple,
            5,
            System.Drawing.Color.DodgerBlue,
        )
        if parent_point.DistanceTo(child_point) > 1e-7:
            event.Display.DrawDottedLine(
                parent_point,
                child_point,
                System.Drawing.Color.Gold,
            )
