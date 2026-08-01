import Rhino
import scriptcontext as sc

import tack.analysis.bbox as bbox_analysis
import tack.analysis.vertex as vertex_analysis
from tack import conduit
from tack import metadata
from tack import utils


def stop_runtime():
    active_conduit = sc.sticky.pop(utils.CONDUIT_KEY, None)
    if active_conduit is not None:
        active_conduit.Enabled = False
    sc.sticky.pop(utils.RUNTIME_KEY, None)


def start_runtime(parent_id, child_id):
    stop_runtime()
    doc = Rhino.RhinoDoc.ActiveDoc
    parent = doc.Objects.Find(parent_id)
    child = doc.Objects.Find(child_id)
    if parent is None or child is None:
        return False

    link = metadata.read_link(child)
    if link is None:
        return False
    state = {
        "parent_id": parent_id,
        "child_id": child_id,
        "busy": False,
        "broken": False,
        "replacement_pending_ids": [],
        "replacement_reconcile_roles": [],
        "link": link,
    }
    analyzers = {
        bbox_analysis.ANCHOR_TYPE: bbox_analysis,
        vertex_analysis.ANCHOR_TYPE: vertex_analysis,
    }
    for role, obj in (("parent", parent), ("child", child)):
        anchor = link[role + "_anchor"]
        analyzer = analyzers.get(anchor["anchor_type"])
        if analyzer is None or analyzer.resolve(obj, anchor) is None:
            return False
        state[role + "_anchors"] = analyzer.anchors(obj)
    sc.sticky[utils.RUNTIME_KEY] = state

    active_conduit = conduit.TackLinkConduit()
    active_conduit.Enabled = True
    sc.sticky[utils.CONDUIT_KEY] = active_conduit
    if utils.DEBUG:
        print(
            "[Tack anchor] runtime started parent={} child={} debug={}".format(
                parent_id,
                child_id,
                utils.DEBUG,
            )
        )
    doc.Views.Redraw()
    return True
