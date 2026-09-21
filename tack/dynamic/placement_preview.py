"""Dynamic child-placement preview used while adding a Tack."""

import Rhino

from tack.core.objects import same_id
from tack.display.drawing import draw_locked_wireframe, draw_transformed_object
from tack.links.transforms import constrained_plane_transform


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
        super().__init__()
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
        if obj is not None and same_id(obj.Id, self.child.Id):
            event.DrawObject = False

    def PostDrawObjects(self, event):
        if self.child is None or self.child.Geometry is None:
            return
        draw_locked_wireframe(event.Display, self.child.Geometry)
        self._drawing_child = True
        try:
            draw_transformed_object(
                event.Display,
                self.child,
                self.transform,
            )
        finally:
            self._drawing_child = False
