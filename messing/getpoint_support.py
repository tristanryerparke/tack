import Rhino
import System


TARGET_OBJECT_ID = System.Guid("05be779f-348c-4f99-a78b-4dadbc8f3c86")


def ensure_layer(doc, name, color):
    layer_index = doc.Layers.Find(name, True)
    if layer_index < 0:
        layer = Rhino.DocObjects.Layer()
        layer.Name = name
        layer.Color = color
        return doc.Layers.Add(layer)

    layer = doc.Layers[layer_index]
    if layer.Color != color:
        layer.Color = color
        doc.Layers.Modify(layer, layer_index, True)
    return layer_index


def select_object(prompt):
    result, obj_ref = Rhino.Input.RhinoGet.GetOneObject(
        prompt,
        False,
        Rhino.DocObjects.ObjectType.AnyObject,
    )
    if result != Rhino.Commands.Result.Success or obj_ref is None:
        return None
    return obj_ref


def get_point(prompt, construction_points=()):
    getter = Rhino.Input.Custom.GetPoint()
    getter.SetCommandPrompt(prompt)
    getter.PermitObjectSnap(True)
    getter.FullFrameRedrawDuringGet = True
    if construction_points:
        getter.AddConstructionPoints(list(construction_points))
        getter.AddSnapPoints(list(construction_points))

    result = getter.Get()
    if result != Rhino.Input.GetResult.Point:
        return None

    point = getter.Point()
    obj_ref = getter.PointOnObject()
    snapped_object = obj_ref.Object() if obj_ref is not None else None
    return {
        "point": point,
        "object_ref": obj_ref,
        "object": snapped_object,
        "object_id": obj_ref.ObjectId if obj_ref is not None else None,
        "object_type": (
            snapped_object.ObjectType if snapped_object is not None else None
        ),
        "osnap_type": getter.OsnapEventType,
    }


def pick_point_on_object(target_id, prompt):
    while True:
        picked = get_point(prompt)
        if picked is None:
            return None
        if picked["object_id"] == target_id:
            return picked
        print("That point is not on the target object. Pick again or press Esc.")


def print_pick_debug(picked, derived, point_label="Point"):
    print("{}: {} (supplied)".format(point_label, picked["point"]))
    if picked["object_id"] is not None:
        print("Object ID: {} (supplied)".format(picked["object_id"]))
    if picked["object_type"] is not None:
        print("Object type: {} (supplied)".format(picked["object_type"]))
    print("Osnap type: {} (supplied)".format(picked["osnap_type"]))
    if derived["end_vertex"] is not None:
        print(
            "End vertex: {} ({})".format(
                derived["end_vertex"],
                derived["end_vertex_source"],
            )
        )
    if derived["end_vertex_index"] is not None:
        print(
            "End vertex index: {} ({})".format(
                derived["end_vertex_index"],
                derived["end_vertex_index_source"],
            )
        )
    if derived["edge_index"] is not None:
        print(
            "Edge component: {} index {} ({})".format(
                derived["edge_component_type"],
                derived["edge_index"],
                derived["edge_index_source"],
            )
        )
    if derived["midpoint"] is not None:
        print(
            "Midpoint: {} ({})".format(
                derived["midpoint"],
                derived["midpoint_source"],
            )
        )
    if derived["face_index"] is not None:
        print(
            "Face component: {} index {} ({})".format(
                derived["face_component_type"],
                derived["face_index"],
                derived["face_index_source"],
            )
        )
    if derived.get("bbox_center") is not None:
        print(
            "BBox center: {} ({})".format(
                derived["bbox_center"],
                derived["bbox_center_source"],
            )
        )
    if derived.get("center_kind") is not None:
        center_details = derived["center_kind"]
        if derived.get("center_index") is not None:
            center_details += " {} index {}".format(
                derived["center_component_type"],
                derived["center_index"],
            )
        print("Center classification: {} ({})".format(
            center_details,
            derived["center_source"],
        ))


def run_with_watcher(function):
    try:
        from run_in_rhino.rhino_env.client import SocketConnection
        from run_in_rhino.rhino_env.parasite import OutputParasite

        connection = SocketConnection()
    except Exception:
        return function()

    result = None
    with OutputParasite(connection):
        result = function()
    if result is not None:
        if str(result) == "Success":
            connection.send_done()
        else:
            connection.send_quit()
    return result
