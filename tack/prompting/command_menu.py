import Rhino
import rhinoscriptsyntax as rs

from tack import utils
from tack.prompting import picking


DISABLE_NORMAL_OSNAPS = True


def pick_link(doc):
    if not DISABLE_NORMAL_OSNAPS:
        return _pick_link(doc)

    osnap_was_enabled = Rhino.ApplicationSettings.ModelAidSettings.Osnap
    Rhino.ApplicationSettings.ModelAidSettings.Osnap = False
    try:
        return _pick_link(doc)
    finally:
        Rhino.ApplicationSettings.ModelAidSettings.Osnap = osnap_was_enabled


def _pick_link(doc):
    parent_id = picking.pick_object(doc, "Select parent object")
    if not parent_id:
        return None
    parent = doc.Objects.Find(parent_id)
    if parent is None:
        return None

    parent_anchor = _pick_anchor(parent, "parent")
    if parent_anchor is None:
        return None

    parent_was_locked = rs.IsObjectLocked(parent_id)
    if not parent_was_locked:
        rs.LockObject(parent_id)
    try:
        child_id = picking.pick_object(doc, "Select child object")
    finally:
        if not parent_was_locked:
            rs.UnlockObject(parent_id)

    if not child_id or utils.same_id(child_id, parent_id):
        print("Select a different child object.")
        return None
    child = doc.Objects.Find(child_id)
    if child is None:
        return None

    child_anchor = _pick_anchor(child, "child")
    if child_anchor is None:
        return None
    return parent_id, child_id, parent_anchor, child_anchor


def _pick_anchor(obj, role):
    doc = Rhino.RhinoDoc.ActiveDoc
    locked_ids = picking.lock_other_objects(doc, obj.Id)
    try:
        return picking.pick_smart_anchor(obj, role)
    finally:
        picking.unlock_objects(locked_ids)
        doc.Views.Redraw()
