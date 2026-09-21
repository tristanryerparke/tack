"""Maintain active Tack relationships after document changes."""

import Rhino

from tack.anchors import analytic_plane
from tack.core.objects import find_object, same_id
from tack.links import repository, schema, state, transforms


def _show_broken_alert(link_state):
    if link_state.get("broken"):
        return
    link_state["broken"] = True
    link_state["plane"] = None
    Rhino.UI.Dialogs.ShowMessage(
        "A Tack relationship can no longer resolve both saved planes. "
        "The child will stop following the parent.",
        "Tack relationship broken",
        Rhino.UI.ShowMessageButton.OK,
        Rhino.UI.ShowMessageIcon.Warning,
    )


def maintain(doc, link_state):
    if link_state.get("busy"):
        return False
    parent = find_object(doc, link_state["parent_id"])
    child = find_object(doc, link_state["child_id"])
    if parent is None or child is None:
        _show_broken_alert(link_state)
        return False

    saved = repository.read_link(doc, link_state["link_id"])
    if saved is not None:
        link_state["link"] = saved
    link = link_state["link"]
    parent_plane = analytic_plane.resolve_definition(doc, link["parent_plane"])
    child_plane = analytic_plane.resolve_definition(doc, link["child_plane"])
    if parent_plane is None or child_plane is None:
        _show_broken_alert(link_state)
        return False

    link_state["broken"] = False
    link_state["plane"] = Rhino.Geometry.Plane(parent_plane)
    link_state["child_plane"] = Rhino.Geometry.Plane(child_plane)
    tolerance = max(doc.ModelAbsoluteTolerance, 1e-7)
    parent_changed = state.object_serial(parent) != link_state.get(
        "parent_runtime_serial"
    )
    child_changed = state.object_serial(child) != link_state.get("child_runtime_serial")

    translation = schema.translation_enabled(link)
    rotation = schema.rotation_enabled(link)
    if schema.link_mode(link) == "inherit_only":
        if child_changed and not parent_changed:
            current_transform = transforms.inherit_transform_data(
                parent_plane,
                child_plane,
            )
            if transforms.transform_data_matches(
                current_transform,
                link["current_transform"],
            ):
                state.refresh_serials(doc, link_state)
                return True
            updated = dict(link)
            updated["current_transform"] = current_transform
            if not repository.save(doc, updated):
                _show_broken_alert(link_state)
                return False
            link_state["link"] = updated
            state.refresh_serials(doc, link_state)
            doc.Views.Redraw()
            return True

        target_child_plane = transforms.inherit_target_child_plane(
            parent_plane,
            link["current_transform"],
        )
        if target_child_plane is None:
            _show_broken_alert(link_state)
            return False
        target_child_plane = transforms.constrained_target_child_plane(
            target_child_plane,
            child_plane,
            translation,
            rotation,
        )
    else:
        target_child_plane = transforms.linked_target_child_plane(
            parent_plane,
            child_plane,
            link["inverted"],
            translation,
            rotation,
        )

    if transforms.planes_match(target_child_plane, child_plane, False, tolerance):
        state.refresh_serials(doc, link_state)
        return True
    correction = Rhino.Geometry.Transform.PlaneToPlane(
        child_plane,
        target_child_plane,
    )

    link_state["busy"] = True
    try:
        transformed = transforms.transform_object_in_place(doc, child, correction)
        if transformed is None or not same_id(transformed.Id, child.Id):
            _show_broken_alert(link_state)
            return False
        resolved_child_plane = analytic_plane.resolve_definition(
            doc,
            link["child_plane"],
        )
        if resolved_child_plane is not None:
            link_state["child_plane"] = Rhino.Geometry.Plane(resolved_child_plane)
        state.refresh_serials(doc, link_state)
        doc.Views.Redraw()
        return True
    finally:
        link_state["busy"] = False


def changed_states(doc):
    changed = []
    for link_state in state.states(doc, create=False).values():
        if link_state.get("busy"):
            continue
        for role in ("parent", "child"):
            current = state.object_serial(find_object(doc, link_state[role + "_id"]))
            if current != link_state.get(role + "_runtime_serial"):
                changed.append(link_state)
                break
    return changed


def maintain_changed_states(doc, pending=()):
    """Settle changed and newly restored parent-to-child chains."""
    pending = {link_state["link_id"]: link_state for link_state in pending}
    max_passes = len(state.states(doc, create=False)) + 1
    for _ in range(max_passes):
        candidates = pending
        pending = {}
        for link_state in changed_states(doc):
            candidates[link_state["link_id"]] = link_state
        if not candidates:
            return
        for link_state in candidates.values():
            maintain(doc, link_state)
