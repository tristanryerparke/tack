import traceback

import Rhino
import System
import System.Drawing
from Rhino.Commands import Result


def _point_styles():
    styles_by_value = {}
    for name in System.Enum.GetNames(Rhino.Display.PointStyle):
        style = System.Enum.Parse(Rhino.Display.PointStyle, name)
        value = System.Convert.ToInt32(style)
        if value not in styles_by_value:
            styles_by_value[value] = ([], style)
        styles_by_value[value][0].append(name)
    return tuple(
        (" / ".join(names), style)
        for _, (names, style) in sorted(styles_by_value.items())
    )


POINT_STYLES = _point_styles()
COLUMN_COUNT = 3
CELL_WIDTH = 36.0
CELL_HEIGHT = 12.0
POINT_RADIUS = 12
TEXT_HEIGHT = 1.5


def _entries(plane):
    row_count = (len(POINT_STYLES) + COLUMN_COUNT - 1) // COLUMN_COUNT
    entries = []
    for index, (name, style) in enumerate(POINT_STYLES):
        column = index % COLUMN_COUNT
        row = index // COLUMN_COUNT
        point = plane.PointAt(
            (column - (COLUMN_COUNT - 1) / 2.0) * CELL_WIDTH,
            ((row_count - 1) / 2.0 - row) * CELL_HEIGHT,
        )
        entries.append((name, style, point))
    return entries


class PointStylePreviewConduit(Rhino.Display.DisplayConduit):
    def __init__(self, plane, entries):
        super(PointStylePreviewConduit, self).__init__()
        self.plane = plane
        self.entries = entries
        self.bounding_box = Rhino.Geometry.BoundingBox(
            [point for _, _, point in entries]
        )
        self.bounding_box.Inflate(
            CELL_WIDTH / 2.0,
            CELL_HEIGHT / 2.0,
            1.0,
        )

    def CalculateBoundingBox(self, event):
        event.IncludeBoundingBox(self.bounding_box)

    def CalculateBoundingBoxZoomExtents(self, event):
        self.CalculateBoundingBox(event)

    def DrawForeground(self, event):
        for name, style, point in self.entries:
            event.Display.DrawPoint(
                point,
                style,
                POINT_RADIUS,
                System.Drawing.Color.Cyan,
            )
            label_plane = Rhino.Geometry.Plane(self.plane)
            label_plane.Origin = point + self.plane.XAxis * 2.0
            event.Display.Draw3dText(
                name,
                System.Drawing.Color.White,
                label_plane,
                TEXT_HEIGHT,
                "Arial",
            )


def RunCommand(is_interactive):
    doc = Rhino.RhinoDoc.ActiveDoc
    view = doc.Views.ActiveView if doc is not None else None
    if view is None:
        return Result.Cancel

    plane = view.ActiveViewport.ConstructionPlane()
    conduit = PointStylePreviewConduit(plane, _entries(plane))
    conduit.Enabled = True
    view.ActiveViewport.ZoomBoundingBox(conduit.bounding_box)
    doc.Views.Redraw()

    try:
        getter = Rhino.Input.Custom.GetPoint()
        getter.SetCommandPrompt(
            "Point styles preview: click or press Esc to close"
        )
        getter.AcceptNothing(True)
        getter.Get()
    finally:
        conduit.Enabled = False
        doc.Views.Redraw()

    return Result.Success


if __name__ == "__main__":
    from tack.watcher import run_entrypoint

    run_entrypoint(lambda: RunCommand(True), True)
    print("Point styles preview closed.")
