"""Attach a child's analytic frame to a parent's analytic frame.

The child-placement preview suppresses the original object draw, displays its
old location in Rhino's locked-object wire color, and draws the transformed
object normally in the active display mode.

Run from the parent terminal:

    uv run rhino-watch demos/analytic_plane_link.py --debug
"""

import importlib
import json
import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import Rhino
from Rhino.Commands import Result
from run_in_rhino.rhino_env.client import SocketConnection
from run_in_rhino.rhino_env.env import install_os_environment
from run_in_rhino.rhino_env.parasite import OutputParasite

import tack

importlib.reload(tack).reload()

from tack import plane_link
from tack import plane_link_metadata
from tack import plane_link_preview
from tack import three_point_plane
from tack.prompting import analytic_plane_picker
from tack.prompting.osnap_anchor_picker import select_object


CALLBACK = "analytic_plane_link"


def _emit(connection, parasite, event, **data):
    payload = {"callback": CALLBACK, "event": event}
    payload.update(data)
    encoded = json.dumps(payload, sort_keys=True)
    print("CALLBACK {}".format(encoded))
    parasite.flush()
    connection.send_data(encoded)


def _pick_frame(doc, obj, role):
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
    plane = three_point_plane.resolve_definition(doc, definition)
    if plane is None:
        print("The {} frame could not be resolved.".format(role))
        return None
    return definition, plane


def _select_different_child(doc, parent_id):
    while True:
        child = select_object(doc, "Select child object")
        if child is None:
            return None
        if not str(child.Id).lower() == str(parent_id).lower():
            return child
        print("Select a child object different from the parent.")


def _preview_placement(doc, child, parent_plane, child_plane):
    conduit = plane_link_preview.TransformPreviewConduit(
        child,
        parent_plane,
        child_plane,
    )
    toggle = Rhino.Input.Custom.OptionToggle(False, "No", "Yes")
    getter = Rhino.Input.Custom.GetOption()
    getter.SetCommandPrompt("Preview the child placement")
    getter.AcceptNothing(True)
    getter.AddOptionToggle("Invert", toggle)
    done_index = getter.AddOption("Done")

    def sync_inversion():
        conduit.inverted = bool(toggle.CurrentValue)
        view = doc.Views.ActiveView
        if view is not None:
            view.Redraw()

    conduit.Enabled = True
    doc.Views.Redraw()
    try:
        while True:
            result = getter.Get()
            if result == Rhino.Input.GetResult.Nothing:
                sync_inversion()
                return conduit.transform, conduit.inverted
            if result != Rhino.Input.GetResult.Option:
                return None
            if getter.OptionIndex() == done_index:
                sync_inversion()
                return conduit.transform, conduit.inverted

            # Keep the conduit synchronized after every non-Done option. This
            # avoids relying on a particular OptionToggle index representation
            # and forces the changed transform to paint before Get resumes.
            sync_inversion()
    finally:
        conduit.Enabled = False
        doc.Views.Redraw()


def RunCommand(is_interactive, connection, parasite):
    doc = Rhino.RhinoDoc.ActiveDoc
    if doc is None or doc.Views.ActiveView is None:
        _emit(connection, parasite, "cancelled", stage="document")
        return Result.Cancel

    three_point_plane.uninstall()
    if not plane_link.clear_document(doc):
        print("The previous analytic-plane relationships could not be cleared.")
        _emit(connection, parasite, "reset_failed")
        return Result.Failure

    parent = select_object(doc, "Select parent object")
    if parent is None:
        _emit(connection, parasite, "cancelled", stage="parent_object")
        return Result.Cancel
    parent_result = _pick_frame(doc, parent, "parent")
    if parent_result is None:
        _emit(connection, parasite, "cancelled", stage="parent_frame")
        return Result.Cancel
    parent_definition, parent_plane = parent_result

    parent_conduit = plane_link_preview.PlaneDisplayConduit(parent_plane)
    parent_conduit.Enabled = True
    doc.Views.Redraw()
    try:
        child = _select_different_child(doc, parent.Id)
        if child is None:
            _emit(connection, parasite, "cancelled", stage="child_object")
            return Result.Cancel
        child_result = _pick_frame(doc, child, "child")
        if child_result is None:
            _emit(connection, parasite, "cancelled", stage="child_frame")
            return Result.Cancel
        child_definition, child_plane = child_result

        placement = _preview_placement(
            doc,
            child,
            parent_plane,
            child_plane,
        )
        if placement is None:
            _emit(connection, parasite, "cancelled", stage="placement")
            return Result.Cancel
        transform, inverted = placement

        undo_record = doc.BeginUndoRecord("Create analytic plane relationship")
        try:
            transformed_child = plane_link.transform_object_in_place(
                doc,
                child,
                transform,
            )
            if transformed_child is None:
                print("The child transformation failed.")
                _emit(connection, parasite, "transform_failed")
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
                print(
                    "The analytic-plane relationship metadata could not be saved."
                )
                _emit(connection, parasite, "save_failed")
                return Result.Failure
        finally:
            if undo_record:
                doc.EndUndoRecord(undo_record)
        plane_link.unsubscribe()
        if plane_link.install(doc, link) is None:
            print("The analytic-plane relationship runtime could not start.")
            _emit(connection, parasite, "runtime_failed", link=link)
            return Result.Failure

        _emit(
            connection,
            parasite,
            "completed",
            link_id=link["link_id"],
            parent_id=str(parent.Id),
            child_id=str(transformed_child.Id),
            inverted=inverted,
        )
        return Result.Success
    finally:
        parent_conduit.Enabled = False
        doc.Views.Redraw()


if __name__ == "__main__":
    connection = SocketConnection()
    install_os_environment(connection)
    with OutputParasite(connection, done_msg=True) as parasite:
        RunCommand(True, connection, parasite)
