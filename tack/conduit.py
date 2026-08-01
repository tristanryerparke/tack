import Rhino
import System.Drawing
import scriptcontext as sc

from tack import link
from tack import utils


DISPLAY_TYPE_TOLERANCE = 0.1


class TackLinkConduit(Rhino.Display.DisplayConduit):
    def DrawForeground(self, event):
        doc = Rhino.RhinoDoc.ActiveDoc
        state = sc.sticky.get(utils.RUNTIME_KEY)
        if doc is None or state is None:
            return
        result = link.inspect_link(doc, state)
        if result is None:
            return

        parent_anchor = result["parent_anchor"]
        child_anchor = result["child_anchor"]
        setup_offset = Rhino.Geometry.Vector3d(*result["link"]["offset"])
        if setup_offset.Length <= DISPLAY_TYPE_TOLERANCE:
            event.Display.DrawPoint(
                parent_anchor,
                Rhino.Display.PointStyle.RoundControlPoint,
                6,
                System.Drawing.Color.Orange,
            )
            return

        event.Display.DrawLine(
            parent_anchor,
            child_anchor,
            System.Drawing.Color.Orange,
            3,
        )
        event.Display.DrawArrowHead(
            child_anchor,
            child_anchor - parent_anchor,
            System.Drawing.Color.Orange,
            32.0,
            0.0,
        )
