import Rhino
import System.Drawing
import scriptcontext as sc

from tack import utils


DISPLAY_TYPE_TOLERANCE = 0.1


class TackLinkConduit(Rhino.Display.DisplayConduit):
    def DrawForeground(self, event):
        for state in sc.sticky.get(utils.RUNTIME_KEY, {}).values():
            display = state.get("display")
            if (
                state.get("broken")
                or display is None
                or display.get("dirty", True)
            ):
                continue

            parent_anchor = display["parent_anchor"]
            child_anchor = display["child_anchor"]
            if display["setup_offset_length"] <= DISPLAY_TYPE_TOLERANCE:
                event.Display.DrawPoint(
                    parent_anchor,
                    Rhino.Display.PointStyle.RoundControlPoint,
                    6,
                    System.Drawing.Color.Orange,
                )
                continue

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
