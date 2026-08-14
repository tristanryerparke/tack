import Rhino
import System.Drawing

from tack import document_runtime
from tack import utils


DISPLAY_TYPE_TOLERANCE = 0.1
PARENT_COLOR = System.Drawing.Color.FromArgb(
    191,
    System.Drawing.Color.Red,
)
CHILD_COLOR = System.Drawing.Color.FromArgb(
    191,
    System.Drawing.Color.Orange,
)
OFFSET_LINE_COLOR = System.Drawing.Color.FromArgb(
    191,
    52,
    52,
    52,
)
CROSSHAIR_RADIUS = 24.0
CROSSHAIR_INNER_RADIUS = 3.75
CROSSHAIR_CIRCLE_SIZE = CROSSHAIR_INNER_RADIUS * 2.0
CROSSHAIR_THICKNESS = 2.0
OFFSET_LINE_PATTERN = 0x00001111
OFFSET_LINE_THICKNESS = 3


def _draw_circle(event, point, color):
    event.Display.DrawPoint(
        point,
        Rhino.Display.PointStyle.Circle,
        CROSSHAIR_CIRCLE_SIZE,
        color,
    )


def _draw_crosshair(event, point, color):
    center = event.Viewport.WorldToClient(point)
    horizontal_segments = (
        (center.X - CROSSHAIR_RADIUS, center.X - CROSSHAIR_INNER_RADIUS),
        (center.X + CROSSHAIR_INNER_RADIUS, center.X + CROSSHAIR_RADIUS),
    )
    for start_x, end_x in horizontal_segments:
        event.Display.Draw2dLine(
            System.Drawing.PointF(start_x, center.Y),
            System.Drawing.PointF(end_x, center.Y),
            color,
            CROSSHAIR_THICKNESS,
        )

    vertical_segments = (
        (center.Y - CROSSHAIR_RADIUS, center.Y - CROSSHAIR_INNER_RADIUS),
        (center.Y + CROSSHAIR_INNER_RADIUS, center.Y + CROSSHAIR_RADIUS),
    )
    for start_y, end_y in vertical_segments:
        event.Display.Draw2dLine(
            System.Drawing.PointF(center.X, start_y),
            System.Drawing.PointF(center.X, end_y),
            color,
            CROSSHAIR_THICKNESS,
        )

    _draw_circle(event, point, color)


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
                _draw_crosshair(event, parent_anchor, CHILD_COLOR)
                continue

            event.Display.DrawPatternedLine(
                parent_anchor,
                child_anchor,
                OFFSET_LINE_COLOR,
                OFFSET_LINE_PATTERN,
                OFFSET_LINE_THICKNESS,
            )
            _draw_crosshair(event, parent_anchor, PARENT_COLOR)
            _draw_crosshair(event, child_anchor, CHILD_COLOR)
