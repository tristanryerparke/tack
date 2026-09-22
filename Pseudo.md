# Tack States: Pseudocode vs Current Implementation

### Add Tack:
1. Configure Tack options
	- Translation(boolean): 
	- Rotation(boolean): Forces the user to select planes as opposed to points)
	- Attachment(boolean): Forces the child so its point/plane coincident with the parent's point/plane)
	- Allow Child Movement (Saves the initial relationship between tack points/planes so that the if the child is moved, it can be reset to have its initial relationship to the parent point/plane be re-instated. If off, children snap back if moved)
	*Note: "planes" are still stored for translation only tacks, but the user is only asked to select their origin*
2. Select Parent
3. Select Parent Point/Frame using osnap picker
4. Select Child
5. Select Child Point/Frame using osnap picker
6. Preview Attachment (Conditional): If Attachment is on, let the user preview the child's position with optional invert if Frames have been selected.
7. Save tack information
	1. Create a tack GUID, save it to record
	2. Save parent and child IDs
	3. Save the point or plane anchor representations for parent and child
	4. Save the settings (translation/rotation/allow child)
	5. Create the record object
	6. Save it to the tack state

> **Contradictory summary — what Tack does now:** Tack has a separate `Allow Child Movement` option and an eight-character hexadecimal Tack ID, not a GUID. `Attach=On` is a one-time full plane alignment: it moves the Child before saving the relationship. `Attach=Off` leaves the Child where it is. Both save the same parent-local plane-plane transform; Child movement only decides whether a later Child-only move replaces that saved transform or is corrected back to it. The complete Link is saved on the Parent object, a reference is saved on the Child object, and only derived runtime data is put in `sc.sticky`.

