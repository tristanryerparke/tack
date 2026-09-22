"""Maintain active Tack Links after document changes."""

import Rhino

from tack.anchors import analytic_plane
from tack.core.objects import find_object, same_id
from tack.links import repository, state, transforms


def _show_invalid_alert(doc, link_state):
    """Persist failure on the Link; its temporary state is then discarded."""
    repository.set_valid(doc, link_state.link_id, False, link_state.parent_id)
    state.cache_state(doc, link_state)
    Rhino.UI.Dialogs.ShowMessage(
        "A Tack relationship can no longer resolve both saved planes. "
        "The child will stop following the parent.",
        "Tack relationship invalid",
        Rhino.UI.ShowMessageButton.OK,
        Rhino.UI.ShowMessageIcon.Warning,
    )


def maintain(doc, link_state):
    if link_state.busy:
        return False
    link = repository.read_link(doc, link_state.link_id, link_state.parent_id)
    parent = find_object(doc, link_state.parent_id)
    child = find_object(doc, link_state.child_id)
    if link is None or parent is None or child is None:
        _show_invalid_alert(doc, link_state)
        return False

    parent_plane = analytic_plane.resolve_definition(doc, link.parent_plane_def)
    child_plane = analytic_plane.resolve_definition(doc, link.child_plane_def)
    if parent_plane is None or child_plane is None:
        _show_invalid_alert(doc, link_state)
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
        from dataclasses import replace

        if not repository.save(
            doc,
            replace(link, current_transform=current_transform),
            replaced=(link,),
        ):
            _show_invalid_alert(doc, link_state)
            return False
        state.refresh_serials(doc, link_state)
        doc.Views.Redraw()
        return True

    target_child_plane = transforms.inherit_target_child_plane(
        parent_plane,
        link.current_transform,
    )
    if target_child_plane is None:
        _show_invalid_alert(doc, link_state)
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
            _show_invalid_alert(doc, link_state)
            return False
        resolved_child_plane = analytic_plane.resolve_definition(doc, link.child_plane_def)
        if resolved_child_plane is not None:
            link_state.child_plane = Rhino.Geometry.Plane(resolved_child_plane)
        state.refresh_serials(doc, link_state)
        doc.Views.Redraw()
        return True
    finally:
        link_state.busy = False


def changed_states(doc):
    changed = []
    for link_state in state.states(doc, create=False).values():
        if link_state.busy:
            continue
        parent = find_object(doc, link_state.parent_id)
        child = find_object(doc, link_state.child_id)
        if (
            state.object_serial(parent) != link_state.parent_serial
            or state.object_serial(child) != link_state.child_serial
        ):
            changed.append(link_state)
    return changed


def maintain_changed_states(doc, pending=()):
    """Settle changed and newly restored parent-to-child chains."""
    pending = {link_state.link_id: link_state for link_state in pending}
    max_passes = len(state.states(doc, create=False)) + 1
    for _ in range(max_passes):
        candidates = pending
        pending = {}
        for link_state in changed_states(doc):
            candidates[link_state.link_id] = link_state
        if not candidates:
            return
        for link_state in candidates.values():
            maintain(doc, link_state)
