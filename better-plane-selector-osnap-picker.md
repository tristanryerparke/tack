# OSnap-driven anchor picker research

This records a proposed picker for choosing the reference point used by a Tack link. Rather than asking the user to choose an anchor category and then select from a custom list of points, it lets Rhino's normal object snaps identify the intended geometric feature.

This is planning/research documentation. It defines a new anchor representation and intentionally does not preserve or describe legacy anchor types.

## Anchor definition

An anchor is a JSON object with a `type` discriminator and only the data needed to identify that type's feature. It does not have a universal `index` field.

```json
{ "type": "bounding_box_center" }
{ "type": "curve_midpoint" }
{ "type": "brep_vertex", "vertex_index": 12 }
{ "type": "brep_face_center", "face_index": 3 }
```

The resolver and reconciler dispatch on `type`:

- A singleton type, such as `bounding_box_center`, regenerates its one point. It has no locator data to reconcile.
- A topology-specific type regenerates the feature identified by its named index, such as `edge_index` or `face_index`.
- A replacement object is accepted only if the specified feature remains valid. Where topology has changed and a feature must be matched by its old location, the match must be unique within model tolerance.

## Picker flow

1. Ask for the parent object and then the child object. While choosing an anchor, lock every other document object, so an object snap cannot accidentally be accepted from the wrong object.
2. Create a `Rhino.Input.Custom.GetPoint`, enable object snaps with `PermitObjectSnap(True)`, and temporarily enable the global OSnap setting.
3. Calculate the selected object's bounding-box center, display it with a small conduit, and supply it to `AddConstructionPoint` and `AddSnapPoint`.
4. On a click, first check whether the result is at that supplied bounding-box center. Otherwise require `PointOnObject()` to identify the selected object and require its object ID to equal the object being anchored.
5. Convert the `ObjRef`, picked point, `OsnapEventType`, and model tolerance into an anchor definition. Reject the pick when the feature cannot be derived unambiguously.
6. Store the definition with the link. At runtime, resolve the definition against the current geometry to recompute its point.

The picker accepts neither a raw point on the object nor an unsupported or ambiguous snap. It asks the user to pick again instead.

## Supported snap derivations

| Rhino snap | Geometry | Anchor definition |
| --- | --- | --- |
| End or Vertex | Brep / extrusion | `{ "type": "brep_vertex", "vertex_index": n }` |
| End or Vertex | Polyline | `{ "type": "polyline_vertex", "vertex_index": n }` |
| End or Vertex | Other open curve | `{ "type": "curve_start" }` or `{ "type": "curve_end" }` |
| Mid / Midpoint | Brep / extrusion | `{ "type": "brep_edge_midpoint", "edge_index": n }` |
| Mid / Midpoint | Polyline | `{ "type": "polyline_segment_midpoint", "segment_index": n }` |
| Mid / Midpoint | Other non-polyline curve | `{ "type": "curve_midpoint" }` |
| Center | Circular Brep edge | `{ "type": "circular_edge_center", "edge_index": n }` |
| Center | Brep face | `{ "type": "brep_face_center", "face_index": n }` |
| Center | Circular curve | `{ "type": "curve_center" }` |
| Supplied custom snap | Any object with a valid bounding box | `{ "type": "bounding_box_center" }` |

For face centers, calculate `AreaMassProperties.Compute(face).Centroid`. For curve and edge midpoints, prefer the normalized-length 50% point and fall back to the parameter-domain midpoint. Convert extrusions to Breps for Brep-specific derivations.

## Data gaps and workarounds

### The custom bounding-box-center snap has no object reference

`AddSnapPoint` and `AddConstructionPoint` give Rhino a point to snap to, but do not associate it with a document object. Therefore, when the user chooses the supplied bounding-box center, `GetPoint.PointOnObject()` cannot identify its source object.

Work around this by comparing the selected point to the calculated bounding-box center within `max(ModelAbsoluteTolerance, 1e-7)`. A match is accepted as `{ "type": "bounding_box_center" }` before attempting to read `PointOnObject()`.

Draw the center with a dedicated display conduit. This makes an otherwise invisible custom snap discoverable and distinguishes it from normal object-snap targets.

### Point-on-object data can be missing or refer to the wrong object

A normal click, a non-object snap, or a custom snap can leave `PointOnObject()` empty. It can also point at a different object. Do not infer an anchor from only the picked coordinate in those cases: reject the pick and loop. Locking all non-target objects during anchor selection reduces the likelihood of the latter case.

### OSnap type alone is not enough to name a Brep component

`OsnapEventType` says a point was an End, Mid, or Center snap, but does not by itself supply the stable Brep vertex, edge, or face index needed for a persistent definition. Read `ObjRef.GeometryComponentIndex` when present to narrow midpoint snaps to an edge and center snaps to an edge or face.

Then regenerate candidate points for that geometry and accept a candidate only when exactly one is within model tolerance of the picked point. This guards against ambiguous coincident features. For a Brep center snap, try circular-edge centers before face centroids because both can use Rhino's `Center` snap.

The exploratory derivation code also tried alternate ObjRef APIs and nearest vertex/edge/face searches when component information was absent. Those are possible fallbacks, but they must still produce one unambiguous feature; otherwise reject the pick.

### Rhino/.NET return shapes vary

`Curve.TryGetCircle()` may return either a `(success, circle)` tuple or a circle-like value depending on the Rhino Python binding. Handle both forms and, if needed, retry with an explicit tolerance. Normalized-length midpoint calculation can fail, so fall back to the curve parameter-domain midpoint.

### Topology can change after a link is made

An anchor definition stores a feature identity, not its original world coordinate. It therefore moves naturally with unchanged topology. Singleton types always resolve to their one current point; `bounding_box_center` does not need a special sentinel index.

For topology-specific definitions, resolve the saved named index when it remains valid. If replacement reconciliation instead relies on the old feature location, require exactly one candidate within tolerance. If no unique feature remains, do not silently choose one; treat the anchor as unreconcilable and break the link.

## Global-state cleanup

The picker temporarily enables `ModelAidSettings.Osnap` and disables `ProjectSnapToCPlane`. Disabling CPlane projection keeps the accepted point on the actual geometry rather than a projected coordinate. A `finally` block must always disable the display conduit, restore both settings, and redraw the document, including when the user cancels or an error occurs.

## Research provenance

The behaviour above was explored in the historical `better-plane-selector` branch. Its `messing/` scripts investigate `GetPoint`, `PointOnObject`, OSnap types, and Brep component indices.
