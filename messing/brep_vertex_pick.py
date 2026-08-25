import importlib

import Rhino
import System.Drawing
from Rhino.Commands import Result

import derivation
import getpoint_support

importlib.reload(derivation)
importlib.reload(getpoint_support)

from derivation import brep_edge_at
from derivation import brep_face_at
from derivation import brep_vertex_at
from derivation import derive_snap_data
from derivation import object_bbox_center
from derivation import polyline_vertex_at
from getpoint_support import ensure_layer
from getpoint_support import get_point
from getpoint_support import print_pick_debug
from getpoint_support import select_object
from getpoint_support import run_with_watcher


def _osnap_name(osnap_type):
    return str(osnap_type).split(".")[-1].lower()


def _red_attributes(layer_index):
    attributes = Rhino.DocObjects.ObjectAttributes()
    attributes.LayerIndex = layer_index
    attributes.ObjectColor = System.Drawing.Color.Red
    attributes.ColorSource = Rhino.DocObjects.ObjectColorSource.ColorFromObject
    return attributes


class _BboxCenterConduit(Rhino.Display.DisplayConduit):
    def __init__(self, center):
        super(_BboxCenterConduit, self).__init__()
        self.center = center

    def DrawForeground(self, event):
        event.Display.DrawPoint(
            self.center,
            Rhino.Display.PointStyle.Circle,
            3,
            System.Drawing.Color.Black,
        )
        event.Display.DrawPoint(
            self.center,
            Rhino.Display.PointStyle.Circle,
            2,
            System.Drawing.Color.White,
        )


def _add_bbox_center_verification_point(doc, center, layer_index):
    point_id = doc.Objects.AddPoint(
        center,
        _red_attributes(layer_index),
    )
    print("Added verification point for bbox center: {}".format(point_id))


def _add_vertex_verification_point(
    doc,
    obj_ref,
    vertex_index,
    end_vertex,
    layer_index,
):
    brep_vertex = (
        brep_vertex_at(obj_ref, vertex_index)
        if vertex_index is not None
        else None
    )
    if brep_vertex is not None:
        point = brep_vertex.Location
        label = "Brep vertex index {}".format(vertex_index)
    else:
        point = (
            polyline_vertex_at(obj_ref, vertex_index)
            if vertex_index is not None
            else None
        )
        if point is not None:
            label = "polyline vertex index {}".format(vertex_index)
        elif end_vertex is not None:
            point = end_vertex
            label = "generic curve end"
        else:
            print("Could not resolve vertex {}.".format(vertex_index))
            return

    point_id = doc.Objects.AddPoint(
        point,
        _red_attributes(layer_index),
    )
    print("Added verification point for {}: {}".format(label, point_id))


def _add_red_edge(doc, obj_ref, edge_index, layer_index):
    edge = brep_edge_at(obj_ref, edge_index)
    if edge is None:
        print("Could not resolve Brep edge index {}.".format(edge_index))
        return

    curve = edge.DuplicateCurve()
    curve_id = doc.Objects.AddCurve(
        curve,
        _red_attributes(layer_index),
    )
    print("Added red curve for Brep edge index {}: {}".format(edge_index, curve_id))


def _add_red_face(doc, obj_ref, face_index, layer_index):
    face = brep_face_at(obj_ref, face_index)
    if face is None:
        print("Could not resolve Brep face index {}.".format(face_index))
        return

    surface = face.DuplicateSurface()
    surface_id = doc.Objects.AddSurface(
        surface,
        _red_attributes(layer_index),
    )
    print("Added red surface for Brep face index {}: {}".format(face_index, surface_id))


def RunCommand(is_interactive):
    doc = Rhino.RhinoDoc.ActiveDoc
    if doc is None:
        print("No active Rhino document.")
        return Result.Cancel

    layer_index = ensure_layer(
        doc,
        "Layer 01",
        System.Drawing.Color.Red,
    )
    if layer_index < 0:
        print("Could not create or find Layer 01.")
        return Result.Cancel

    target_ref = select_object("Select an object")
    if target_ref is None:
        return Result.Cancel
    target_object = target_ref.Object()
    center = object_bbox_center(target_ref)
    if target_object is None or center is None:
        print("Could not get the selected object's bounding box.")
        return Result.Cancel

    center_conduit = _BboxCenterConduit(center)
    center_conduit.Enabled = True
    doc.Views.Redraw()
    picked = None
    custom_bbox_center = False
    try:
        while True:
            picked = get_point(
                "Pick a vertex, midpoint, center, or bbox center",
                construction_points=(center,),
            )
            if picked is None:
                return Result.Cancel

            center_tolerance = max(doc.ModelAbsoluteTolerance, 1e-7)
            if picked["point"].DistanceTo(center) <= center_tolerance:
                picked.update(
                    {
                        "object_ref": target_ref,
                        "object": target_object,
                        "object_id": target_ref.ObjectId,
                        "object_type": target_object.ObjectType,
                        "osnap_type": "BBox Center",
                    }
                )
                custom_bbox_center = True
                break
            if picked["object_id"] == target_ref.ObjectId:
                break
            print(
                "That point is not on the selected object. "
                "Pick again or press Esc."
            )
    finally:
        center_conduit.Enabled = False
        doc.Views.Redraw()

    derived = derive_snap_data(
        picked["object_ref"] if not custom_bbox_center else None,
        picked["point"],
        picked["osnap_type"],
    )
    if custom_bbox_center:
        derived["bbox_center"] = center
        derived["bbox_center_source"] = "derived"
    print_pick_debug(picked, derived, point_label="Accepted point")

    snap_name = _osnap_name(picked["osnap_type"])
    if custom_bbox_center:
        _add_bbox_center_verification_point(doc, center, layer_index)
        doc.Views.Redraw()
        return Result.Success
    if snap_name in ("end", "vertex"):
        vertex_index = derived["end_vertex_index"]
        if vertex_index is not None or derived["end_vertex"] is not None:
            _add_vertex_verification_point(
                doc,
                picked["object_ref"],
                vertex_index,
                derived["end_vertex"],
                layer_index,
            )
    elif snap_name in ("mid", "midpoint"):
        edge_index = derived["edge_index"]
        if edge_index is not None:
            _add_red_edge(
                doc,
                picked["object_ref"],
                edge_index,
                layer_index,
            )
    elif snap_name == "center":
        if derived["center_kind"] == "circular edge":
            edge_index = derived["center_index"]
            if edge_index is not None:
                _add_red_edge(
                    doc,
                    picked["object_ref"],
                    edge_index,
                    layer_index,
                )
        elif derived["center_kind"] == "face center":
            face_index = derived["center_index"]
            if face_index is not None:
                _add_red_face(
                    doc,
                    picked["object_ref"],
                    face_index,
                    layer_index,
                )

    doc.Views.Redraw()
    return Result.Success


if __name__ == "__main__":
    run_with_watcher(lambda: RunCommand(True))