#### Add Tack (Current):
1. Select the Parent and configure options in the same prompt using [`select_parent_and_degrees_of_freedom()`](tack/prompting/add_flow.py#L110)
	- Translation(boolean): If on, the Child's origin follows the target origin. If off, the Child keeps its live origin.
	- Rotation(boolean): If on, analytic planes are picked and the Child's axes follow the target axes. If off, one origin anchor is picked and world axes complete the stored plane.
	- Attach(boolean): If on, move the Child into full plane alignment before saving the relationship. It is not a saved mode.
	- Allow Child Movement(boolean): If on, a Child-only move replaces the saved relationship. If off, Tack corrects the Child back to it.
	- The four option values are saved as per-user plug-in settings by [`_save_parent_options()`](tack/prompting/add_flow.py#L26).
2. Pick the Parent anchor/plane using [`pick_plane()`](tack/prompting/add_flow.py#L69)
	- Rotation off calls [`pick_origin()`](tack/prompting/analytic_plane_picker.py#L365) and stores a `world_axes_plane` definition.
	- Rotation on calls [`pick_plane()`](tack/prompting/analytic_plane_picker.py#L378). A circular center can define a plane in one pick; otherwise origin, X and Y analytic anchors define it.
	- The picker temporarily locks other objects, enables Osnap, disables Project-to-CPlane, and only accepts derivable anchors using [`AnchorPickSession`](tack/prompting/osnap_anchor_picker.py#L66).
3. Select and check the Child
	- [`select_child()`](tack/prompting/add_flow.py#L96) disables preselection and rejects the Parent itself.
	- [`repository.would_create_cycle()`](tack/links/repository.py#L242) rejects a directed parent-child loop before the Child plane is picked.
	- The Child anchor/plane is picked using the same Rotation-dependent flow as the Parent. Rotation-on selection then offers `Flip`; [`_flip_child_plane()`](tack/prompting/add_flow.py#L39) emits a Child plane definition whose resolver reverses its Z orientation using [`flipped_definition()`](tack/anchors/analytic_plane.py#L137). This is selection data, not a Link flag.
4. Establish the initial relationship in [`actions.add()`](tack/actions.py#L23)
	- Attach on: [`preview_placement()`](tack/prompting/add_flow.py#L159) displays full plane alignment and waits for Enter. The Child geometry is then replaced in place with the accepted transform.
	- Attach off: the Child is not moved.
	- In both cases, [`repository.create()`](tack/links/repository.py#L250) resolves the actual post-selection Parent/Child planes and saves the Child plane in Parent-local coordinates as `original_transform` and `current_transform`.
	- Translation and Rotation filter which parts of that target plane are applied later using [`constrained_target_child_plane()`](tack/links/transforms.py#L31).
5. Persist and install the Tack
	- [`repository.create()`](tack/links/repository.py#L250) creates an eight-character ID and an immutable [`Link`](tack/links/schema.py#L15).
	- [`repository.save()`](tack/links/repository.py#L133) writes the complete Link under `Tack.Link` on the Parent and the ID under `Tack.LinkRef` on the Child in one undoable metadata update.
	- [`runtime.install()`](tack/links/runtime.py#L205) resolves both planes into a temporary `LinkState`, installs the display conduit, and subscribes the lifecycle handlers.

Current Link creation is effectively:

```python
if degrees_of_freedom["attach"]:
    transform = preview_placement(doc, child, parent_plane, child_plane)
    transformed_child = transforms.transform_object_in_place(doc, child, transform)

link = repository.create(
    doc,
    parent.Id,
    transformed_child.Id,
    parent_definition,
    child_definition,
    translation=degrees_of_freedom["translation"],
    rotation=degrees_of_freedom["rotation"],
    allow_child_movement=degrees_of_freedom["allow_child_movement"],
)
```

The complete call is in [`actions.add()`](tack/actions.py#L23).

### EndCommand Handler:
1. Iterate through the tacks in the state (sc.sticky section pertaining to tack in this document), first looking through the invalid ones to see if any can be reconstructed.(valid and invalid lists), for each:
	1. Check that the parent exists and its point/plane can be resolved
	2. Check that the child exists and its point/plane can be resolved
	3. If the tack can't be resolved, shift it into the "invalid" state area
	4. If the tack is invalid and still is invalid, increment its stale counter (counters greater than ~200 purge the invalid tack)
	5. If the tack was previously invalid and can be made valid, shift it into the "valid" state area. 
2. Re-order valid tacks order of their directed acyclic graph (this ensures cascading tacks are addressed. 
3. **Reconciliation:** Loop through the above re-ordered list and test if a tack needs to be updated:
	1. **Moved Parent:** Calculate plane of the parent, compare it to the stored plane, has it moved? If so, parse that transform and solve the child's new location to make the original saved plane-plane relationship valid. 
	2. **Moved Child:** Calculate the plane of the child, compare it to the stored plane. Has it moved? 
		1. If child movement is allowed, update the plane-plane relationship that is to be maintained if the parent moves
		2. If child movemet is not allowed, snap the child back so that the stored plane-plane is maintained. 
	3. **Neither Moved**:  Return quickly and cleanly to avoid lag during normal rhino use

> **Contradictory summary — what Tack does now:** EndCommand does not scan every object, rebuild a persistent valid/invalid pair of lists, compare planes to detect changes, or topologically reorder the graph. It observes only endpoints already named by active/cached states, reconciles those states with object metadata, detects changes with Rhino object runtime serial numbers, and settles chains with at most `number of active Tacks + 1` passes. Every Tack resolves its saved parent-local transform. A Child-only move replaces it only when `Allow Child Movement` is on; otherwise the enabled parts of the Child are corrected back to it.

#### EndCommand Handler (Current):
1. Finish the native-command preview
	- [`end_command_handler()`](tack/links/lifecycle.py#L73) tells the shared conduit that the command ended, which clears dynamic sources and previews.
	- A module-level `_solving` flag prevents Tack's own object replacements from recursively starting another solve.
2. Reconcile runtime state with object metadata using [`_reconcile_runtime_with_metadata()`](tack/links/lifecycle.py#L36)
	- [`_observed_links()`](tack/links/lifecycle.py#L23) starts with only active/cached endpoints, then includes the endpoint IDs named by the Parent records it finds.
	- A runtime state whose active Parent record/Child reference pair disappeared is moved to the invalid cache using [`cache_state()`](tack/links/state.py#L66).
	- A valid metadata pair with no matching state is resolved into a new state using [`new_state()`](tack/links/state.py#L122). This is how native Undo can restore a recently removed Tack.
	- Cached states are aged by [`keep_invalid_for_undo()`](tack/links/state.py#L104) and removed when their age reaches exactly 200 command endings.
3. Find changed Tacks using [`changed_states()`](tack/links/solver.py#L98)
	- Parent and Child `RuntimeSerialNumber` values are compared with the serials cached in `LinkState`.
	- If no serial changed and no state was newly reconstructed, no call to `maintain()` is made.
4. Settle changed chains using [`maintain_changed_states()`](tack/links/solver.py#L113)
	- There is no explicit DAG reorder. Each pass maintains all current candidates, then another pass catches downstream Children whose runtime serial changed during the previous pass.
	- The loop is bounded to `len(active states) + 1` passes. New cycles are separately prevented when a Tack is created by [`graph.would_create_cycle()`](tack/links/graph.py#L4).
5. Maintain each changed Tack using [`maintain()`](tack/links/solver.py#L23)
	- Both endpoint objects and both analytic planes are resolved again before anything moves.
	- Child changed without Parent + Allow Child Movement: recalculate and persist `current_transform`. The saved `original_transform` remains available for Reset Transform in [`reset_transform()`](tack/links/runtime.py#L253).
	- Otherwise: resolve the target from `current_transform`, then apply the enabled Translation/Rotation components. A Child-only move is therefore corrected when Allow Child Movement is off.
	- If the target already matches the Child plane within document tolerance, only the cached serials are refreshed. Otherwise the Child geometry is replaced in place.

The command-end handoff is:

```python
pending = _reconcile_runtime_with_metadata(doc)
if not state.states(doc, create=False):
    if not state.has_tracked_states():
        unsubscribe()
    return

_solving = True
try:
    solver.maintain_changed_states(doc, pending)
finally:
    _solving = False
```

The complete handler is [`end_command_handler()`](tack/links/lifecycle.py#L73).

### Document Start:
1. Iterate through all objects in the doc, if they are parents in a tack, determine if the tack can be reconstructed (aka parent and child are present and planes resolve). 
2. The valid and invalid tack states can be reconstructed from the search above, and inserted into sc.sticky.

> **Contradictory summary — what Tack does now:** Startup does perform a full object scan, but it restores only Links whose Parent record and Child reference agree, whose persisted `valid` flag is true, whose endpoint objects exist, and whose planes resolve. Persisted invalid or unresolvable Links are skipped rather than reconstructed into the invalid runtime cache.

#### Document Start (Current):
1. Load the file
	- Rhino loads each object's `Tack.Link`/`Tack.LinkRef` user dictionary metadata itself.
	- [`ReadDocument()`](csharp/TackScriptPlugin/ProjectPlugin.Startup.cs#L97) separately loads Tack's plug-in-owned document JSON. At present that JSON contains display visibility, not relationship records.
2. Schedule restoration
	- Plug-in startup and `EndOpenDocument` call [`ScheduleRestore()`](csharp/TackScriptPlugin/ProjectPlugin.Startup.cs#L129), which asynchronously invokes [`actions.restore_open_documents()`](tack/actions.py#L158).
3. Rebuild each open document's active runtime states
	- [`runtime.restore_document()`](tack/links/runtime.py#L233) first clears all temporary state for the document.
	- [`repository.all_links()`](tack/links/repository.py#L98) scans all document objects and keeps only an agreed Parent record/Child reference pair with `valid=True`.
	- [`state.new_state()`](tack/links/state.py#L122) resolves the Parent and Child planes. A Link that cannot resolve returns no state and is skipped.
4. Restore session services
	- If at least one state was rebuilt, the shared conduit is installed and lifecycle events are subscribed.
	- The document's saved display preference is restored using [`preferences.display_enabled()`](tack/links/preferences.py#L13), and the Tack panel is refreshed.

Current restoration is effectively:

```python
for link in repository.all_links(doc):
    link_state = state.new_state(doc, link)
    if link_state is not None:
        state.set_state(doc, link_state)

if state.states(doc, create=False):
    ensure_conduit(doc, preferences.display_enabled(doc, default_display_enabled))
    lifecycle.subscribe()
```

The complete implementation is [`runtime.restore_document()`](tack/links/runtime.py#L233).

### Dynamic Draw:
1. See if the current command is one that we are allowed to do tack dynamic drawing in.
2. If so, see if the object in question (one being moved) is a parent. 
3. If so, move the child too (doing the display conduit magic that makes it look like both are being moved natively) Note that this "movement" should be filtered by the tack type.

> **Contradictory summary — what Tack does now:** This is broadly correct, except the preview also understands cascading Tacks, ignores a linked Child that Rhino is already transforming directly, and is display-only. The actual Child object is corrected by EndCommand after Rhino commits the Parent transform. Preview is limited to `Drag`, `Move`, `Rotate`, and `Rotate3D`, and is suppressed when the command prompt reports `Copy=Yes`.

#### Dynamic Draw (Current):
1. Track the active native command
	- [`begin_command_handler()`](tack/links/lifecycle.py#L64) passes the English command name to [`LinkedPlaneConduit.command_began()`](tack/display/link_conduit.py#L129).
	- [`NativeTransformPreview._preview_allowed()`](tack/dynamic/native_preview.py#L66) accepts only `drag`, `move`, `rotate`, and `rotate3d`, with Copy off.
2. Read Rhino's live transforms
	- Every `PreDrawObjects`, [`LinkedPlaneConduit.PreDrawObjects()`](tack/display/link_conduit.py#L139) calls [`NativeTransformPreview.update()`](tack/dynamic/native_preview.py#L106).
	- `GetDynamicTransform()` is checked for both Parent and Child endpoints. A Parent's live transform can drive a preview; a Child already being transformed directly is not replaced by a parent-driven preview.
3. Calculate filtered Child previews
	- Every Tack resolves `current_transform` against the transformed Parent plane.
	- Translation/Rotation are filtered with the same transform functions used by the final solver.
4. Settle preview chains
	- A preview transform for one Child becomes the live Parent transform for its outgoing Tack.
	- The preview repeats for at most `len(active states) + 1` passes, allowing Parent → Child → Grandchild drawing without changing document geometry.
5. Draw the result
	- [`suppresses_object()`](tack/dynamic/native_preview.py#L193) prevents Rhino from drawing the Child at its old normal location.
	- [`draw_objects()`](tack/dynamic/native_preview.py#L221) draws the old Child as a locked wireframe and the transformed Child in its preview location.
	- [`LinkedPlaneConduit.DrawOverlay()`](tack/display/link_conduit.py#L230) also draws Tack crosshairs at previewed planes.

The current preview gate is:

```python
_ALLOWED_COMMANDS = {"drag", "move", "rotate", "rotate3d"}

def _preview_allowed(self):
    return self._active_command in _ALLOWED_COMMANDS and _COPY_ENABLED_PATTERN.search(
        str(Rhino.RhinoApp.CommandPrompt or "")
    ) is None
```

The complete class is [`NativeTransformPreview`](tack/dynamic/native_preview.py#L26).

### Saved State (Current):

> **Contradictory summary — what Tack does now:** `sc.sticky` is not the source of truth. Relationship definitions travel with Rhino objects in the `.3dm`; Tack's plug-in document archive currently saves only display visibility; `sc.sticky` contains disposable per-session runtime state.

1. Parent object metadata
	- [`parent.set_links()`](tack/object_metadata/parent.py#L35) stores a compact JSON map under `Tack.Link`.
	- Each [`Link`](tack/links/schema.py#L15) stores ID, creation time, endpoint IDs, both analytic plane definitions, Translation, Rotation, Allow Child Movement, validity, and both parent-local transforms. A flipped Child plane is represented by its plane definition, not the Link.
2. Child object metadata
	- [`child.set_link_ids()`](tack/object_metadata/child.py#L29) stores a compact JSON list of Tack IDs under `Tack.LinkRef`.
	- A Link is active only when the Parent's complete record and the expected Child's ID reference agree.
3. Plug-in document data
	- [`preferences.set_display_enabled()`](tack/links/preferences.py#L19) stores `display_enabled` in Tack's C# document archive.
	- [`WriteDocument()`](csharp/TackScriptPlugin/ProjectPlugin.Startup.cs#L89) writes that generic JSON archive into the `.3dm`.
4. Per-user plug-in settings
	- [`plugin_data.settings()`](tack/core/plugin_data.py#L49) reads the Add options, default visibility, crosshair appearance, and panel display options from the plug-in settings.
5. Temporary session state
	- [`LinkState`](tack/links/state.py#L17) caches resolved planes, endpoint serials, and the busy flag.
	- [`InvalidLinkState`](tack/links/state.py#L32) holds only a removed runtime state and its age so native Undo can reconnect it.
	- [`documents.get_value()`](tack/core/documents.py#L20) stores these values per document beneath one `sc.sticky` registry.

The object metadata has this logical shape (the actual values are compact JSON strings):

```text
Parent.Attributes.UserDictionary["Tack.Link"]
    -> {"a1b2c3d4": {complete Link record}}

Child.Attributes.UserDictionary["Tack.LinkRef"]
    -> ["a1b2c3d4"]
```

### Invalid Tack State (Current):

> **Contradictory summary — what Tack does now:** “Invalid” has two different meanings. A cached invalid runtime state is temporary Undo support and can return when valid metadata returns. A Link marked `valid=False` is persisted on its Parent but is excluded from normal scans and is not automatically retried at document start.

1. Missing or changed metadata
	- Command-end reconciliation calls [`state.cache_state()`](tack/links/state.py#L66), retaining the previous runtime identity for up to 200 command endings.
	- If Undo restores an active Parent record/Child reference pair, reconciliation creates a fresh `LinkState` and removes the cached invalid entry.
2. Missing endpoint or unresolvable plane during maintenance
	- [`_show_invalid_alert()`](tack/links/solver.py#L10) attempts to persist `valid=False`, caches the runtime state, and shows a Rhino warning.
	- The Link then stops participating in solving and drawing.
3. Startup behavior
	- [`active_observed_links()`](tack/links/repository.py#L72) excludes `valid=False` records by default.
	- Startup therefore does not age, retry, or restore those records into the runtime invalid cache.

### Display State (Current):

> **Contradictory summary — what Tack does now:** The same shared conduit hosts persistent crosshairs, panel selection highlighting, and native transform previews across open documents. Each draw event is still filtered back to that event's document and its own runtime states.

1. [`LinkedPlaneConduit`](tack/display/link_conduit.py#L14) is installed once in `sc.sticky`, with one [`NativeTransformPreview`](tack/dynamic/native_preview.py#L26) per document serial number.
2. Every Tack draws both endpoint crosshairs and a dotted line between distinct endpoint origins. Attached endpoint crosshairs overlap, and the zero-length line is omitted.
3. Tack visibility changes crosshairs/highlighting, but the conduit still runs native movement previews while active states exist.
4. Closing a document calls [`close_document_handler()`](tack/links/lifecycle.py#L102), removes that document's runtime/display data, forgets its panel, and unsubscribes globally when no tracked states remain.
