import Rhino
import System.Drawing

from tack import document_runtime
from tack import utils


DISPLAY_TYPE_TOLERANCE = 0.1
DISPLAY_COLOR = System.Drawing.Color.FromArgb(
    191,
    System.Drawing.Color.Orange,
)


class TackLinkConduit(Rhino.Display.DisplayConduit):
    def DrawForeground(self, event):
        doc = event.RhinoDoc
        if doc is None:
            return
        if document_runtime.try_get_value(
            doc,
            utils.DISPLAY_ENABLED_KEY,
        ) is False:
            return
        states = document_runtime.try_get_value(doc, utils.RUNTIME_KEY)
        if not states:
            return

        for state in states.values():
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
                    Rhino.Display.PointStyle.SolidRound,
                    6,
                    DISPLAY_COLOR,
                )
                continue

            event.Display.DrawLine(
                parent_anchor,
                child_anchor,
                DISPLAY_COLOR,
                3,
            )
            event.Display.DrawArrowHead(
                child_anchor,
                child_anchor - parent_anchor,
                DISPLAY_COLOR,
                32.0,
                0.0,
            )
