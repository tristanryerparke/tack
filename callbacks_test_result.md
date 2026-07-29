# Callback test results

## Move / Gumball move

### Move and Undo test

The same `ReplaceRhinoObject` callback fired for both the forward move and Undo:

- Forward move: `old` contained the original 8-vertex Brep; `new` contained the moved 8-vertex Brep.
- Undo: `old` contained the moved Brep; `new` contained the restored original Brep.
- The GUID remained `2195ad58-2c20-439a-bd5e-2436c5395ea6`.
- During Undo, callbacks ran with `UndoActive=True`.
- No object callback ran after `UndoActive` became false; `RhinoApp.Idle` reported the settled state.

### MoveFace / face Gumball test

The same `ReplaceRhinoObject` behavior was observed:

- Forward MoveFace: `old` contained the original 8-vertex Brep and `new` contained the moved 8-vertex Brep.
- The forward `new` object had `Guid.Empty`, but its complete geometry was available; the moved vertices had z values from `32.8849` to `37.8849`.
- Undo: `old` contained the moved geometry and `new` contained the restored original geometry, with `UndoActive=True`.
- The vertex count stayed at 8, so vertex indices remained valid.
- `UndeleteRhinoObject` also exposed the restored full geometry, but was not needed because `ReplaceRhinoObject` supplied the old/new pair.
- `AddRhinoObject`, `DeleteRhinoObject`, `PurgeRhinoObject`, `ModifyObjectAttributes`, `UserStringChanged`, and `AfterTransformObjects` fired but were not needed for maintaining Tack.
- `ObjectChanged` observed temporary missing objects and is not a safe primary source.

For MoveFace, use `ReplaceRhinoObject` for the geometry update and `RhinoApp.Idle` to finalize state after undo settles.

### Scale1D test

`ReplaceRhinoObject` provided everything needed:

- Forward Scale1D: `old` contained the original 8-vertex Brep and `new` contained the complete scaled 8-vertex Brep with the same GUID.
- Vertex 0 changed from `x=-27.2176` to `x=-82.4969`.
- The vertex count stayed at 8, so vertex indices remained valid.
- Undo: `old` contained the scaled geometry and `new` contained the restored original geometry, with `UndoActive=True`.
- `UndeleteRhinoObject` also exposed restored geometry, and `IDLE_SETTLED` confirmed the final original state.
- `AfterTransformObjects` fired but was not needed.

For Scale1D, use `ReplaceRhinoObject` and preserve the stored vertex index when the vertex count is unchanged.

Useful callbacks:

1. **`RhinoDoc.ReplaceRhinoObject`**
   - Best callback for geometry analysis.
   - Provides complete old/new geometry and vertex locations.
   - Forward transforms may provide `Guid.Empty` for `NewRhinoObject.Id`, while the geometry is still valid.
   - During undo, `old` was the moved geometry and `new` was the restored geometry.

2. **`RhinoDoc.UndeleteRhinoObject`**
   - During undo, provided the restored full geometry.
   - Useful fallback when relying on object events.

3. **`RhinoApp.Idle`**
   - First stable point after `UndoActive`/`RedoActive` become false.
   - Suitable for final reconciliation, not for obtaining the old/new geometry pair.

`AddRhinoObject`, `DeleteRhinoObject`, `PurgeRhinoObject`, `ModifyObjectAttributes`, `UserStringChanged`, and `AfterTransformObjects` also fired, but were not needed for Move geometry analysis.

## Boolean Difference — one result

### Forward Boolean Difference

`ReplaceRhinoObject` did not fire. The useful callback was `AddRhinoObject`, which provided the complete new 14-vertex result:

```text
new ID: ca9356ce-b097-4f80-9c17-4ad45d22266d
vertices: 14
```

The original parent ID became missing:

```text
2195ad58-2c20-439a-bd5e-2436c5395ea6 → missing
```

The result retained the linked point at vertex index `7`:

```text
(107.2176, 48.0897, 5.0000)
```

The old parent geometry was not provided by the Boolean callback; cache the original linked point before the operation.

### Undo

Result-object events fired with `UndoActive=True`, but were transient. `IDLE_SETTLED` showed the original parent restored with its original 8 vertices and indices.

### Implementation verdict

1. Cache the original linked point before Boolean Difference.
2. Collect new Breps from `AddRhinoObject`.
3. Wait for `RhinoApp.Idle`.
4. Select the candidate containing the cached linked point.
5. Rebind the link to that candidate.

Do not use `ReplaceRhinoObject` for this Boolean Difference path.

## Boolean Difference — split result

### Forward Boolean Difference

`ReplaceRhinoObject` did not fire. `AddRhinoObject` fired once for each complete result:

```text
7bd03267-5146-4313-a556-98814beb82c0 → 8 vertices
75bc1fed-7676-4093-8993-27eb1dac337f → 10 vertices
```

The original parent was missing. The original linked point:

```text
(107.2176, 48.0897, 5.0000)
```

was present in the 10-vertex result at vertex index `3`, and absent from the 8-vertex result.

### Undo

`AddRhinoObject` and the other object callbacks fired for transient result objects with `UndoActive=True`. The original parent was restored after the event sequence settled at `IDLE_SETTLED`.

### Implementation verdict

1. Cache the original linked point and vertex index.
2. Collect every `AddRhinoObject` candidate.
3. If vertex counts are unchanged, validate the stored index.
4. If counts changed, locate the cached point by position.
5. Adopt only the candidate containing the original linked point.
6. Wait for `RhinoApp.Idle` before mutating links during undo.

Matching an arbitrary candidate vertex is insufficient.

## Undo lifecycle

During undo:

```text
UndoActive=True
RedoActive=False
```

Object callbacks can observe temporary missing objects and intermediate states. `ReplaceRhinoObject` and `UndeleteRhinoObject` can still expose useful restored geometry during undo, but document mutation should wait.

After Rhino finishes undo:

```text
UndoActive=False
RedoActive=False
UndoRecordingIsActive=False
```

`RhinoApp.Idle` is the reliable post-undo synchronization point.

## EndUndoRecord / custom undo

`EndUndoRecord()` is a method that closes an undo record explicitly created with `BeginUndoRecord()`; it is not a lifecycle event for normal user undo.

`AddCustomUndoEvent()` callbacks run during undo, while `UndoActive=True`, not after undo completes.

The current Rhino Python binding exposes no dedicated `UndoFinished` or `EndCommand` event suitable for this purpose.
