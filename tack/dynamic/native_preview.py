"""Dynamic drawing for linked children during native Rhino transforms."""

import re

import Rhino

from tack.anchors import analytic_plane
from tack.core.objects import find_object, same_id
from tack.display.drawing import draw_locked_wireframe, draw_transformed_object
from tack.links import transforms

_COPY_ENABLED_PATTERN = re.compile(r"\bcopy\s*=\s*yes\b", re.IGNORECASE)
_ALLOWED_COMMANDS = {"drag", "move", "rotate", "rotate3d"}


def _dynamic_transform(rhino_object):
    if rhino_object is None:
        return None
    try:
        available, transform = rhino_object.GetDynamicTransform()
    except Exception:  # noqa: BLE001 - Rhino objects can outlive their geometry
        return None
    if not available or transform is None or transform.IsIdentity:
        return None
    return transform


class NativeTransformPreview:
    def __init__(self, document_serial, states):
        self.document_serial = int(document_serial)
        self.states = states
        self._sources = {}
        self._previews = {}
        self._drawing_child = False
        self._active_command = None

    def preview_for(self, link_id):
        return self._previews.get(link_id)

    def object_geometry(self, obj):
        if obj is None or obj.Geometry is None:
            return None
        geometry = obj.Geometry
        transform = _dynamic_transform(obj)
        if transform is None:
            for preview in self._previews.values():
                if same_id(preview["child"].Id, obj.Id):
                    transform = preview["transform"]
                    break
        if transform is None:
            return geometry
        geometry = geometry.Duplicate()
        if geometry is None or not geometry.Transform(transform):
            return obj.Geometry
        return geometry

    def clear(self):
        for preview in self._previews.values():
            preview["state"]["dynamic_preview_active"] = False
        self._sources.clear()
        self._previews.clear()

    def command_began(self, command_name):
        self._active_command = str(command_name or "").lower().lstrip("_")

    def command_ended(self):
        self._active_command = None
        self.clear()

    def _preview_allowed(self):
        if self._active_command not in _ALLOWED_COMMANDS:
            return False
        prompt = str(Rhino.RhinoApp.CommandPrompt or "")
        return _COPY_ENABLED_PATTERN.search(prompt) is None

    def _capture(self, doc, link_state):
        link = link_state["link"]
        parent = find_object(doc, link_state["parent_id"])
        child = find_object(doc, link_state["child_id"])
        if parent is None or child is None:
            return None
        parent_plane = analytic_plane.resolve_definition(doc, link["parent_plane"])
        child_plane = analytic_plane.resolve_definition(doc, link["child_plane"])
        if parent_plane is None or child_plane is None:
            return None
        return {
            "parent_serial": int(parent.RuntimeSerialNumber),
            "child_serial": int(child.RuntimeSerialNumber),
            "parent_plane": parent_plane,
            "child_plane": child_plane,
            "inverted": bool(link["inverted"]),
            "mode": link.get("mode", "attached"),
            "translation": link.get("translation", True),
            "rotation": link.get("rotation", True),
            "state": link_state,
        }

    def _source_for(self, doc, link_state):
        link_id = link_state["link_id"]
        parent = find_object(doc, link_state["parent_id"])
        child = find_object(doc, link_state["child_id"])
        if parent is None or child is None:
            return None
        source = self._sources.get(link_id)
        if (
            source is not None
            and source["parent_serial"] == int(parent.RuntimeSerialNumber)
            and source["child_serial"] == int(child.RuntimeSerialNumber)
        ):
            return source
        source = self._capture(doc, link_state)
        if source is not None:
            self._sources[link_id] = source
        return source

    def update(self, doc):
        for preview in self._previews.values():
            preview["state"]["dynamic_preview_active"] = False

        states = [
            link_state
            for link_state in self.states.values()
            if not link_state.get("busy") and not link_state.get("broken")
        ]
        if not self._preview_allowed():
            self._sources.clear()
            self._previews = {}
            return

        live_transforms = {}
        direct_dynamic_objects = set()
        for link_state in states:
            for role in ("parent", "child"):
                obj = find_object(doc, link_state[role + "_id"])
                dynamic_transform = _dynamic_transform(obj)
                if dynamic_transform is None:
                    continue
                object_key = str(obj.Id).lower()
                direct_dynamic_objects.add(object_key)
                if role == "parent":
                    live_transforms[object_key] = dynamic_transform

        previews = {}
        for _ in range(len(states) + 1):
            added_transform = False
            for link_state in states:
                parent = find_object(doc, link_state["parent_id"])
                child = find_object(doc, link_state["child_id"])
                if parent is None or child is None:
                    continue
                source = self._source_for(doc, link_state)
                if source is None:
                    continue

                parent_transform = live_transforms.get(str(parent.Id).lower())
                child_is_directly_dynamic = (
                    str(child.Id).lower() in direct_dynamic_objects
                )
                if parent_transform is not None and child_is_directly_dynamic:
                    continue
                if parent_transform is None:
                    continue

                live_parent_plane = Rhino.Geometry.Plane(source["parent_plane"])
                live_parent_plane.Transform(parent_transform)
                if not source["rotation"]:
                    live_parent_plane = Rhino.Geometry.Plane(
                        live_parent_plane.Origin,
                        source["parent_plane"].XAxis,
                        source["parent_plane"].YAxis,
                    )
                live_child_plane = Rhino.Geometry.Plane(source["child_plane"])
                if source["mode"] == "inherit_only":
                    target_child_plane = transforms.inherit_target_child_plane(
                        live_parent_plane,
                        source["state"]["link"]["current_transform"],
                    )
                    if target_child_plane is None:
                        continue
                    target_child_plane = transforms.constrained_target_child_plane(
                        target_child_plane,
                        live_child_plane,
                        source["translation"],
                        source["rotation"],
                    )
                else:
                    target_child_plane = transforms.linked_target_child_plane(
                        live_parent_plane,
                        live_child_plane,
                        source["inverted"],
                        source["translation"],
                        source["rotation"],
                    )
                preview_transform = Rhino.Geometry.Transform.PlaneToPlane(
                    live_child_plane,
                    target_child_plane,
                )
                if preview_transform.IsIdentity:
                    continue

                previews[link_state["link_id"]] = {
                    "child": child,
                    "state": link_state,
                    "parent_plane": live_parent_plane,
                    "child_plane": target_child_plane,
                    "transform": preview_transform,
                    "draw_child": not child_is_directly_dynamic,
                }
                link_state["dynamic_preview_active"] = True

                child_key = str(child.Id).lower()
                if (
                    child_key not in live_transforms
                    and child_key not in direct_dynamic_objects
                ):
                    live_transforms[child_key] = preview_transform
                    added_transform = True
            if not added_transform:
                break

        self._previews = previews
        if not previews:
            self._sources.clear()

    def suppresses_object(self, obj):
        return bool(
            obj is not None
            and not self._drawing_child
            and any(
                preview["draw_child"] and same_id(obj.Id, preview["child"].Id)
                for preview in self._previews.values()
            )
        )

    def include_bounding_boxes(self, event):
        for preview in self._previews.values():
            if not preview["draw_child"]:
                continue
            geometry = preview["child"].Geometry
            if geometry is None:
                continue
            bounding_box = geometry.GetBoundingBox(True)
            if not bounding_box.IsValid:
                continue
            points = list(bounding_box.GetCorners())
            transformed = []
            for point in points:
                moved = Rhino.Geometry.Point3d(point)
                moved.Transform(preview["transform"])
                transformed.append(moved)
            event.IncludeBoundingBox(Rhino.Geometry.BoundingBox(points + transformed))

    def draw_objects(self, event):
        for preview in self._previews.values():
            if not preview["draw_child"]:
                continue
            child = preview["child"]
            if child is None or child.Geometry is None:
                continue
            draw_locked_wireframe(event.Display, child.Geometry)
            self._drawing_child = True
            try:
                draw_transformed_object(
                    event.Display,
                    child,
                    preview["transform"],
                )
            finally:
                self._drawing_child = False
