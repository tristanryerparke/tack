import System.Drawing

import Rhino
import scriptcontext as sc

from ondsel.assembly import assembly_common
from ondsel.assembly import assembly_model
from ondsel.assembly.assembly_pull import _AssemblyPreviewConduit, _source_geometry


CONDUIT_KEY = "Ondsel.Assembly.DynamicConduit.v1"


class AssemblyDynamicConduit(Rhino.Display.DisplayConduit):
    def __init__(self):
        super(AssemblyDynamicConduit, self).__init__()
        self._observed_part_ids = None
        self._observed_poses = None
        self._observed_geometries = None
        self._part_ids = None
        self._source_poses = None
        self._source_geometries = None
        self._preview = None
        self._driver_part_id = None
        self._last_driver_pose = None
        self._dynamic_transform = None
        self._active = False
        self._solving = False

    def _observe(self, doc, data):
        part_ids = tuple(data["parts"].keys())
        if part_ids != self._observed_part_ids:
            poses = {}
            geometries = {}
            for part in data["parts"].values():
                object_id = part["object_id"]
                rhino_object = doc.Objects.FindId(assembly_common.parse_guid(object_id))
                if rhino_object is None:
                    return None, None
                poses[object_id] = assembly_model._current_pose_from_home(
                    doc,
                    part,
                    include_dynamic=False,
                )
                geometries[object_id] = _source_geometry(rhino_object)
            self._observed_part_ids = part_ids
            self._observed_poses = poses
            self._observed_geometries = geometries
            return poses, []

        current_poses = {}
        changed = []
        for part in data["parts"].values():
            object_id = part["object_id"]
            current_pose = assembly_model._current_pose_from_home(
                doc,
                part,
                include_dynamic=False,
            )
            current_poses[object_id] = current_pose
            if assembly_model._pose_motion_metric(
                self._observed_poses[object_id],
                current_pose,
            ) >= 1e-5:
                changed.append(object_id)
        return current_poses, changed

    def _set_sources(self, poses, geometries):
        self._part_ids = tuple(poses.keys())
        self._source_poses = {
            object_id: assembly_model._copy_pose(pose)
            for object_id, pose in poses.items()
        }
        self._source_geometries = {
            object_id: geometry.Duplicate()
            for object_id, geometry in geometries.items()
        }
        self._preview = _AssemblyPreviewConduit(
            self._source_geometries,
            self._source_poses,
        )

    def _clear_preview(self):
        self._active = False
        self._driver_part_id = None
        self._last_driver_pose = None
        self._dynamic_transform = None
        self._part_ids = None
        self._source_poses = None
        self._source_geometries = None
        self._preview = None

    def command_ended(self, doc):
        data = assembly_model.read_data(doc)
        if data["parts"]:
            self._observed_part_ids = None
            self._observe(doc, data)
        self._clear_preview()

    def _update_preview(self, doc):
        if doc is None or assembly_model.is_solving(doc):
            self._clear_preview()
            return
        data = assembly_model.read_data(doc)
        if not data["parts"]:
            self._clear_preview()
            return

        current_poses, locally_changed = self._observe(doc, data)
        if current_poses is None:
            self._clear_preview()
            return

        driver_part_id = None
        dynamic_transform = None
        for object_id in data["parts"]:
            rhino_object = doc.Objects.FindId(assembly_common.parse_guid(object_id))
            dynamic_transform = assembly_model._dynamic_transform(rhino_object)
            if dynamic_transform is not None:
                driver_part_id = object_id
                break

        if driver_part_id is not None:
            if self._part_ids is None:
                self._set_sources(current_poses, self._observed_geometries)
            driver_plane = assembly_model._pose_to_plane(
                self._source_poses[driver_part_id]
            )
            driver_plane.Transform(dynamic_transform)
            driver_pose = assembly_model._plane_to_pose(driver_plane)
        elif locally_changed:
            driver_part_id = locally_changed[0]
            if self._part_ids is None:
                self._set_sources(
                    self._observed_poses,
                    self._observed_geometries,
                )
            driver_pose = current_poses[driver_part_id]
        elif self._active:
            driver_part_id = self._driver_part_id
            driver_pose = self._last_driver_pose
        else:
            self._clear_preview()
            return

        self._active = True
        self._driver_part_id = driver_part_id
        self._dynamic_transform = dynamic_transform
        if (
            self._last_driver_pose is not None
            and assembly_model._pose_motion_metric(self._last_driver_pose, driver_pose) < 1e-5
        ):
            return

        if self._solving:
            return
        self._solving = True
        try:
            result = assembly_model.solve_and_propagate(
                doc,
                driver_part_id=driver_part_id,
                driver_pose=driver_pose,
                apply=False,
            )
            self._last_driver_pose = assembly_model._copy_pose(driver_pose)
            self._preview.update(result["poses"], driver_part_id)
            follower_positions = [
                "{}:{}".format(
                    object_id[:8],
                    [round(value, 3) for value in pose["position"]],
                )
                for object_id, pose in result["poses"].items()
                if object_id != driver_part_id
            ]
            assembly_model._debug(
                "dynamic preview driver={} pos={} followers={}".format(
                    driver_part_id[:8],
                    "pos=" + str([round(value, 4) for value in driver_pose["position"]])
                    + " quat=" + str([round(value, 4) for value in driver_pose["quaternion"]]),
                    " ".join(follower_positions),
                )
            )
        except Exception as error:
            assembly_model._debug("dynamic preview failed: {}".format(error))
        finally:
            self._solving = False

    def PreDrawObjects(self, event):
        self._update_preview(event.RhinoDoc)

    def PreDrawObject(self, event):
        if not self._active or event.RhinoObject is None:
            return
        object_id = assembly_common.guid_string(event.RhinoObject.Id)
        if self._part_ids is not None and object_id in self._part_ids:
            event.DrawObject = False

    def _wireframe_brep(self, object_id):
        geometry = self._source_geometries[object_id].Duplicate()
        if object_id == self._driver_part_id and self._dynamic_transform is not None:
            geometry.Transform(self._dynamic_transform)
        if isinstance(geometry, Rhino.Geometry.Brep):
            return geometry
        if hasattr(geometry, "ToBrep"):
            return geometry.ToBrep()
        return None

    def PostDrawObjects(self, event):
        if not self._active or self._source_geometries is None:
            return
        wire_color = System.Drawing.Color.FromArgb(150, 100, 100, 100)
        for object_id in self._source_geometries:
            brep = self._wireframe_brep(object_id)
            if brep is not None:
                event.Display.DrawBrepWires(brep, wire_color, -1)
        if self._preview is not None:
            self._preview.PostDrawObjects(event)


def command_ended(doc):
    conduit = sc.sticky.get(CONDUIT_KEY)
    if conduit is not None:
        conduit.command_ended(doc)


def start():
    conduit = sc.sticky.get(CONDUIT_KEY)
    if conduit is None:
        conduit = AssemblyDynamicConduit()
        sc.sticky[CONDUIT_KEY] = conduit
    conduit.Enabled = True


def stop():
    conduit = sc.sticky.pop(CONDUIT_KEY, None)
    if conduit is not None:
        conduit.Enabled = False
