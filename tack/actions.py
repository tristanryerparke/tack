"""Shared Python implementation behind Tack's C# commands and panel buttons."""

import Rhino
from Rhino.Commands import Result

from tack.core import plugin_data
from tack.display.plane_preview import PlaneDisplayConduit
from tack.links import graph, repository, runtime, schema, transforms
from tack.prompting.add_flow import (
    pick_plane,
    preview_placement,
    select_child,
    select_parent_and_degrees_of_freedom,
)


def _refresh_panel(doc):
    from tack.ui import panel

    panel.refresh(doc)


def add(doc, default_display_enabled=True):
    if doc is None or doc.Views.ActiveView is None:
        return Result.Cancel

    parent_selection = select_parent_and_degrees_of_freedom(doc)
    if parent_selection is None:
        return Result.Cancel
    parent, degrees_of_freedom = parent_selection
    parent_result = pick_plane(
        doc,
        parent,
        "parent",
        degrees_of_freedom["rotation"],
    )
    if parent_result is None:
        return Result.Cancel
    parent_definition, parent_plane = parent_result

    parent_display = PlaneDisplayConduit(parent_plane)
    parent_display.Enabled = True
    doc.Views.Redraw()
    try:
        child = select_child(doc, parent.Id)
        if child is None:
            return Result.Cancel
        replacing = any(
            schema.same_object_pair(
                link,
                {"parent_id": str(parent.Id), "child_id": str(child.Id)},
            )
            for link in repository.all_links(doc)
        )
        if not replacing and graph.would_create_cycle(
            repository.all_links(doc),
            parent.Id,
            child.Id,
        ):
            Rhino.UI.Dialogs.ShowMessage(
                "This Tack would create a parent-child loop. "
                "Tack loops are unstable and cannot be created.",
                "Tack loop not allowed",
                Rhino.UI.ShowMessageButton.OK,
                Rhino.UI.ShowMessageIcon.Warning,
            )
            return Result.Cancel
        child_result = pick_plane(
            doc,
            child,
            "child",
            degrees_of_freedom["rotation"],
        )
        if child_result is None:
            return Result.Cancel
        child_definition, child_plane = child_result
        mode = "attached" if degrees_of_freedom["attach"] else "inherit_only"

        inverted = False
        original_transform = None
        current_transform = None
        transformed_child = child
        if mode == "attached":
            placement = preview_placement(
                doc,
                child,
                parent_plane,
                child_plane,
                degrees_of_freedom["translation"],
                degrees_of_freedom["rotation"],
            )
            if placement is None:
                return Result.Cancel
            transform, inverted = placement
        else:
            original_transform = transforms.inherit_transform_data(
                parent_plane,
                child_plane,
            )
            current_transform = list(original_transform)

        undo_record = doc.BeginUndoRecord("Add Tack")
        try:
            if mode == "attached":
                transformed_child = transforms.transform_object_in_place(
                    doc,
                    child,
                    transform,
                )
                if transformed_child is None:
                    return Result.Failure
            child_definition["object_id"] = str(transformed_child.Id)
            link = repository.create(
                doc,
                parent.Id,
                transformed_child.Id,
                parent_definition,
                child_definition,
                inverted,
                mode=mode,
                original_transform=original_transform,
                current_transform=current_transform,
                translation=degrees_of_freedom["translation"],
                rotation=degrees_of_freedom["rotation"],
            )
            if link is None:
                return Result.Failure
        finally:
            if undo_record:
                doc.EndUndoRecord(undo_record)

        if runtime.install(doc, link, default_display_enabled) is None:
            return Result.Failure
        _refresh_panel(doc)
        return Result.Success
    finally:
        parent_display.Enabled = False
        doc.Views.Redraw()


def show(doc):
    if not runtime.set_display_enabled(doc, True):
        Rhino.RhinoApp.WriteLine("No active Tacks to show.")
        return Result.Cancel
    return Result.Success


def hide(doc):
    if not runtime.set_display_enabled(doc, False):
        Rhino.RhinoApp.WriteLine("No active Tacks to hide.")
        return Result.Cancel
    return Result.Success


def remove(doc, link_id):
    if doc is None or repository.read_link(doc, link_id) is None:
        Rhino.RhinoApp.WriteLine("The selected Tack no longer exists.")
        return Result.Cancel
    if not runtime.remove_link(doc, link_id):
        return Result.Failure
    _refresh_panel(doc)
    Rhino.RhinoApp.WriteLine("Deleted Tack {}.".format(str(link_id)[:8]))
    return Result.Success


def clear(doc):
    if doc is None:
        return Result.Cancel
    count = len(repository.all_links(doc))
    if not count:
        Rhino.RhinoApp.WriteLine("No Tacks to clear.")
        return Result.Cancel
    confirmation = Rhino.UI.Dialogs.ShowMessage(
        "Clear all {} Tack(s) from this file?".format(count),
        "Clear all Tacks",
        Rhino.UI.ShowMessageButton.YesNo,
        Rhino.UI.ShowMessageIcon.Warning,
    )
    if confirmation != Rhino.UI.ShowMessageResult.Yes:
        return Result.Cancel
    if not runtime.clear_document(doc):
        return Result.Failure
    _refresh_panel(doc)
    Rhino.RhinoApp.WriteLine("Cleared {} Tack(s).".format(count))
    return Result.Success


def restore_open_documents(default_display_enabled=None):
    if default_display_enabled is None:
        saved_default = plugin_data.setting(plugin_data.DEFAULT_DISPLAY_ENABLED, True)
        default_display_enabled = (
            saved_default if isinstance(saved_default, bool) else True
        )
    restored = 0
    for doc in Rhino.RhinoDoc.OpenDocuments(False):
        restored += runtime.restore_document(doc, default_display_enabled)
        _refresh_panel(doc)
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
