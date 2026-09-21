"""Persistent Tack crosshairs, selection highlights, and preview host conduit."""

import Rhino
import System.Drawing

from tack.anchors import analytic_plane
from tack.core.objects import find_object, same_id
from tack.display.drawing import draw_dotted_line, draw_wireframe
from tack.dynamic.native_preview import NativeTransformPreview

TREE_SELECTION_WIRE_THICKNESS = 4


class LinkedPlaneConduit(Rhino.Display.DisplayConduit):
    """Document-scoped persistent planes and native-transform previews."""

    def __init__(self, document_serial, states, display_state):
        super().__init__()
        self.document_serial = int(document_serial)
        self.states = states
        self.display_state = display_state
        self.dynamic = NativeTransformPreview(document_serial, states)
        self._selected_ids = ()

    def _matches(self, event):
        doc = getattr(event, "RhinoDoc", None)
        return doc is not None and int(doc.RuntimeSerialNumber) == self.document_serial

    def _crosshair_size(self):
        from tack.links import runtime

        doc = Rhino.RhinoDoc.FromRuntimeSerialNumber(self.document_serial)
        return runtime.crosshair_size(doc)

    def _crosshair_thickness(self):
        from tack.links import runtime

        doc = Rhino.RhinoDoc.FromRuntimeSerialNumber(self.document_serial)
        return runtime.crosshair_thickness(doc)

    def _crosshair_states(self):
        from tack.links import runtime

        items = list(self.states.items())
        doc = Rhino.RhinoDoc.FromRuntimeSerialNumber(self.document_serial)
        if doc is None or not runtime.show_selected_tacks_only(doc):
            return items
        selected = runtime.selected_link_ids(doc)
        return [
            (link_id, link_state)
            for link_id, link_state in items
            if any(same_id(link_id, saved_id) for saved_id in selected)
        ]

    def _selected_geometry(self):
        from tack.links import runtime

        doc = Rhino.RhinoDoc.FromRuntimeSerialNumber(self.document_serial)
        if doc is None:
            return None
        return self.dynamic.object_geometry(
            find_object(doc, runtime.selected_object_id(doc))
        )

    def _selected_tack_state(self, doc):
        from tack.links import runtime

        selected_link_id = runtime.selected_tack_id(doc)
        return next(
            (
                link_state
                for link_id, link_state in self.states.items()
                if same_id(link_id, selected_link_id)
            ),
            None,
        )

    def _selected_object_ids(self):
        from tack.links import runtime

        if not self.display_state["enabled"]:
            return ()
        doc = Rhino.RhinoDoc.FromRuntimeSerialNumber(self.document_serial)
        if doc is None or not runtime.highlight_selected_objects(doc):
            return ()
        selected_object_id = runtime.selected_object_id(doc)
        if selected_object_id is not None:
            return (selected_object_id,)
        link_state = self._selected_tack_state(doc)
        if link_state is None:
            return ()
        return (link_state["parent_id"], link_state["child_id"])

    def _selected_tack_geometries(self):
        doc = Rhino.RhinoDoc.FromRuntimeSerialNumber(self.document_serial)
        if doc is None:
            return None
        link_state = self._selected_tack_state(doc)
        if link_state is None:
            return None
        return (
            self.dynamic.object_geometry(find_object(doc, link_state["parent_id"])),
            self.dynamic.object_geometry(find_object(doc, link_state["child_id"])),
        )

    def clear_preview(self):
        self.dynamic.clear()

    def command_began(self, command_name):
        self.dynamic.command_began(command_name)

    def command_ended(self):
        self.dynamic.command_ended()

    def PreDrawObjects(self, event):
        if self._matches(event):
            self._selected_ids = self._selected_object_ids()
            self.dynamic.update(event.RhinoDoc)

    def PreDrawObject(self, event):
        if not self._matches(event):
            return
        obj = event.RhinoObject
        if self.dynamic.suppresses_object(obj):
            event.DrawObject = False
            return
        if (
            obj is not None
            and event.Display.DrawingWires
            and any(same_id(obj.Id, selected_id) for selected_id in self._selected_ids)
        ):
            event.DrawObject = False

    def CalculateBoundingBox(self, event):
        if not self._matches(event):
            return
        if self.display_state["enabled"]:
            for link_id, link_state in self._crosshair_states():
                preview = self.dynamic.preview_for(link_id)
                parent_plane = (
                    preview.get("parent_plane")
                    if preview is not None
                    else link_state.get("plane")
                )
                planes = (parent_plane,)
                if link_state["link"].get("mode", "attached") == "inherit_only":
                    child_plane = (
                        preview.get("child_plane")
                        if preview is not None
                        else link_state.get("child_plane")
                    )
                    planes = (parent_plane, child_plane)
                for plane in planes:
                    if not link_state.get("broken") and plane is not None:
                        event.IncludeBoundingBox(
                            analytic_plane.bounding_box(
                                plane,
                                self._crosshair_size(),
                            )
                        )
        self.dynamic.include_bounding_boxes(event)

    def PostDrawObjects(self, event):
        if not self._matches(event):
            return
        self.dynamic.draw_objects(event)

        if not self.display_state["enabled"] or not self._selected_ids:
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
                    draw_wireframe(
                        event.Display,
                        parent_geometry,
                        System.Drawing.Color.Red,
                        TREE_SELECTION_WIRE_THICKNESS,
                    )
                if child_geometry is not None:
                    draw_wireframe(
                        event.Display,
                        child_geometry,
                        analytic_plane.CROSSHAIR_COLOR,
                        TREE_SELECTION_WIRE_THICKNESS,
                    )
            else:
                draw_wireframe(
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
        for link_id, link_state in self._crosshair_states():
            preview = self.dynamic.preview_for(link_id)
            parent_plane = (
                preview.get("parent_plane")
                if preview is not None
                else link_state.get("plane")
            )
            if link_state["link"].get("mode", "attached") == "inherit_only":
                child_plane = (
                    preview.get("child_plane")
                    if preview is not None
                    else link_state.get("child_plane")
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
        for link_id, link_state in self._crosshair_states():
            if link_state["link"].get("mode", "attached") != "inherit_only":
                continue
            preview = self.dynamic.preview_for(link_id)
            parent_plane = (
                preview.get("parent_plane")
                if preview is not None
                else link_state.get("plane")
            )
            child_plane = (
                preview.get("child_plane")
                if preview is not None
                else link_state.get("child_plane")
            )
            if parent_plane is None or child_plane is None:
                continue
            draw_dotted_line(
                event.Display,
                parent_plane.Origin,
                child_plane.Origin,
                analytic_plane.CROSSHAIR_COLOR,
                2,
                self._crosshair_size() / 20.0,
            )
