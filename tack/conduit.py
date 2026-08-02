import Rhino
import System.Drawing
import scriptcontext as sc

from tack import link
from tack import metadata
from tack import utils


DISPLAY_TYPE_TOLERANCE = 0.1


def _runtime_state(saved_link):
    for link_id, state in sc.sticky.get(utils.RUNTIME_KEY, {}).items():
        if utils.same_id(link_id, saved_link["link_id"]):
            return state
    return {
        "link_id": saved_link["link_id"],
        "parent_id": saved_link["parent_id"],
        "child_id": saved_link["child_id"],
        "link": saved_link,
    }


class TackLinkConduit(Rhino.Display.DisplayConduit):
    def DrawForeground(self, event):
        doc = Rhino.RhinoDoc.ActiveDoc
        if doc is None:
            return
        for saved_link in metadata.all_links(doc):
            state = _runtime_state(saved_link)
            if state.get("broken"):
                continue
            result = link.inspect_link(doc, state)
            if result is None:
                continue

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
