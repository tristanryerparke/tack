"""Display conduits for analytic plane picking and live Tack links."""

import re

import Rhino
import System.Drawing

from tack import analytic_plane
from tack import utils


LOCKED_WIRE_THICKNESS = 1
TREE_SELECTION_WIRE_THICKNESS = 4
_COPY_ENABLED_PATTERN = re.compile(r"\bcopy\s*=\s*yes\b", re.IGNORECASE)


def inverted_plane(plane):
    return Rhino.Geometry.Plane(plane.Origin, plane.XAxis, -plane.YAxis)


def plane_to_plane_transform(parent_plane, child_plane, inverted=False):
    source = inverted_plane(child_plane) if inverted else child_plane
    return Rhino.Geometry.Transform.PlaneToPlane(source, parent_plane)


def constrained_target_child_plane(
    target_plane,
    child_plane,
    translation=True,
    rotation=True,
):
    """Keep the child components excluded by a Tack's degrees of freedom."""
    origin = target_plane.Origin if translation else child_plane.Origin
    x_axis = target_plane.XAxis if rotation else child_plane.XAxis
    y_axis = target_plane.YAxis if rotation else child_plane.YAxis
    return Rhino.Geometry.Plane(origin, x_axis, y_axis)


def linked_target_child_plane(
    parent_plane,
    child_plane,
    inverted=False,
    translation=True,
    rotation=True,
):
    target_plane = inverted_plane(parent_plane) if inverted and rotation else parent_plane
    return constrained_target_child_plane(
        target_plane,
        child_plane,
        translation,
        rotation,
    )


def constrained_plane_transform(
    parent_plane,
    child_plane,
    inverted=False,
    translation=True,
    rotation=True,
):
    target_plane = linked_target_child_plane(
        parent_plane,
        child_plane,
        inverted,
        translation,
        rotation,
    )
    return Rhino.Geometry.Transform.PlaneToPlane(child_plane, target_plane)


def _draw_bounding_box(display, geometry, color, thickness):
    bounding_box = geometry.GetBoundingBox(True)
    if not bounding_box.IsValid:
        return
    for line in Rhino.Geometry.Box(bounding_box).GetEdges():
        display.DrawLine(line, color, thickness)


def _draw_brep_edges(display, brep, color, thickness):
    if brep is None:
        return
    for edge in brep.Edges:
        display.DrawCurve(edge, color, thickness)


def _draw_wireframe(display, geometry, color, thickness):
    if isinstance(geometry, Rhino.Geometry.Brep):
        _draw_brep_edges(display, geometry, color, thickness)
    elif isinstance(geometry, Rhino.Geometry.Extrusion):
        _draw_brep_edges(display, geometry.ToBrep(), color, thickness)
    elif isinstance(geometry, Rhino.Geometry.Mesh):
        display.DrawMeshWires(geometry, color, thickness)
    elif isinstance(geometry, Rhino.Geometry.Curve):
        display.DrawCurve(geometry, color, thickness)
    elif isinstance(geometry, Rhino.Geometry.SubD):
        display.DrawSubDWires(geometry, color, float(thickness))
    elif isinstance(geometry, Rhino.Geometry.Surface):
        _draw_brep_edges(display, geometry.ToBrep(), color, thickness)
    elif isinstance(geometry, Rhino.Geometry.Point):
        display.DrawPoint(geometry.Location, color)
    elif isinstance(geometry, Rhino.Geometry.PointCloud):
        display.DrawPointCloud(geometry, 2, color)
    else:
        _draw_bounding_box(display, geometry, color, thickness)


def _draw_locked_wireframe(display, geometry):
    _draw_wireframe(
        display,
        geometry,
        Rhino.ApplicationSettings.AppearanceSettings.LockedObjectColor,
        LOCKED_WIRE_THICKNESS,
    )


def _draw_dotted_line(display, start, end, color, thickness, spacing):
    direction = end - start
    length = direction.Length
    if length <= 1e-7:
        return
    dot_count = min(200, max(1, int(length / max(spacing, 1e-7))))
    step = length / dot_count
    direction.Unitize()
    for index in range(dot_count):
        dot_start = start + direction * (index * step)
        dot_end = start + direction * (index * step + step * 0.35)
        display.DrawLine(dot_start, dot_end, color, thickness)


class PlaneDisplayConduit(Rhino.Display.DisplayConduit):
    def __init__(self, plane):
        super(PlaneDisplayConduit, self).__init__()
        self.plane = plane

    def CalculateBoundingBox(self, event):
        event.IncludeBoundingBox(analytic_plane.bounding_box(self.plane))

    def DrawOverlay(self, event):
        analytic_plane.draw_preview(event.Display, self.plane)


