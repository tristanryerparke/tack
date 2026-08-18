import Rhino
import scriptcontext as sc

from ondsel.assembly import assembly_common
from ondsel.assembly import assembly_model
from ondsel.assembly.assembly_pull import _AssemblyPreviewConduit, _source_geometry


CONDUIT_KEY = "Ondsel.Assembly.DynamicConduit.v1"


class AssemblyDynamicConduit(Rhino.Display.DisplayConduit):
    def __init__(self):
        super(AssemblyDynamicConduit, self).__init__()
        self._part_ids = None
        self._source_poses = None
        self._source_geometries = None
        self._preview = None
        self._driver_part_id = None
        self._last_driver_pose = None
        self._solving = False

    def _reset_sources(self, doc, data):
        part_ids = tuple(data["parts"].keys())
        if part_ids == self._part_ids:
            return True
        source_poses = {}
        source_geometries = {}
        for part in data["parts"].values():
            object_id = part["object_id"]
            rhino_object = doc.Objects.FindId(assembly_common.parse_guid(object_id))
            if rhino_object is None:
                return False
            source_poses[object_id] = assembly_model._current_pose_from_home(
                doc,
                part,
                include_dynamic=False,
            )
            source_geometries[object_id] = _source_geometry(rhino_object)
        self._part_ids = part_ids
        self._source_poses = source_poses
        self._source_geometries = source_geometries
        self._preview = _AssemblyPreviewConduit(source_geometries, source_poses)
        return True

    def _clear_preview(self):
        self._driver_part_id = None
        self._last_driver_pose = None
        self._part_ids = None
        self._source_poses = None
        self._source_geometries = None
        self._preview = None

    def PostDrawObjects(self, event):
        doc = event.RhinoDoc
        if doc is None or assembly_model.is_solving(doc):
            return
        data = assembly_model.read_data(doc)
        if not data["parts"]:
            self._clear_preview()
            return

        driver_part_id = None
        for object_id in data["parts"]:
            rhino_object = doc.Objects.FindId(assembly_common.parse_guid(object_id))
            if assembly_model._dynamic_transform(rhino_object) is not None:
                driver_part_id = object_id
                break
        if driver_part_id is None:
            self._clear_preview()
            return
        if not self._reset_sources(doc, data):
            self._clear_preview()
            return

        driver_part = data["parts"][driver_part_id]
        driver_object = doc.Objects.FindId(assembly_common.parse_guid(driver_part_id))
        dynamic_transform = assembly_model._dynamic_transform(driver_object)
        if dynamic_transform is None:
            self._clear_preview()
            return
        driver_plane = assembly_model._pose_to_plane(self._source_poses[driver_part_id])
        driver_plane.Transform(dynamic_transform)
        driver_pose = assembly_model._plane_to_pose(driver_plane)
        if (
            self._driver_part_id == driver_part_id
            and self._last_driver_pose is not None
            and assembly_model._pose_motion_metric(self._last_driver_pose, driver_pose) < 1e-5
        ):
            if self._preview is not None:
                self._preview.PostDrawObjects(event)
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
            self._driver_part_id = driver_part_id
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
            self._preview.PostDrawObjects(event)
        except Exception as error:
            assembly_model._debug("dynamic preview failed: {}".format(error))
        finally:
            self._solving = False


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
