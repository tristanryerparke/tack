"""Shared Python implementation behind Tack's C# commands and panel buttons."""

import Rhino
from Rhino.Commands import Result

from tack import analytic_plane
from tack import display
from tack import plane_link
from tack import plane_link_metadata
from tack.prompting import analytic_plane_picker
from tack.prompting.osnap_anchor_picker import select_object


def _pick_plane(doc, obj, role):
    view = doc.Views.ActiveView
    if view is None:
        return None
    picked = analytic_plane_picker.pick_plane(
        doc,
        obj,
        view.ActiveViewport.ConstructionPlane(),
    )
    if picked is None:
        return None
    definition = picked["definition"]
    plane = analytic_plane.resolve_definition(doc, definition)
    if plane is None:
        Rhino.RhinoApp.WriteLine(
            "The {} Tack plane could not be resolved.".format(role)
        )
        return None
    return definition, plane


def _select_child(doc, parent_id):
    while True:
        child = select_object(
            doc,
            "Select child object",
            allow_preselection=False,
        )
        if child is None:
            return None
        if not str(child.Id).lower() == str(parent_id).lower():
            return child
        Rhino.RhinoApp.WriteLine("Select a child different from the parent.")


def _preview_placement(doc, child, parent_plane, child_plane):
    conduit = display.TransformPreviewConduit(
        child,
        parent_plane,
        child_plane,
    )
    inverted = Rhino.Input.Custom.OptionToggle(False, "No", "Yes")
    getter = Rhino.Input.Custom.GetOption()
    getter.SetCommandPrompt("Preview the child placement")
    getter.AcceptNothing(True)
    getter.AddOptionToggle("Invert", inverted)
    done_index = getter.AddOption("Done")

    def redraw():
        conduit.inverted = bool(inverted.CurrentValue)
        doc.Views.Redraw()

    conduit.Enabled = True
    doc.Views.Redraw()
    try:
        while True:
            result = getter.Get()
            if result == Rhino.Input.GetResult.Nothing:
                redraw()
                return conduit.transform, conduit.inverted
            if result != Rhino.Input.GetResult.Option:
                return None
            if getter.OptionIndex() == done_index:
                redraw()
                return conduit.transform, conduit.inverted
            redraw()
    finally:
        conduit.Enabled = False
        doc.Views.Redraw()


def add(doc, default_display_enabled=True):
    if doc is None or doc.Views.ActiveView is None:
        return Result.Cancel

    parent = select_object(doc, "Select parent object")
    if parent is None:
        return Result.Cancel
    parent_result = _pick_plane(doc, parent, "parent")
    if parent_result is None:
        return Result.Cancel
    parent_definition, parent_plane = parent_result

    parent_display = display.PlaneDisplayConduit(parent_plane)
    parent_display.Enabled = True
    doc.Views.Redraw()
    try:
        child = _select_child(doc, parent.Id)
        if child is None:
            return Result.Cancel
        child_result = _pick_plane(doc, child, "child")
        if child_result is None:
            return Result.Cancel
        child_definition, child_plane = child_result
        placement = _preview_placement(doc, child, parent_plane, child_plane)
        if placement is None:
            return Result.Cancel
        transform, inverted = placement

        undo_record = doc.BeginUndoRecord("Add Tack")
        try:
            transformed_child = plane_link.transform_object_in_place(
                doc,
                child,
                transform,
            )
            if transformed_child is None:
                return Result.Failure
            child_definition["object_id"] = str(transformed_child.Id)
            link = plane_link_metadata.create(
                doc,
                parent.Id,
                transformed_child.Id,
                parent_definition,
                child_definition,
                inverted,
            )
            if link is None:
                return Result.Failure
        finally:
            if undo_record:
                doc.EndUndoRecord(undo_record)

        if plane_link.install(doc, link, default_display_enabled) is None:
            return Result.Failure
        return Result.Success
    finally:
        parent_display.Enabled = False
        doc.Views.Redraw()


def show(doc):
    if not plane_link.set_display_enabled(doc, True):
        Rhino.RhinoApp.WriteLine("No active Tacks to show.")
        return Result.Cancel
    return Result.Success


def hide(doc):
    if not plane_link.set_display_enabled(doc, False):
        Rhino.RhinoApp.WriteLine("No active Tacks to hide.")
        return Result.Cancel
    return Result.Success


def clear(doc):
    if doc is None:
        return Result.Cancel
    count = len(plane_link_metadata.all_links(doc))
    plane_link.clear_document(doc)
    Rhino.RhinoApp.WriteLine("Cleared {} Tack(s).".format(count))
    return Result.Success


def restore_open_documents(default_display_enabled=True):
    restored = 0
    for doc in Rhino.RhinoDoc.OpenDocuments(False):
        restored += plane_link.restore_document(doc, default_display_enabled)
    if restored:
        Rhino.RhinoApp.WriteLine("Restored {} Tack(s).".format(restored))
    return Result.Success


_ACTIONS = {
    "add": add,
    "show": show,
    "hide": hide,
    "clear": clear,
}


def run(action, doc=None, default_display_enabled=True):
    implementation = _ACTIONS.get(action)
    if implementation is None:
        raise ValueError("Unknown Tack action: {}".format(action))
    active_doc = Rhino.RhinoDoc.ActiveDoc if doc is None else doc
    if active_doc is None:
        return Result.Cancel
    if action == "add":
        return implementation(active_doc, default_display_enabled)
    return implementation(active_doc)
