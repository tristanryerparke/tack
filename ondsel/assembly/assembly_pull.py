import System.Drawing

import Rhino
import rhinoscriptsyntax as rs
import scriptcontext as sc
from Rhino.Commands import Result

from ondsel.assembly import assembly_common
from ondsel.assembly import assembly_model


PREVIEW_COLOR = System.Drawing.Color.FromArgb(230, 80, 160, 220)
DRIVER_COLOR = System.Drawing.Color.FromArgb(255, 255, 190, 70)


class _AssemblyPreviewConduit(Rhino.Display.DisplayConduit):
    def __init__(self, source_geometries, source_poses):
        super(_AssemblyPreviewConduit, self).__init__()
        self.source_geometries = source_geometries
        self.source_poses = source_poses
        self.poses = dict(source_poses)
        self.driver_part_id = None
        self.preview_material = Rhino.Display.DisplayMaterial()
        self.preview_material.Diffuse = PREVIEW_COLOR
        self.driver_material = Rhino.Display.DisplayMaterial()
        self.driver_material.Diffuse = DRIVER_COLOR

    def update(self, poses, driver_part_id):
        self.poses = dict(poses)
        self.driver_part_id = driver_part_id

    def _preview_brep(self, object_id):
        geometry = self.source_geometries[object_id].Duplicate()
        source_pose = self.source_poses[object_id]
        target_pose = self.poses.get(object_id, source_pose)
        delta = assembly_model._pose_delta(source_pose, target_pose)
        geometry.Transform(delta)
        if isinstance(geometry, Rhino.Geometry.Brep):
            return geometry
        if hasattr(geometry, "ToBrep"):
            return geometry.ToBrep()
        return None

    def CalculateBoundingBox(self, event):
        for object_id in self.source_geometries:
            brep = self._preview_brep(object_id)
            if brep is not None:
                event.IncludeBoundingBox(brep.GetBoundingBox(True))

    def CalculateBoundingBoxZoomExtents(self, event):
        self.CalculateBoundingBox(event)

    def PostDrawObjects(self, event):
        for object_id in self.source_geometries:
            brep = self._preview_brep(object_id)
            if brep is None:
                continue
            material = (
                self.driver_material
                if object_id == self.driver_part_id
                else self.preview_material
            )
            event.Display.DrawBrepShaded(brep, material)


class _PullGetPoint(Rhino.Input.Custom.GetPoint):
    def __init__(self, update_callback, start_point):
        super(_PullGetPoint, self).__init__()
        self.update_callback = update_callback
        self.start_point = start_point
        self.last_point = None

    def _point_from_event(self, event):
        for name in ("Point", "CurrentPoint"):
            try:
                point = getattr(event, name)
                if callable(point):
                    point = point()
            except Exception:
                point = None
            if point is not None:
                return point
        try:
            point = self.Point
            return point() if callable(point) else point
        except Exception:
            return None

    def _update(self, point):
        if point is None:
            return
        if self.last_point is not None and self.last_point.DistanceTo(point) < 1e-5:
            return
        self.last_point = Rhino.Geometry.Point3d(point)
        self.update_callback(self.last_point)

    def OnMouseMove(self, event):
        super(_PullGetPoint, self).OnMouseMove(event)
        self._update(self._point_from_event(event))
        Rhino.RhinoDoc.ActiveDoc.Views.Redraw()

    def OnDynamicDraw(self, event):
        self._update(getattr(event, "CurrentPoint", None))
        super(_PullGetPoint, self).OnDynamicDraw(event)


def _tracked_part(doc, data, rhino_object):
    object_id = assembly_common.guid_string(rhino_object.Id)
    return data["parts"].get(object_id)


def _source_geometry(rhino_object):
    geometry = rhino_object.Geometry
    return geometry.Duplicate()


def _select_part(doc, data):
    getter = Rhino.Input.Custom.GetObject()
    getter.SetCommandPrompt("Select an assembly part to pull")
    getter.GeometryFilter = (
        Rhino.DocObjects.ObjectType.Brep
        | Rhino.DocObjects.ObjectType.Extrusion
        | Rhino.DocObjects.ObjectType.Surface
    )
    getter.SubObjectSelect = False
    getter.EnablePreSelect(True, True)
    getter.EnablePostSelect(True)
    if getter.Get() != Rhino.Input.GetResult.Object:
        return None
    rhino_object = getter.Object(0).Object()
    if rhino_object is None:
        return None
    part = _tracked_part(doc, data, rhino_object)
    if part is None:
        print("Select one of the tracked assembly parts.")
        return None
    return part


