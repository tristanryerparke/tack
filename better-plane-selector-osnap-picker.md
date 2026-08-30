# OSnap-driven anchor picker research

This records a proposed picker for choosing the reference point used by a Tack link. Rather than asking the user to choose an anchor category and then select from a custom list of points, it lets Rhino's normal object snaps identify the intended geometric feature.

This is planning/research documentation. It defines a new anchor representation and intentionally does not preserve or describe legacy anchor types.

## Anchor definition

An anchor is a JSON object with a `type` discriminator and whatever type-specific metadata is needed to identify that feature. There is no universal schema beyond `type`: each type handler validates, resolves, and reconciles its own fields. The metadata is stored and passed through unchanged rather than being reduced to a fixed `index` field.

```json
{ "type": "bounding_box_center" }
{ "type": "curve_midpoint" }
{ "type": "brep_vertex", "vertex_index": 12 }
{ "type": "brep_face_center", "face_index": 3 }
{ "type": "brep_edge_quadrant", "edge_index": 4, "quadrant": 2 }
```

The resolver and reconciler dispatch on `type`:

- A singleton type, such as `bounding_box_center`, regenerates its one point. It has no locator data to reconcile.
- A topology-specific type regenerates the feature identified by all of its named metadata, such as `edge_index` plus `quadrant`.
- A replacement object is accepted only if the type handler can resolve the specified feature. Where topology has changed and a feature must be matched by its old location, the match must be unique within model tolerance.

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
| Quadrant | Circular/elliptical Brep edge | `{ "type": "brep_edge_quadrant", "edge_index": n, "quadrant": q }` |
| Quadrant | Circular/elliptical curve | `{ "type": "curve_quadrant", "quadrant": q }` |
| Supplied custom snap | Any object with a valid bounding box | `{ "type": "bounding_box_center" }` |

For face centers, calculate `AreaMassProperties.Compute(face).Centroid`. For curve and edge midpoints, prefer the normalized-length 50% point and fall back to the parameter-domain midpoint. Quadrant `q` identifies one of the valid quarter-turn positions of the circular or elliptical curve; a trimmed arc only exposes positions that lie on its domain. Convert extrusions to Breps for Brep-specific derivations.

### Overlapping snap positions

Use `OsnapEventType` as the primary classification. When a fallback must infer a feature from coincident candidate points, apply this precedence:

1. `End` or `Vertex`
2. `Midpoint`
3. `Quadrant`

Therefore, when an endpoint coincides with quadrant `0`, store the endpoint definition rather than a quadrant definition. When a midpoint coincides with quadrant `2`, store the midpoint definition rather than a quadrant definition. Quadrant is the fallback identity only when neither higher-priority feature applies.

## Data gaps and workarounds

### The custom bounding-box-center snap has no object reference

`AddSnapPoint` and `AddConstructionPoint` give Rhino a point to snap to, but do not associate it with a document object. Therefore, when the user chooses the supplied bounding-box center, `GetPoint.PointOnObject()` cannot identify its source object.

Work around this by comparing the selected point to the calculated bounding-box center within `max(ModelAbsoluteTolerance, 1e-7)`. A match is accepted as `{ "type": "bounding_box_center" }` before attempting to read `PointOnObject()`.

Draw the center with a dedicated display conduit. This makes an otherwise invisible custom snap discoverable and distinguishes it from normal object-snap targets.

### Point-on-object data can be missing or refer to the wrong object

A normal click, a non-object snap, or a custom snap can leave `PointOnObject()` empty. It can also point at a different object. Do not infer an anchor from only the picked coordinate in those cases: reject the pick and loop. Locking all non-target objects during anchor selection reduces the likelihood of the latter case.

### OSnap type alone is not enough to name a Brep component

`OsnapEventType` says a point was an End, Mid, Center, or Quadrant snap, but does not by itself supply the stable Brep vertex, edge, face, or quadrant identity needed for a persistent definition. Read `ObjRef.GeometryComponentIndex` when present to narrow midpoint and quadrant snaps to an edge and center snaps to an edge or face.

Then regenerate candidate points for that geometry and accept a candidate only when exactly one is within model tolerance of the picked point. This guards against ambiguous coincident features. For a Brep center snap, try circular-edge centers before face centroids because both can use Rhino's `Center` snap. For a quadrant snap, determine the matching valid quadrant and include it alongside the edge index when the anchor is stored.

The exploratory derivation code also tried alternate ObjRef APIs and nearest vertex/edge/face searches when component information was absent. Those are possible fallbacks, but they must still produce one unambiguous feature; otherwise reject the pick.

### Rhino/.NET return shapes vary

`Curve.TryGetCircle()` may return either a `(success, circle)` tuple or a circle-like value depending on the Rhino Python binding. Handle both forms and, if needed, retry with an explicit tolerance. Normalized-length midpoint calculation can fail, so fall back to the curve parameter-domain midpoint.

### Topology can change after a link is made

An anchor definition stores a feature identity, not its original world coordinate. It therefore moves naturally with unchanged topology. Singleton types always resolve to their one current point; `bounding_box_center` does not need a special sentinel index.

For topology-specific definitions, the type handler resolves all saved metadata when it remains valid: for example, a quadrant handler resolves both `edge_index` and `quadrant`. If replacement reconciliation instead relies on the old feature location, require exactly one candidate within tolerance. If no unique feature remains, do not silently choose one; treat the anchor as unreconcilable and break the link.

## Global-state cleanup

The picker temporarily enables `ModelAidSettings.Osnap` and disables `ProjectSnapToCPlane`. Disabling CPlane projection keeps the accepted point on the actual geometry rather than a projected coordinate. A `finally` block must always disable the display conduit, restore both settings, and redraw the document, including when the user cancels or an error occurs.

## Research provenance

The behaviour above was explored in the historical `better-plane-selector` branch. Its `messing/` scripts investigate `GetPoint`, `PointOnObject`, OSnap types, and Brep component indices.