class TransformPreviewConduit(Rhino.Display.DisplayConduit):
    def __init__(
        self,
        child,
        parent_plane,
        child_plane,
        inverted=False,
        translation=True,
        rotation=True,
    ):
        super(TransformPreviewConduit, self).__init__()
        self.child = child
        self.parent_plane = parent_plane
        self.child_plane = child_plane
        self.inverted = bool(inverted)
        self.translation = bool(translation)
        self.rotation = bool(rotation)
        self._drawing_child = False

    @property
    def transform(self):
        return constrained_plane_transform(
            self.parent_plane,
            self.child_plane,
            self.inverted,
            self.translation,
            self.rotation,
        )

    def CalculateBoundingBox(self, event):
        bounding_box = self.child.Geometry.GetBoundingBox(True)
        if not bounding_box.IsValid:
            return
        points = list(bounding_box.GetCorners())
        transformed = []
        for point in points:
            moved = Rhino.Geometry.Point3d(point)
            moved.Transform(self.transform)
            transformed.append(moved)
        event.IncludeBoundingBox(Rhino.Geometry.BoundingBox(points + transformed))

    def PreDrawObject(self, event):
        if self._drawing_child:
            return
        obj = event.RhinoObject
        if obj is not None and utils.same_id(obj.Id, self.child.Id):
            event.DrawObject = False

    def PostDrawObjects(self, event):
        if self.child is None or self.child.Geometry is None:
            return
        _draw_locked_wireframe(event.Display, self.child.Geometry)
        self._drawing_child = True
        try:
            event.Display.DrawObject(self.child, self.transform)
        finally:
            self._drawing_child = False


def _dynamic_transform(rhino_object):
    if rhino_object is None:
        return None
    try:
        available, transform = rhino_object.GetDynamicTransform()
    except Exception:
        return None
    if not available or transform is None or transform.IsIdentity:
        return None
    return transform


