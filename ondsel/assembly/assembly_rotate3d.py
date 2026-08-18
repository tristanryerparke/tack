import importlib
import math

import Rhino
import rhinoscriptsyntax as rs
import scriptcontext as sc
from Rhino.Commands import Result

from ondsel.assembly import assembly_common
from ondsel.assembly import assembly_model
from ondsel.assembly import assembly_pull

assembly_pull = importlib.reload(assembly_pull)
from ondsel.assembly.assembly_pull import (
    _AssemblyPreviewConduit,
    _PullGetPoint,
    _select_part,
    _source_geometry,
)


def _get_point(prompt):
    result, point = Rhino.Input.RhinoGet.GetPoint(prompt, False)
    if result != Result.Success:
        return None
    return point


def _project_radial(point, axis_origin, axis_direction):
    radial = point - axis_origin
    radial -= axis_direction * (radial * axis_direction)
    if not radial.Unitize():
        return None
    return radial


def _rotation_angle(point, axis_origin, axis_direction, start_radial):
    radial = _project_radial(point, axis_origin, axis_direction)
    if radial is None:
        return None
    sine = axis_direction * Rhino.Geometry.Vector3d.CrossProduct(start_radial, radial)
    cosine = start_radial * radial
    return math.atan2(sine, cosine)


def _rotated_pose(pose, axis_origin, axis_direction, angle):
    plane = assembly_model._pose_to_plane(pose)
    transform = Rhino.Geometry.Transform.Rotation(
        angle,
        axis_direction,
        axis_origin,
    )
    plane.Transform(transform)
    return assembly_model._plane_to_pose(plane)


def _rotate(doc, part, axis_origin, axis_direction, start_point):
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

    start_radial = _project_radial(start_point, axis_origin, axis_direction)
    if start_radial is None:
        print("Rotation start point must not lie on the rotation axis.")
        return Result.Cancel

    state = {"poses": dict(source_poses), "error": None}
    conduit = _AssemblyPreviewConduit(source_geometries, source_poses)
    conduit.update(state["poses"], part_id)

    def update_preview(point):
        angle = _rotation_angle(
            point,
            axis_origin,
            axis_direction,
            start_radial,
        )
        if angle is None:
            return
        driver_pose = _rotated_pose(
            source_poses[part_id],
            axis_origin,
            axis_direction,
            angle,
        )
        try:
            result = assembly_model.solve_and_propagate(
                doc,
                driver_part_id=part_id,
                driver_pose=driver_pose,
                apply=False,
            )
            state["poses"] = result["poses"]
            state["angle"] = angle
            conduit.update(state["poses"], part_id)
        except Exception as error:
            state["error"] = error
            assembly_model._debug("rotate3d preview solve failed: {}".format(error))

    assembly_model._set_command_busy(doc, True)
    try:
        conduit.Enabled = True
        doc.Views.Redraw()
        getter = _PullGetPoint(update_preview, start_point)
        getter.SetCommandPrompt("Rotate the constrained assembly; click to commit")
        getter.SetBasePoint(start_point, True)
        getter.AcceptNothing(False)
        getter.FullFrameRedrawDuringGet = True
        result = getter.Get()
        if result != Rhino.Input.GetResult.Point or state["error"] is not None:
            return Result.Cancel

        final_point = getter.Point
        if callable(final_point):
            final_point = final_point()
        requested_angle = _rotation_angle(
            final_point,
            axis_origin,
            axis_direction,
            start_radial,
        )
        if requested_angle is None:
            return Result.Cancel
        final_pose = state["poses"].get(part_id, source_poses[part_id])
        solved_delta = assembly_model._pose_delta(
            source_poses[part_id],
            final_pose,
        )
        solved_start = Rhino.Geometry.Point3d(start_point)
        solved_start.Transform(solved_delta)
        final_angle = _rotation_angle(
            solved_start,
            axis_origin,
            axis_direction,
            start_radial,
        )
        if final_angle is None or abs(final_angle) < 1e-8:
            return Result.Success

        rs.UnselectAllObjects()
        if not rs.SelectObject(assembly_common.parse_guid(part_id)):
            return Result.Failure
        command = "_Rotate3D {},{},{} {},{},{} {} _Enter".format(
            axis_origin.X,
            axis_origin.Y,
            axis_origin.Z,
            axis_origin.X + axis_direction.X,
            axis_origin.Y + axis_direction.Y,
            axis_origin.Z + axis_direction.Z,
            math.degrees(final_angle),
        )
        assembly_model._set_command_busy(doc, False)
        try:
            if not rs.Command(command, echo=False):
                return Result.Failure
        finally:
            assembly_model._set_command_busy(doc, True)
            rs.UnselectAllObjects()
        assembly_model._debug("rotate3d committed native Rotate3D driver={}".format(part_id[:8]))
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

    axis_start = _get_point("Rotate3D axis start")
    if axis_start is None:
        return Result.Cancel
    axis_end = _get_point("Rotate3D axis end")
    if axis_end is None:
        return Result.Cancel
    axis_direction = axis_end - axis_start
    if not axis_direction.Unitize():
        print("Rotation axis points must be distinct.")
        return Result.Cancel
    start_point = _get_point("Rotate3D rotation start point")
    if start_point is None:
        return Result.Cancel
    return _rotate(doc, part, axis_start, axis_direction, start_point)


if __name__ == "__main__":
    from tack.watcher import run_entrypoint

    run_entrypoint(lambda: RunCommand(True), True)
