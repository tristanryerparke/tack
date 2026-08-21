#! python 3
"""Show screen-space pill labels anchored to world points.

Run from the project root with run-in-rhino, for example:

    uv run rhino-watch tests/rhino/pill_dot_conduit.py --debug

The conduit is kept in ``scriptcontext.sticky`` so it remains visible after
this script reports completion. Run the script again to replace the previous
conduit.
"""

import Rhino
import scriptcontext as sc
from Rhino.Display import DisplayConduit
from Rhino.Geometry import Point2d, Point3d
from System.Drawing import Color

from run_in_rhino.rhino_env.client import SocketConnection
from run_in_rhino.rhino_env.parasite import OutputParasite


STICKY_KEY = "Tack.Test.PillDotConduit"


class PillDotConduit(DisplayConduit):
    def __init__(self, labels, text_height=16, padding=7):
        super(PillDotConduit, self).__init__()
        self.labels = labels
        self.text_height = text_height
        self.padding = padding
        self.fill_color = Color.FromArgb(235, 255, 255, 255)
        self.text_color = Color.FromArgb(255, 20, 20, 20)

    def DrawForeground(self, event):
        for anchor, label in self.labels:
            # DrawDot uses Rhino's native pill rendering in the display
            # pipeline, just as Tack draws its foreground graphics here.
            event.Display.DrawDot(
                anchor,
                label,
                self.text_color,
                self.fill_color,
            )


def install_test_conduit():
    previous = sc.sticky.get(STICKY_KEY)
    if previous is not None:
        previous.Enabled = False

    labels = [
        (Point3d(0, 0, 0), "Origin"),
        (Point3d(10, 0, 0), "Ten"),
        (Point3d(0, 10, 0), "Longer label"),
    ]
    conduit = PillDotConduit(labels)
    sc.sticky[STICKY_KEY] = conduit
    conduit.Enabled = True

    sc.doc.Views.Redraw()
    print(
        "Installed {} pill labels; sticky={}, enabled={}.".format(
            len(labels),
            sc.sticky.get(STICKY_KEY) is conduit,
            conduit.Enabled,
        )
    )


connection = SocketConnection()
with OutputParasite(connection, done_msg=True):
    install_test_conduit()
    print("Pill dot conduit test complete; sent done.")