class LinkedPlaneConduit(Rhino.Display.DisplayConduit):
    """Document-scoped persistent planes and native-transform previews."""

    def __init__(self, document_serial, states, display_state):
        super(LinkedPlaneConduit, self).__init__()
        self.document_serial = int(document_serial)
        self.states = states
        self.display_state = display_state
        self._sources = {}
        self._previews = {}
        self._drawing_child = False
        self._active_command = None

    def _matches(self, event):
        doc = getattr(event, "RhinoDoc", None)
        return (
            doc is not None
            and int(doc.RuntimeSerialNumber) == self.document_serial
        )

    def _crosshair_size(self):
        from tack import plane_link

        doc = Rhino.RhinoDoc.FromRuntimeSerialNumber(self.document_serial)
        return plane_link.crosshair_size(doc)

    def _crosshair_thickness(self):
        from tack import plane_link

        doc = Rhino.RhinoDoc.FromRuntimeSerialNumber(self.document_serial)
        return plane_link.crosshair_thickness(doc)

    def _crosshair_states(self):
        from tack import plane_link

        items = list(self.states.items())
        doc = Rhino.RhinoDoc.FromRuntimeSerialNumber(self.document_serial)
        if doc is None or not plane_link.show_selected_tacks_only(doc):
            return items
        selected = plane_link.selected_link_ids(doc)
        return [
            (link_id, state)
            for link_id, state in items
            if any(utils.same_id(link_id, saved_id) for saved_id in selected)
        ]

    def _object_geometry(self, obj):
        if obj is None or obj.Geometry is None:
            return None
        geometry = obj.Geometry
        transform = _dynamic_transform(obj)
        if transform is None:
            for preview in self._previews.values():
                if utils.same_id(preview["child"].Id, obj.Id):
                    transform = preview["transform"]
                    break
        if transform is None:
            return geometry
        geometry = geometry.Duplicate()
        if geometry is None or not geometry.Transform(transform):
            return obj.Geometry
        return geometry

    def _selected_geometry(self):
        from tack import plane_link

        doc = Rhino.RhinoDoc.FromRuntimeSerialNumber(self.document_serial)
        if doc is None:
            return None
        return self._object_geometry(
            utils.find_object(doc, plane_link.selected_object_id(doc))
        )

    def _selected_tack_geometries(self):
        from tack import plane_link

        doc = Rhino.RhinoDoc.FromRuntimeSerialNumber(self.document_serial)
        if doc is None:
            return None
        selected_link_id = plane_link.selected_tack_id(doc)
        state = next(
            (
                state
                for link_id, state in self.states.items()
                if utils.same_id(link_id, selected_link_id)
            ),
            None,
        )
        if state is None:
            return None
        return (
            self._object_geometry(utils.find_object(doc, state["parent_id"])),
            self._object_geometry(utils.find_object(doc, state["child_id"])),
        )

    def _capture(self, doc, state):
        link = state["link"]
        parent = utils.find_object(doc, state["parent_id"])
        child = utils.find_object(doc, state["child_id"])
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
            "state": state,
        }

    def _source_for(self, doc, state):
        link_id = state["link_id"]
        parent = utils.find_object(doc, state["parent_id"])
        child = utils.find_object(doc, state["child_id"])
        if parent is None or child is None:
            return None
        source = self._sources.get(link_id)
        if (
            source is not None
            and source["parent_serial"] == int(parent.RuntimeSerialNumber)
            and source["child_serial"] == int(child.RuntimeSerialNumber)
        ):
            return source
        source = self._capture(doc, state)
        if source is not None:
            self._sources[link_id] = source
        return source

    def clear_preview(self):
        for preview in self._previews.values():
            state = preview["state"]
            state["dynamic_preview_active"] = False
        self._sources.clear()
        self._previews.clear()

    def command_began(self, command_name):
        self._active_command = str(command_name or "").lower().lstrip("_")

    def command_ended(self):
        self._active_command = None
        self.clear_preview()

    def _preview_allowed(self):
        if self._active_command not in ("drag", "move", "rotate", "rotate3d"):
            return False
        # Rhino's live command prompt updates as built-in Copy options change.
        # Suppress Tack's movement preview while Rhino is previewing a copy.
        prompt = str(Rhino.RhinoApp.CommandPrompt or "")
        return _COPY_ENABLED_PATTERN.search(prompt) is None

    def _update(self, doc):
        for preview in self._previews.values():
            preview["state"]["dynamic_preview_active"] = False

        states = [
            state
            for state in self.states.values()
            if not state.get("busy") and not state.get("broken")
        ]
        if not self._preview_allowed():
            self._sources.clear()
            self._previews = {}
            return

        transforms = {}
        direct_dynamic_objects = set()
        for state in states:
            for role in ("parent", "child"):
                obj = utils.find_object(doc, state[role + "_id"])
                dynamic_transform = _dynamic_transform(obj)
                if dynamic_transform is None:
                    continue
                object_key = str(obj.Id).lower()
                direct_dynamic_objects.add(object_key)
                if role == "parent":
                    transforms[object_key] = dynamic_transform

        previews = {}
        for _ in range(len(states) + 1):
            added_transform = False
            for state in states:
                parent = utils.find_object(doc, state["parent_id"])
                child = utils.find_object(doc, state["child_id"])
                if parent is None or child is None:
                    continue
                source = self._source_for(doc, state)
                if source is None:
                    continue

                parent_transform = transforms.get(str(parent.Id).lower())
                inherit_only = source["mode"] == "inherit_only"
                child_is_directly_dynamic = (
                    str(child.Id).lower() in direct_dynamic_objects
                )
                # Copy previews every selected object natively. If both Tack
                # endpoints are selected, do not add a redundant linked-child
                # preview over Rhino's parent-and-child copy preview.
                if parent_transform is not None and child_is_directly_dynamic:
                    continue
                if parent_transform is not None:
                    live_parent_plane = Rhino.Geometry.Plane(source["parent_plane"])
                    live_parent_plane.Transform(parent_transform)
                    if not source["rotation"]:
                        live_parent_plane = Rhino.Geometry.Plane(
                            live_parent_plane.Origin,
                            source["parent_plane"].XAxis,
                            source["parent_plane"].YAxis,
                        )
                    live_child_plane = Rhino.Geometry.Plane(source["child_plane"])
                    if inherit_only:
                        from tack import plane_link

                        target_child_plane = plane_link.inherit_target_child_plane(
                            live_parent_plane,
                            source["state"]["link"]["current_transform"],
                        )
                        if target_child_plane is None:
                            continue
                        target_child_plane = constrained_target_child_plane(
                            target_child_plane,
                            live_child_plane,
                            source["translation"],
                            source["rotation"],
                        )
                    else:
                        target_child_plane = linked_target_child_plane(
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
                else:
                    continue

                previews[state["link_id"]] = {
                    "child": child,
                    "state": state,
                    "parent_plane": live_parent_plane,
                    "child_plane": target_child_plane,
                    "transform": preview_transform,
                    "draw_child": not child_is_directly_dynamic,
                }
                state["dynamic_preview_active"] = True

                child_key = str(child.Id).lower()
                if (
                    child_key not in transforms
                    and child_key not in direct_dynamic_objects
                ):
                    transforms[child_key] = preview_transform
                    added_transform = True
            if not added_transform:
                break

        self._previews = previews
        if not previews:
            self._sources.clear()

    def PreDrawObjects(self, event):
        if self._matches(event):
            self._update(event.RhinoDoc)

    def PreDrawObject(self, event):
        if not self._matches(event) or self._drawing_child:
            return
        obj = event.RhinoObject
        if obj is None:
            return
        if any(
            preview["draw_child"]
            and utils.same_id(obj.Id, preview["child"].Id)
            for preview in self._previews.values()
        ):
            event.DrawObject = False

    def CalculateBoundingBox(self, event):
        if not self._matches(event):
            return
        if self.display_state["enabled"]:
            for link_id, state in self._crosshair_states():
                preview = self._previews.get(link_id)
                parent_plane = (
                    preview.get("parent_plane")
                    if preview is not None
                    else state.get("plane")
                )
                planes = (parent_plane,)
                if state["link"].get("mode", "attached") == "inherit_only":
                    child_plane = (
                        preview.get("child_plane")
                        if preview is not None
                        else state.get("child_plane")
                    )
                    planes = (parent_plane, child_plane)
                for plane in planes:
                    if not state.get("broken") and plane is not None:
                        event.IncludeBoundingBox(
                            analytic_plane.bounding_box(
                                plane,
                                self._crosshair_size(),
                            )
                        )

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
            event.IncludeBoundingBox(
                Rhino.Geometry.BoundingBox(points + transformed)
            )

    def PostDrawObjects(self, event):
        if not self._matches(event):
            return
        for preview in self._previews.values():
            if not preview["draw_child"]:
                continue
            child = preview["child"]
            if child is None or child.Geometry is None:
                continue
            _draw_locked_wireframe(event.Display, child.Geometry)
            self._drawing_child = True
            try:
                event.Display.DrawObject(child, preview["transform"])
            finally:
                self._drawing_child = False

        if not self.display_state["enabled"]:
            return
        selected_tack_geometries = self._selected_tack_geometries()
        selected_geometry = self._selected_geometry()
        if selected_tack_geometries is None and selected_geometry is None:
            return
        previous_z_bias = event.Display.ZBiasMode
        try:
            event.Display.ZBiasMode = Rhino.Display.ZBiasMode.TowardsCamera
            if selected_tack_geometries is not None:
                parent_geometry, child_geometry = selected_tack_geometries
                if parent_geometry is not None:
                    _draw_wireframe(
                        event.Display,
                        parent_geometry,
                        analytic_plane.CROSSHAIR_COLOR,
                        TREE_SELECTION_WIRE_THICKNESS,
                    )
                if child_geometry is not None:
                    _draw_wireframe(
                        event.Display,
                        child_geometry,
                        System.Drawing.Color.Red,
                        TREE_SELECTION_WIRE_THICKNESS,
                    )
            else:
                _draw_wireframe(
                    event.Display,
                    selected_geometry,
                    analytic_plane.CROSSHAIR_COLOR,
                    TREE_SELECTION_WIRE_THICKNESS,
                )
        finally:
            event.Display.ZBiasMode = previous_z_bias

    def DrawOverlay(self, event):
        if not self._matches(event) or not self.display_state["enabled"]:
            return
        for link_id, state in self._crosshair_states():
            preview = self._previews.get(link_id)
            parent_plane = (
                preview.get("parent_plane")
                if preview is not None
                else state.get("plane")
            )
            if state["link"].get("mode", "attached") == "inherit_only":
                child_plane = (
                    preview.get("child_plane")
                    if preview is not None
                    else state.get("child_plane")
                )
                if parent_plane is None or child_plane is None:
                    continue
                for plane in (parent_plane, child_plane):
                    analytic_plane.draw_preview(
                        event.Display,
                        plane,
                        self._crosshair_size(),
                        self._crosshair_thickness(),
                    )
            elif parent_plane is not None:
                analytic_plane.draw_preview(
                    event.Display,
                    parent_plane,
                    self._crosshair_size(),
                    self._crosshair_thickness(),
                )

    def DrawForeground(self, event):
        if not self._matches(event) or not self.display_state["enabled"]:
            return
        for link_id, state in self._crosshair_states():
            if state["link"].get("mode", "attached") != "inherit_only":
                continue
            preview = self._previews.get(link_id)
            parent_plane = (
                preview.get("parent_plane")
                if preview is not None
                else state.get("plane")
            )
            child_plane = (
                preview.get("child_plane")
                if preview is not None
                else state.get("child_plane")
            )
            if parent_plane is None or child_plane is None:
                continue
            _draw_dotted_line(
                event.Display,
                parent_plane.Origin,
                child_plane.Origin,
                analytic_plane.CROSSHAIR_COLOR,
                2,
                self._crosshair_size() / 20.0,
            )
