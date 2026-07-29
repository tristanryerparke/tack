# Coincident callback test plan

## Current runtime design

The coincident runtime uses these callbacks:

- `ReplaceRhinoObject` for transformations and undo/redo replacements.
- `AddRhinoObject` for Boolean Difference result candidates.
- `DeleteRhinoObject` for permanent deletion detection.
- `UndeleteRhinoObject` for undo restoration.

The runtime does not use `RhinoApp.Idle` for recovery.

## Resume the test session

1. Start the saved relationship from document metadata:

   ```bash
   uv run in-rhino glue_restore.py
   ```

2. Arm the read-only lifecycle diagnostic:

   ```bash
   uv run in-rhino /tmp/tack_coincident_duplicate_debug.py
   ```

3. Confirm that the runtime reports the parent and child IDs and that the diagnostic reports `[Tack duplicate-debug] ARMED`.

## Delete and undo-delete test

Test both the parent and child separately.

1. Run `_Delete` on the tracked object.
2. Record the Tack callback output.
3. Confirm that a permanent deletion produces:

   ```text
   [Tack coincident] DeleteRhinoObject
   ```

   followed by the broken-link warning if the linked object cannot be recovered from callback data or saved metadata.

4. Undo the deletion.
5. Confirm that undo produces:

   ```text
   [Tack coincident] DeleteRhinoObject ... UndoActive=True
   [Tack coincident] UndeleteRhinoObject ... UndoActive=True
   ```

6. Confirm that the original object is re-adopted, the warning is not shown during undo, no duplicate object is created, and the parent/child vertices are coincident.

## Boolean Difference test

### One result

1. Restore the saved relationship.
2. Run `_BooleanDifference` with one result Brep.
3. Confirm `AddRhinoObject` exposes the complete result and that the result containing the saved parent vertex is adopted.
4. Undo the Boolean Difference.
5. Confirm `DeleteRhinoObject`/`UndeleteRhinoObject` restore the original parent without a duplicate and without a broken-link warning.

### Split result

1. Restore the saved relationship.
2. Run `_BooleanDifference` with a cutter that produces two result Breps.
3. Confirm both `AddRhinoObject` candidates are inspected.
4. Confirm the candidate containing the saved linked point is adopted and the other candidate is rejected.
5. Undo the Boolean Difference.
6. Confirm the original parent is restored through `UndeleteRhinoObject`, with no duplicate and no warning.

## Transformation regression test

For each command below, perform the command and then undo it:

- `Move`
- `MoveFace`
- `Scale1D`

Confirm:

- `ReplaceRhinoObject` provides complete old/new geometry.
- Vertex indices remain unchanged when counts remain unchanged.
- The child is corrected during the forward command.
- Tack does not call `CommitChanges()` on the child while `UndoActive=True`.
- Undo restores coincidence without creating a duplicate child.

## Important output to capture

For every test, capture:

- Callback name.
- `UndoActive` and `RedoActive` values.
- Event object IDs.
- `ReplaceRhinoObject` old/new IDs and geometry.
- Any new object IDs.
- Final parent/child IDs and coincident vertex locations.
- Whether the broken-link dialog appeared.

The read-only diagnostic prints objects carrying:

```text
Tack.CoincidentLink.v1
Tack.CoincidentChildId.v1
```

A new GUID appearing for the child during undo indicates a regression similar to the previously reproduced nested-`CommitChanges()` bug.
