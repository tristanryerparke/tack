"""Maintain active Tack Links after document changes."""

from dataclasses import replace

import Rhino

from tack.anchors import analytic_plane
from tack.core.objects import find_object, same_id
from tack.links import repository, state, transforms


def _show_invalid_alert():
    Rhino.UI.Dialogs.ShowMessage(
        "A Tack relationship can no longer resolve both saved planes. "
        "The child will stop following the parent.",
        "Tack relationship invalid",
        Rhino.UI.ShowMessageButton.OK,
        Rhino.UI.ShowMessageIcon.Warning,
    )


def invalidate(doc, link_state):
    """Persist failure on the Link; its temporary state is then discarded."""
    repository.set_valid(doc, link_state.link_id, False, link_state.parent_id)
    state.remember_state(doc, link_state, reset=False)
    _show_invalid_alert()


def maintain(doc, link_state):
    if link_state.busy:
        return False
    link = repository.read_link(doc, link_state.link_id, link_state.parent_id)
    parent = find_object(doc, link_state.parent_id)
    child = find_object(doc, link_state.child_id)
    if link is None or parent is None or child is None:
        invalidate(doc, link_state)
        return False

    parent_plane = analytic_plane.resolve_definition(doc, link.parent_plane_def)
    child_plane = analytic_plane.resolve_definition(doc, link.child_plane_def)
    if parent_plane is None or child_plane is None:
        invalidate(doc, link_state)
        return False

    link_state.parent_plane = Rhino.Geometry.Plane(parent_plane)
    link_state.child_plane = Rhino.Geometry.Plane(child_plane)
    tolerance = max(doc.ModelAbsoluteTolerance, 1e-7)
    parent_changed = state.object_serial(parent) != link_state.parent_serial
    child_changed = state.object_serial(child) != link_state.child_serial

    if child_changed and not parent_changed and link.allow_child_movement:
        current_transform = transforms.inherit_transform_data(parent_plane, child_plane)
        if transforms.transform_data_matches(current_transform, link.current_transform):
            state.refresh_serials(doc, link_state)
            return True
        if not repository.save(
            doc,
            replace(link, current_transform=current_transform),
            replaced=(link,),
        ):
            invalidate(doc, link_state)
            return False
        state.refresh_serials(doc, link_state)
        doc.Views.Redraw()
        return True

    target_child_plane = transforms.inherit_target_child_plane(
        parent_plane,
        link.current_transform,
    )
    if target_child_plane is None:
        invalidate(doc, link_state)
        return False
    target_child_plane = transforms.constrained_target_child_plane(
        target_child_plane,
        child_plane,
        link.translation,
        link.rotation,
    )

    if transforms.planes_match(target_child_plane, child_plane, tolerance):
        state.refresh_serials(doc, link_state)
        return True
    correction = Rhino.Geometry.Transform.PlaneToPlane(child_plane, target_child_plane)

    link_state.busy = True
    try:
        transformed = transforms.transform_object_in_place(doc, child, correction)
        if transformed is None or not same_id(transformed.Id, child.Id):
            invalidate(doc, link_state)
            return False
        resolved_child_plane = analytic_plane.resolve_definition(doc, link.child_plane_def)
        if resolved_child_plane is not None:
            link_state.child_plane = Rhino.Geometry.Plane(resolved_child_plane)
        state.refresh_serials(doc, link_state)
        doc.Views.Redraw()
        return True
    finally:
        link_state.busy = False


def maintain_changed_states(doc, pending=()):
    """Maintain changed Links once in parent-to-child topological order."""
    pending_ids = {link_state.link_id for link_state in pending}
    for link_state in state.ordered_states(state.states(doc, create=False)):
        if link_state.link_id in pending_ids or state.changed(doc, link_state):
            maintain(doc, link_state)
