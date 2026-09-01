"""Live child preview while a native command drags a link parent.

Polls ``RhinoObject.GetDynamicTransform()`` every redraw frame (the only
moment Rhino exposes an in-progress Move/Rotate transform; it is gone by
``EndCommand``). For each dragged parent the child's target transform is
computed analytically from the saved plane definitions and drawn as a ghost
without mutating the document. The committing update still belongs to
``plane_link.EndCommandHandler`` so undo stays a single native record.

Pattern proven on the ``ondel-experimentation`` branch (commit 89748e5).
"""

import Rhino
import scriptcontext as sc

from tack import plane_link_preview
from tack import three_point_plane
from tack import utils


CONDUIT_KEY = "Tack.AnalyticPlaneLink.DynamicConduit"


def _dynamic_transform(rhino_object):
    """Return Rhino's in-progress drag transform, or None."""
    if rhino_object is None:
        return None
    try:
        result = rhino_object.GetDynamicTransform()
        available = bool(result[0])
        transform = result[1]
    except Exception:
        return None
    if not available or transform is None or transform.IsIdentity:
        return None
    return transform


class PlaneLinkDynamicConduit(Rhino.Display.DisplayConduit):
    def __init__(self):
        super(PlaneLinkDynamicConduit, self).__init__()
        # link_id -> {"parent_serial", "child_serial", "parent_plane",
        #             "child_plane", "inverted", "state"}
        self._sources = {}
        # link_id -> {"child", "transform", "rest_plane", "live_plane"}
        self._previews = {}
        self._drawing_child = False

    def _capture(self, doc, state):
        link = state["link"]
        parent = utils.find_object(doc, state["parent_id"])
        child = utils.find_object(doc, state["child_id"])
        if parent is None or child is None:
            return None
        parent_plane = three_point_plane.resolve_definition(
            doc,
            link["parent_plane"],
        )
        child_plane = three_point_plane.resolve_definition(
            doc,
            link["child_plane"],
        )
        if parent_plane is None or child_plane is None:
            return None
        return {
            "parent_serial": int(parent.RuntimeSerialNumber),
            "child_serial": int(child.RuntimeSerialNumber),
            "parent_plane": parent_plane,
            "child_plane": child_plane,
            "inverted": bool(link["inverted"]),
            "state": state,
        }

    def _source_for(self, doc, state):
        link_id = state["link_id"]
        parent = utils.find_object(doc, state["parent_id"])
        child = utils.find_object(doc, state["child_id"])
        if parent is None or child is None:
            self._sources.pop(link_id, None)
            return None
        source = self._sources.get(link_id)
        if (
            source is not None
            and source["parent_serial"] == int(parent.RuntimeSerialNumber)
            and source["child_serial"] == int(child.RuntimeSerialNumber)
        ):
            return source
        source = self._capture(doc, state)
        if source is None:
            self._sources.pop(link_id, None)
            return None
        self._sources[link_id] = source
        return source

    def command_ended(self, doc):
        for source in self._sources.values():
            state = source["state"]
            state["dynamic_preview_active"] = False
            if state.get("broken") is not True and source.get("parent_plane"):
                state["origin"] = Rhino.Geometry.Point3d(
                    source["parent_plane"].Origin
                )
                state["plane"] = Rhino.Geometry.Plane(source["parent_plane"])
        self._clear(doc)

    def _clear(self, doc):
        for preview in self._previews.values():
            state = preview.get("state")
            if state is not None:
                state["dynamic_preview_active"] = False
                if not state.get("broken"):
                    rest_plane = preview.get("rest_plane")
                    if rest_plane is not None:
                        state["origin"] = Rhino.Geometry.Point3d(rest_plane.Origin)
                        state["plane"] = Rhino.Geometry.Plane(rest_plane)
        self._sources = {}
        self._previews = {}

    def _update(self, doc):
        from tack import plane_link

        if doc is None or plane_link._solving:
            self._clear(doc)
            return
        states = plane_link.states(doc, create=False)
        if not states:
            if self._previews:
                self._clear(doc)
            return

        for preview in self._previews.values():
            state = preview.get("state")
            if state is not None:
                state["dynamic_preview_active"] = False

        previews = {}
        for state in states.values():
            if state.get("busy") or state.get("broken"):
                continue
            parent = utils.find_object(doc, state["parent_id"])
            transform = _dynamic_transform(parent)
            if transform is None:
                continue
            source = self._source_for(doc, state)
            if source is None:
                continue
            child = utils.find_object(doc, state["child_id"])
            if child is None:
                continue
            live_parent_plane = Rhino.Geometry.Plane(source["parent_plane"])
            live_parent_plane.Transform(transform)
            correction = plane_link_preview.plane_to_plane_transform(
                live_parent_plane,
                source["child_plane"],
                source["inverted"],
            )
            previews[state["link_id"]] = {
                "child": child,
                "state": state,
                "transform": correction,
                "rest_plane": Rhino.Geometry.Plane(source["parent_plane"]),
                "live_plane": Rhino.Geometry.Plane(live_parent_plane),
            }
            state["dynamic_preview_active"] = True
            state["origin"] = Rhino.Geometry.Point3d(live_parent_plane.Origin)
            state["plane"] = Rhino.Geometry.Plane(live_parent_plane)

        self._previews = previews
        if not previews:
            self._sources = {}

    def PreDrawObjects(self, event):
        self._update(event.RhinoDoc)

    def PreDrawObject(self, event):
        if self._drawing_child or not self._previews:
            return
        obj = event.RhinoObject
        if obj is None:
            return
        for preview in self._previews.values():
            if utils.same_id(obj.Id, preview["child"].Id):
                event.DrawObject = False
                return

    def CalculateBoundingBox(self, event):
        for preview in self._previews.values():
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
            plane = preview["live_plane"]
            event.IncludeBoundingBox(
                Rhino.Geometry.BoundingBox(
                    three_point_plane.plane_border(
                        plane.Origin,
                        plane.XAxis,
                        plane.YAxis,
                        three_point_plane.preview_half_extent(),
                    )
                )
            )

    def PostDrawObjects(self, event):
        for preview in self._previews.values():
            child = preview["child"]
            if child is None or child.Geometry is None:
                continue
            plane_link_preview._draw_locked_wireframe(
                event.Display,
                child.Geometry,
            )
            self._drawing_child = True
            try:
                event.Display.DrawObject(child, preview["transform"])
            finally:
                self._drawing_child = False

    def DrawOverlay(self, event):
        for preview in self._previews.values():
            plane = preview["live_plane"]
            three_point_plane.draw_preview(
                event.Display,
                plane.Origin,
                plane.XAxis,
                plane.YAxis,
                three_point_plane.preview_half_extent(),
            )


def _conduit():
    return sc.sticky.get(CONDUIT_KEY)


def ensure():
    conduit = _conduit()
    if conduit is None:
        conduit = PlaneLinkDynamicConduit()
        sc.sticky[CONDUIT_KEY] = conduit
    conduit.Enabled = True


def disable():
    conduit = sc.sticky.pop(CONDUIT_KEY, None)
    if conduit is not None:
        conduit.Enabled = False


def command_ended(doc):
    conduit = _conduit()
    if conduit is not None:
        conduit.command_ended(doc)
