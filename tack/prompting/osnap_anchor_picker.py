"""Reusable OSnap picker for analytic anchor definitions."""

import Rhino
import System.Drawing
import rhinoscriptsyntax as rs
from Rhino.Commands import Result

from tack import anchor_definitions


class BoundingBoxCenterConduit(Rhino.Display.DisplayConduit):
    def __init__(self, point):
        super(BoundingBoxCenterConduit, self).__init__()
        self.point = point

    def DrawForeground(self, event):
        event.Display.DrawPoint(
            self.point,
            Rhino.Display.PointStyle.Circle,
            4,
            System.Drawing.Color.Black,
        )
        event.Display.DrawPoint(
            self.point,
            Rhino.Display.PointStyle.Circle,
            2,
            System.Drawing.Color.White,
        )


def select_object(doc, prompt="Select object to anchor"):
    """Select an object whose geometry has a valid bounding box."""
    while True:
        result, obj_ref = Rhino.Input.RhinoGet.GetOneObject(
            prompt,
            False,
            Rhino.DocObjects.ObjectType.AnyObject,
        )
        if result != Result.Success or obj_ref is None:
            return None
        obj = obj_ref.Object()
        if obj is not None and anchor_definitions.bounding_box_center(obj) is not None:
            return obj
        print("Select an object with a valid bounding box.")


def _lock_other_objects(doc, target_id):
    locked_ids = []
    for candidate in doc.Objects:
        if candidate is None or str(candidate.Id).lower() == str(target_id).lower():
            continue
        try:
            if not rs.IsObjectLocked(candidate.Id) and rs.LockObject(candidate.Id):
                locked_ids.append(candidate.Id)
        except Exception:
            pass
    return locked_ids


def _unlock_objects(object_ids):
    for object_id in object_ids:
        try:
            rs.UnlockObject(object_id)
        except Exception:
            pass


class AnchorPickSession:
    """Constrain one or more analytic anchor picks to a target object."""

    def __init__(self, doc, obj):
        self.doc = doc
        self.obj = obj
        self.tolerance = max(doc.ModelAbsoluteTolerance, 1e-7)
        self.bounding_box_center = anchor_definitions.bounding_box_center(obj)
        if self.bounding_box_center is None:
            raise ValueError("The target object has no valid bounding box center")
        self._locked_ids = []
        self._osnap_was_enabled = None
        self._project_was_enabled = None
        self._center_conduit = BoundingBoxCenterConduit(self.bounding_box_center)

    def __enter__(self):
        self._locked_ids = _lock_other_objects(self.doc, self.obj.Id)
        try:
            settings = Rhino.ApplicationSettings.ModelAidSettings
            self._osnap_was_enabled = settings.Osnap
            self._project_was_enabled = settings.ProjectSnapToCPlane
            settings.Osnap = True
            settings.ProjectSnapToCPlane = False
            self._center_conduit.Enabled = True
            self.doc.Views.Redraw()
            return self
        except Exception:
            self.__exit__(None, None, None)
            raise

    def __exit__(self, exc_type, exc_value, traceback_value):
        self._center_conduit.Enabled = False
        settings = Rhino.ApplicationSettings.ModelAidSettings
        if self._osnap_was_enabled is not None:
            settings.Osnap = self._osnap_was_enabled
        if self._project_was_enabled is not None:
            settings.ProjectSnapToCPlane = self._project_was_enabled
        _unlock_objects(self._locked_ids)
        self._locked_ids = []
        self.doc.Views.Redraw()
        return False

    def pick(self, prompt, getter_factory=None, preview_factory=None):
        """Return ``(resolved_point, definition)`` or ``None`` on cancel.

        ``getter_factory`` can provide a custom ``GetPoint`` subclass.
        ``preview_factory`` receives that getter and can return an additional
        display conduit, allowing callers to add interaction-specific previews.
        """
        while True:
            getter = (
                getter_factory()
                if getter_factory is not None
                else Rhino.Input.Custom.GetPoint()
            )
            getter.SetCommandPrompt(prompt)
            getter.AcceptNothing(False)
            getter.PermitObjectSnap(True)
            getter.AddConstructionPoint(self.bounding_box_center)
            getter.AddSnapPoint(self.bounding_box_center)
            getter.FullFrameRedrawDuringGet = True

            preview = (
                preview_factory(getter)
                if preview_factory is not None
                else None
            )
            if preview is not None:
                preview.Enabled = True
            self.doc.Views.Redraw()
            try:
                if getter.Get() != Rhino.Input.GetResult.Point:
                    return None

                point = getter.Point()
                if point.DistanceTo(self.bounding_box_center) <= self.tolerance:
                    return point, {"type": anchor_definitions.BOUNDING_BOX_CENTER}

                obj_ref = getter.PointOnObject()
                if (
                    obj_ref is None
                    or str(obj_ref.ObjectId).lower() != str(self.obj.Id).lower()
                ):
                    print(
                        "Pick an object snap or bounding-box center "
                        "on the selected object."
                    )
                    continue

                derived = anchor_definitions.derive(
                    obj_ref,
                    point,
                    getter.OsnapEventType,
                    self.tolerance,
                )
                if derived is not None:
                    definition, resolved_point = derived
                    return resolved_point, definition

                print(
                    "That snap cannot be derived unambiguously. "
                    "Pick another snap."
                )
            finally:
                if preview is not None:
                    preview.Enabled = False
                self.doc.Views.Redraw()
