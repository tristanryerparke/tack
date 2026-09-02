"""Display conduits for analytic plane picking and live Tack links."""

import Rhino

from tack import analytic_plane
from tack import utils


LOCKED_WIRE_THICKNESS = 1


def inverted_plane(plane):
    return Rhino.Geometry.Plane(plane.Origin, plane.XAxis, -plane.YAxis)


def plane_to_plane_transform(parent_plane, child_plane, inverted=False):
    source = inverted_plane(child_plane) if inverted else child_plane
    return Rhino.Geometry.Transform.PlaneToPlane(source, parent_plane)


def _draw_bounding_box(display, geometry, color):
    bounding_box = geometry.GetBoundingBox(True)
    if not bounding_box.IsValid:
        return
    for line in Rhino.Geometry.Box(bounding_box).GetEdges():
        display.DrawLine(line, color, LOCKED_WIRE_THICKNESS)


def _draw_locked_wireframe(display, geometry):
    color = Rhino.ApplicationSettings.AppearanceSettings.LockedObjectColor
    if isinstance(geometry, Rhino.Geometry.Brep):
        display.DrawBrepWires(geometry, color, 1)
    elif isinstance(geometry, Rhino.Geometry.Extrusion):
        display.DrawExtrusionWires(geometry, color, 1)
    elif isinstance(geometry, Rhino.Geometry.Mesh):
        display.DrawMeshWires(geometry, color, LOCKED_WIRE_THICKNESS)
    elif isinstance(geometry, Rhino.Geometry.Curve):
        display.DrawCurve(geometry, color, LOCKED_WIRE_THICKNESS)
    elif isinstance(geometry, Rhino.Geometry.SubD):
        display.DrawSubDWires(geometry, color, float(LOCKED_WIRE_THICKNESS))
    elif isinstance(geometry, Rhino.Geometry.Surface):
        display.DrawSurface(geometry, color, 1)
    elif isinstance(geometry, Rhino.Geometry.Point):
        display.DrawPoint(geometry.Location, color)
    elif isinstance(geometry, Rhino.Geometry.PointCloud):
        display.DrawPointCloud(geometry, 2, color)
    else:
        _draw_bounding_box(display, geometry, color)


class PlaneDisplayConduit(Rhino.Display.DisplayConduit):
    def __init__(self, plane):
        super(PlaneDisplayConduit, self).__init__()
        self.plane = plane

    def CalculateBoundingBox(self, event):
        event.IncludeBoundingBox(analytic_plane.bounding_box(self.plane))

    def DrawOverlay(self, event):
        analytic_plane.draw_preview(event.Display, self.plane)


class TransformPreviewConduit(Rhino.Display.DisplayConduit):
    def __init__(self, child, parent_plane, child_plane, inverted=False):
        super(TransformPreviewConduit, self).__init__()
        self.child = child
        self.parent_plane = parent_plane
        self.child_plane = child_plane
        self.inverted = bool(inverted)
        self._drawing_child = False

    @property
    def transform(self):
        return plane_to_plane_transform(
            self.parent_plane,
            self.child_plane,
            self.inverted,
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

    def _matches(self, event):
        doc = getattr(event, "RhinoDoc", None)
        return (
            doc is not None
            and int(doc.RuntimeSerialNumber) == self.document_serial
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

    def command_ended(self):
        self.clear_preview()

    def _update(self, doc):
        for preview in self._previews.values():
            preview["state"]["dynamic_preview_active"] = False

        previews = {}
        for state in self.states.values():
            if state.get("busy") or state.get("broken"):
                continue
            parent = utils.find_object(doc, state["parent_id"])
            dynamic_transform = _dynamic_transform(parent)
            if dynamic_transform is None:
                continue
            source = self._source_for(doc, state)
            child = utils.find_object(doc, state["child_id"])
            if source is None or child is None:
                continue

            live_parent_plane = Rhino.Geometry.Plane(source["parent_plane"])
            live_parent_plane.Transform(dynamic_transform)
            previews[state["link_id"]] = {
                "child": child,
                "state": state,
                "plane": live_parent_plane,
                "transform": plane_to_plane_transform(
                    live_parent_plane,
                    source["child_plane"],
                    source["inverted"],
                ),
            }
            state["dynamic_preview_active"] = True

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
            utils.same_id(obj.Id, preview["child"].Id)
            for preview in self._previews.values()
        ):
            event.DrawObject = False

    def CalculateBoundingBox(self, event):
        if not self._matches(event):
            return
        if self.display_state["enabled"]:
            preview_planes = {
                link_id: preview["plane"]
                for link_id, preview in self._previews.items()
            }
            for link_id, state in self.states.items():
                plane = preview_planes.get(link_id, state.get("plane"))
                if not state.get("broken") and plane is not None:
                    event.IncludeBoundingBox(analytic_plane.bounding_box(plane))

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

    def PostDrawObjects(self, event):
        if not self._matches(event):
            return
        for preview in self._previews.values():
            child = preview["child"]
            if child is None or child.Geometry is None:
                continue
            _draw_locked_wireframe(event.Display, child.Geometry)
            self._drawing_child = True
            try:
                event.Display.DrawObject(child, preview["transform"])
            finally:
                self._drawing_child = False

    def DrawOverlay(self, event):
        if not self._matches(event) or not self.display_state["enabled"]:
            return
        preview_planes = {
            link_id: preview["plane"]
            for link_id, preview in self._previews.items()
        }
        for link_id, state in self.states.items():
            plane = preview_planes.get(link_id, state.get("plane"))
            if not state.get("broken") and plane is not None:
                analytic_plane.draw_preview(event.Display, plane)
