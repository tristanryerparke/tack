"""Persistent Tack crosshairs, selection highlights, and preview host conduit."""

import Rhino
import System.Drawing

from tack.anchors import analytic_plane
from tack.core.objects import find_object, same_id
from tack.display.drawing import draw_dotted_line, draw_wireframe
from tack.dynamic.native_preview import NativeTransformPreview

TREE_SELECTION_WIRE_THICKNESS = 4


class LinkedPlaneConduit(Rhino.Display.DisplayConduit):
    """Shared cross-document persistent planes and native-transform previews."""

    def __init__(self):
        super().__init__()
        self.dynamics = {}
        self._active_command = None
        self._frame_selection = {}

    def _context(self, event):
        from tack.links import runtime

        doc = getattr(event, "RhinoDoc", None)
        if doc is None:
            return None
        states = runtime.states_for(doc)
        if states is None:
            return None
        serial = int(doc.RuntimeSerialNumber)
        return {
            "doc": doc,
            "serial": serial,
            "states": states,
            "enabled": runtime.display_enabled(doc),
            "dynamic": self.dynamic_for(serial, states),
        }

    def dynamic_for(self, document_serial, states):
        dynamic = self.dynamics.get(document_serial)
        if dynamic is None:
            dynamic = NativeTransformPreview(document_serial, states)
            if self._active_command is not None:
                dynamic.command_began(self._active_command)
            self.dynamics[document_serial] = dynamic
        else:
            dynamic.states = states
        return dynamic

    def forget_document(self, document_serial):
        dynamic = self.dynamics.pop(int(document_serial), None)
        if dynamic is not None:
            dynamic.clear()
        self._frame_selection.pop(int(document_serial), None)

    def _crosshair_size(self, doc):
        from tack.links import runtime

        return runtime.crosshair_size(doc)

    def _crosshair_thickness(self, doc):
        from tack.links import runtime

        return runtime.crosshair_thickness(doc)

    def _crosshair_states(self, doc, states):
        from tack.links import runtime

        items = list(states.items())
        if not runtime.show_selected_tacks_only(doc):
            return items
        selected = runtime.selected_link_ids(doc)
        return [
            (link_id, link_state)
            for link_id, link_state in items
            if any(same_id(link_id, saved_id) for saved_id in selected)
        ]

    def _selected_geometry(self, context):
        from tack.links import runtime

        return context["dynamic"].object_geometry(
            find_object(context["doc"], runtime.selected_object_id(context["doc"]))
        )

    def _selected_tack_state(self, doc, states):
        from tack.links import runtime

        selected_link_id = runtime.selected_tack_id(doc)
        return next(
            (
                link_state
                for link_id, link_state in states.items()
                if same_id(link_id, selected_link_id)
            ),
            None,
        )

    def _selected_object_ids(self, context):
        from tack.links import runtime

        if not context["enabled"] or not runtime.highlight_selected_objects(context["doc"]):
            return ()
        doc = context["doc"]
        selected_object_id = runtime.selected_object_id(doc)
        if selected_object_id is not None:
            return (selected_object_id,)
        link_state = self._selected_tack_state(doc, context["states"])
        return () if link_state is None else (link_state.parent_id, link_state.child_id)

    def _selected_tack_geometries(self, context):
        doc = context["doc"]
        link_state = self._selected_tack_state(doc, context["states"])
        if link_state is None:
            return None
        return (
            context["dynamic"].object_geometry(find_object(doc, link_state.parent_id)),
            context["dynamic"].object_geometry(find_object(doc, link_state.child_id)),
        )

    def clear_preview(self):
        for dynamic in self.dynamics.values():
            dynamic.clear()
        self.dynamics.clear()
        self._frame_selection.clear()

    def command_began(self, command_name):
        self._active_command = str(command_name or "").lower().lstrip("_")
        for dynamic in self.dynamics.values():
            dynamic.command_began(self._active_command)

    def command_ended(self):
        self._active_command = None
        for dynamic in self.dynamics.values():
            dynamic.command_ended()

    def PreDrawObjects(self, event):
        context = self._context(event)
        if context is None:
            return
        self._frame_selection[context["serial"]] = self._selected_object_ids(context)
        context["dynamic"].update(context["doc"])

    def PreDrawObject(self, event):
        context = self._context(event)
        if context is None:
            return
        obj = event.RhinoObject
        if context["dynamic"].suppresses_object(obj):
            event.DrawObject = False
            return
        if (
            obj is not None
            and event.Display.DrawingWires
            and any(
                same_id(obj.Id, selected_id)
                for selected_id in self._frame_selection.get(context["serial"], ())
            )
        ):
            event.DrawObject = False

    def CalculateBoundingBox(self, event):
        context = self._context(event)
        if context is None:
            return
        doc = context["doc"]
        dynamic = context["dynamic"]
        if context["enabled"]:
            for link_id, link_state in self._crosshair_states(doc, context["states"]):
                preview = dynamic.preview_for(link_id)
                parent_plane = (
                    preview.get("parent_plane") if preview is not None else link_state.parent_plane
                )
                child_plane = (
                    preview.get("child_plane") if preview is not None else link_state.child_plane
                )
                for plane in (parent_plane, child_plane):
                    if plane is not None:
                        event.IncludeBoundingBox(
                            analytic_plane.bounding_box(plane, self._crosshair_size(doc))
                        )
        dynamic.include_bounding_boxes(event)

    def PostDrawObjects(self, event):
        context = self._context(event)
        if context is None:
            return
        context["dynamic"].draw_objects(event)

        if not context["enabled"] or not self._frame_selection.get(context["serial"]):
            return
        selected_tack_geometries = self._selected_tack_geometries(context)
        selected_geometry = self._selected_geometry(context)
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
        context = self._context(event)
        if context is None or not context["enabled"]:
            return
        doc = context["doc"]
        dynamic = context["dynamic"]
        size = self._crosshair_size(doc)
        thickness = self._crosshair_thickness(doc)
        for link_id, link_state in self._crosshair_states(doc, context["states"]):
            preview = dynamic.preview_for(link_id)
            parent_plane = preview.get("parent_plane") if preview else link_state.parent_plane
            child_plane = preview.get("child_plane") if preview else link_state.child_plane
            for plane in (parent_plane, child_plane):
                if plane is not None:
                    analytic_plane.draw_preview(event.Display, plane, size, thickness)

    def DrawForeground(self, event):
        context = self._context(event)
        if context is None or not context["enabled"]:
            return
        doc = context["doc"]
        dynamic = context["dynamic"]
        size = self._crosshair_size(doc)
        for link_id, link_state in self._crosshair_states(doc, context["states"]):
            preview = dynamic.preview_for(link_id)
            parent_plane = preview.get("parent_plane") if preview else link_state.parent_plane
            child_plane = preview.get("child_plane") if preview else link_state.child_plane
            if parent_plane is not None and child_plane is not None:
                draw_dotted_line(
                    event.Display,
                    parent_plane.Origin,
                    child_plane.Origin,
                    analytic_plane.CROSSHAIR_COLOR,
                    2,
                    size / 20.0,
                )
