"""Display conduit for a single analytic-plane preview."""

import Rhino

from tack.anchors import analytic_plane


class PlaneDisplayConduit(Rhino.Display.DisplayConduit):
    def __init__(self, plane):
        super().__init__()
        self.plane = plane

    def CalculateBoundingBox(self, event):
        event.IncludeBoundingBox(analytic_plane.bounding_box(self.plane))

    def DrawOverlay(self, event):
        analytic_plane.draw_preview(event.Display, self.plane)