def _pull(doc, part, base_point):
    data = assembly_model.read_data(doc)
    part_id = part["object_id"]
    source_poses = {
        item["object_id"]: assembly_model._current_pose_from_home(doc, item)
        for item in data["parts"].values()
    }
    source_geometries = {}
    for item in data["parts"].values():
        object_id = item["object_id"]
        rhino_object = doc.Objects.FindId(assembly_common.parse_guid(object_id))
        if rhino_object is None:
            return Result.Failure
        source_geometries[object_id] = _source_geometry(rhino_object)

    state = {"poses": dict(source_poses), "error": None}
    conduit = _AssemblyPreviewConduit(source_geometries, source_poses)
    conduit.update(source_poses, part_id)
    def update_preview(point):
        driver_pose = assembly_model._copy_pose(source_poses[part_id])
        driver_pose["position"] = [
            start_value + point_value - start_value_point
            for start_value, point_value, start_value_point in zip(
                source_poses[part_id]["position"],
                assembly_common.point_tuple(point),
                assembly_common.point_tuple(base_point),
            )
        ]
        try:
            result = assembly_model.solve_and_propagate(
                doc,
                driver_part_id=part_id,
                driver_pose=driver_pose,
                apply=False,
            )
            state["poses"] = result["poses"]
            conduit.update(state["poses"], part_id)
        except Exception as error:
            state["error"] = error
            assembly_model._debug("pull preview solve failed: {}".format(error))

    assembly_model._set_command_busy(doc, True)
    try:
        conduit.Enabled = True
        doc.Views.Redraw()
        getter = _PullGetPoint(update_preview, base_point)
        getter.SetCommandPrompt("Move the constrained assembly; click to commit")
        getter.SetBasePoint(base_point, True)
        getter.AcceptNothing(False)
        getter.FullFrameRedrawDuringGet = True
        result = getter.Get()
        if result != Rhino.Input.GetResult.Point or state["error"] is not None:
            return Result.Cancel

        final_point = getter.Point
        if callable(final_point):
            final_point = final_point()
        update_preview(final_point)
        final_pose = state["poses"].get(part_id, source_poses[part_id])
        source_position = Rhino.Geometry.Point3d(*source_poses[part_id]["position"])
        solved_position = Rhino.Geometry.Point3d(*final_pose["position"])
        solved_delta = solved_position - source_position
        if solved_delta.IsTiny():
            return Result.Success
        target_position = base_point + solved_delta

        rs.UnselectAllObjects()
        if not rs.SelectObject(assembly_common.parse_guid(part_id)):
            return Result.Failure
        command = "_Move {},{},{} {},{},{} _Enter".format(
            base_point.X,
            base_point.Y,
            base_point.Z,
            target_position.X,
            target_position.Y,
            target_position.Z,
        )
        assembly_model._set_command_busy(doc, False)
        try:
            if not rs.Command(command, echo=False):
                return Result.Failure
        finally:
            assembly_model._set_command_busy(doc, True)
            rs.UnselectAllObjects()
        assembly_model._debug("pull committed native Move driver={}".format(part_id[:8]))
        return Result.Success
    finally:
        conduit.Enabled = False
        doc.Views.Redraw()
        assembly_model._set_command_busy(doc, False)


def RunCommand(is_interactive):
    doc = Rhino.RhinoDoc.ActiveDoc
    if doc is None:
        return Result.Cancel
    data = assembly_model.read_data(doc)
    if not data["parts"] or not data["constraints"]:
        print("Start an assembly with parts and constraints first.")
        return Result.Cancel
    part = _select_part(doc, data)
    if part is None:
        return Result.Cancel
    base_result, base_point = Rhino.Input.RhinoGet.GetPoint(
        "Move point from",
        False,
    )
    if base_result != Rhino.Commands.Result.Success:
        return Result.Cancel
    return _pull(doc, part, base_point)


if __name__ == "__main__":
    from tack.watcher import run_entrypoint

    run_entrypoint(lambda: RunCommand(True), True)
