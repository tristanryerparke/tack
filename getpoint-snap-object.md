# GetPoint: find the object used by an object snap

`Rhino.Input.Custom.GetPoint` returns the picked point, and can also return an `ObjRef` for the Rhino document object that the point landed on.

```python
import Rhino


def get_point_and_snap_object():
    getter = Rhino.Input.Custom.GetPoint()
    getter.SetCommandPrompt("Pick a point")
    getter.PermitObjectSnap(True)

    result = getter.Get()
    if result != Rhino.Input.GetResult.Point:
        return None

    point = getter.Point()
    obj_ref = getter.PointOnObject()

    snapped_object = None
    object_id = None
    if obj_ref is not None:
        snapped_object = obj_ref.Object()
        object_id = obj_ref.ObjectId

    return {
        "point": point,
        "object_ref": obj_ref,
        "object": snapped_object,
        "object_id": object_id,
        "osnap_type": getter.OsnapEventType,
    }


picked = get_point_and_snap_object()
if picked is not None:
    print("Point: {}".format(picked["point"]))
    print("Object ID: {}".format(picked["object_id"]))
    print("Osnap type: {}".format(picked["osnap_type"]))
```

## Important details

- `PointOnObject()` returns `None` when the point was not on a document object.
- `ObjectRef.Object()` returns the `RhinoObject`; `ObjectRef.ObjectId` returns its GUID.
- `OsnapEventType` identifies the snap mode, such as End, Near, or Vertex.
- `PointOnObject()` describes the object containing the resulting point. Use `OsnapEventType` as well when you need to determine whether an object snap actually produced the point.
- Points added with `AddSnapPoint(s)` or `AddConstructionPoint(s)` do not automatically carry an object association, so `PointOnObject()` will not identify their source object. Store the source object alongside those points yourself.

## Custom snap points with source tracking

For application-defined points, keep the source object in a parallel data structure:

```python
import Rhino


sources = []
points = []

for rhino_object in objects:
    for point in get_candidate_points(rhino_object):
        points.append(point)
        sources.append(rhino_object)

getter = Rhino.Input.Custom.GetPoint()
getter.SetCommandPrompt("Pick a custom point")
getter.AddSnapPoints(points)

if getter.Get() == Rhino.Input.GetResult.Point:
    picked_point = getter.Point()
    picked_index = min(
        range(len(points)),
        key=lambda index: picked_point.DistanceTo(points[index]),
    )
    source_object = sources[picked_index]
```

For exact matching, prefer retaining the candidate index in your own hit-testing or selection logic rather than relying on a distance comparison.
