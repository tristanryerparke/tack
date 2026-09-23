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

> **Contradictory summary — what Tack does now:** Tack has a separate `Allow Child Movement` option and an eight-character hexadecimal Tack ID, not a GUID. `Attach=On` is a one-time full plane alignment: it moves the Child and deliberately saves an exact identity relationship. `Attach=Off` leaves the Child where it is and calculates the initial parent-local relationship. Child movement only decides whether a later Child-only move replaces that relationship or is corrected back to it. The complete Link is saved on the Parent object, a reference is saved on the Child object, and derived runtime data stays session-only.

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
	- [`repository.would_create_cycle()`](tack/links/repository.py#L240) rejects a directed parent-child loop before the Child plane is picked.
	- The Child anchor/plane is picked using the same Rotation-dependent flow as the Parent. Rotation-on selection then offers `Flip`; [`_flip_child_plane()`](tack/prompting/add_flow.py#L39) emits a Child plane definition whose resolver reverses its Z orientation using [`flipped_definition()`](tack/anchors/analytic_plane.py#L137). This is selection data, not a Link flag.
4. Establish the initial relationship in [`actions.add()`](tack/actions.py#L23)
	- Attach on: [`preview_placement()`](tack/prompting/add_flow.py#L159) displays full plane alignment and waits for Enter. The Child geometry is replaced in place, then [`identity_transform_data()`](tack/links/transforms.py#L27) is supplied as the exact saved relationship.
	- Attach off: the Child is not moved. [`repository.create()`](tack/links/repository.py#L248) resolves both planes and calculates their parent-local relationship.
	- In both cases, the relationship is copied into `original_transform` and `current_transform`.
	- Translation and Rotation filter which parts of that target plane are applied later using [`constrained_target_child_plane()`](tack/links/transforms.py#L52).
5. Persist and install the Tack
	- [`repository.create()`](tack/links/repository.py#L248) creates an eight-character ID and an immutable [`Link`](tack/links/schema.py#L16).
	- [`repository.save()`](tack/links/repository.py#L131) writes the complete Link under `Tack.Link` on the Parent and the ID under `Tack.LinkRef` on the Child in one undoable metadata update.
	- [`runtime.install()`](tack/links/runtime.py#L205) resolves both planes into a temporary `LinkState`, installs the display conduit, and subscribes the lifecycle handlers.

Current Link creation is effectively:

```python
relationship_transform = None
if degrees_of_freedom["attach"]:
    transform = preview_placement(doc, child, parent_plane, child_plane)
    transformed_child = transforms.transform_object_in_place(doc, child, transform)
    relationship_transform = transforms.identity_transform_data()

link = repository.create(
    doc,
    parent.Id,
    transformed_child.Id,
    parent_definition,
    child_definition,
    translation=degrees_of_freedom["translation"],
    rotation=degrees_of_freedom["rotation"],
    allow_child_movement=degrees_of_freedom["allow_child_movement"],
    relationship_transform=relationship_transform,
)
```

The complete call is in [`actions.add()`](tack/actions.py#L23).

### EndCommand Handler:
1. Iterate through the tacks in this document's runtime state, first looking through the invalid ones to see if any can be reconstructed.(valid and invalid lists), for each:
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

> **Contradictory summary — what Tack does now:** This now follows the same shape without scanning every document object at EndCommand. It observes active endpoints plus an expiring log of previously associated object IDs, reconstructs resolvable metadata, and topologically orders active Tacks. Runtime serials remain the fast movement test. Every Tack resolves its saved parent-local transform; a Child-only move replaces it only when `Allow Child Movement` is on.

#### EndCommand Handler (Current):
1. Finish the native-command preview
	- [`end_command_handler()`](tack/links/lifecycle.py#L97) tells the shared conduit that the command ended, which clears dynamic sources and previews.
	- A module-level `_solving` flag prevents Tack's own object replacements from recursively starting another solve.
2. Reconcile runtime state with object metadata using [`_reconcile_runtime_with_metadata()`](tack/links/lifecycle.py#L42)
	- [`_observed_links()`](tack/links/lifecycle.py#L25) starts with active endpoints and the object IDs in the recent-object log. Parent records can add their named Child IDs to this narrow scan.
	- When metadata or an endpoint disappears, [`remember_state()`](tack/links/state.py#L54) discards the derived `LinkState` and logs only its Parent and Child IDs.
	- Valid and `valid=False` metadata pairs are retried. A pair whose objects and planes resolve gets a fresh [`LinkState`](tack/links/state.py#L18), and an invalid persisted Link is changed back to `valid=True`.
	- [`age_recent_object_ids()`](tack/links/state.py#L100) removes logged IDs when their age reaches exactly 200 EndCommands.
3. Find changed Tacks using [`changed()`](tack/links/state.py#L157)
	- Parent and Child `RuntimeSerialNumber` values are compared with the serials cached in `LinkState`.
	- If no serial changed and no state was newly reconstructed, `maintain()` is not called.
4. Order and settle changed chains
	- [`ordered_states()`](tack/links/state.py#L111) performs a stable topological sort from Parent to Child.
	- [`maintain_changed_states()`](tack/links/solver.py#L98) walks that order once. Moving an upstream Child changes its serial before its outgoing Tack is reached.
	- New cycles are separately prevented when a Tack is created by [`graph.would_create_cycle()`](tack/links/graph.py#L4).
5. Maintain each changed Tack using [`maintain()`](tack/links/solver.py#L25)
	- Both endpoint objects and both analytic planes are resolved again before anything moves.
	- Child changed without Parent + Allow Child Movement: recalculate and persist `current_transform`. The saved `original_transform` remains available for Reset Transform in [`reset_transform()`](tack/links/runtime.py#L282).
	- Otherwise: resolve the target from `current_transform`, then apply the enabled Translation/Rotation components. A Child-only move is therefore corrected when Allow Child Movement is off.
	- If the target already matches the Child plane within document tolerance, only the cached serials are refreshed. Otherwise the Child geometry is replaced in place.

The command-end handoff is:

```python
pending = _reconcile_runtime_with_metadata(doc)
if state.states(doc, create=False):
    _solving = True
    try:
        solver.maintain_changed_states(doc, pending)
    finally:
        _solving = False

state.age_recent_object_ids(doc)
if not state.has_tracked_states():
    unsubscribe()
```

The complete handler is [`end_command_handler()`](tack/links/lifecycle.py#L97).

### Document Start:
1. Iterate through all objects in the doc, if they are parents in a tack, determine if the tack can be reconstructed (aka parent and child are present and planes resolve). 
2. The valid and invalid tack states can be reconstructed from the search above, and inserted into this document's runtime state.

> **Contradictory summary — what Tack does now:** Startup performs the one full-document scan. Agreed, resolvable Parent records and Child references become active states. Persisted invalid Links are retried and revalidated when they resolve. Unresolvable or incomplete relationships contribute their known object IDs to the 200-EndCommand recovery log.

#### Document Start (Current):
1. Load the file
	- Rhino loads each object's `Tack.Link`/`Tack.LinkRef` user dictionary metadata itself.
	- [`ReadDocument()`](csharp/TackScriptPlugin/ProjectPlugin.Startup.cs#L97) separately loads Tack's plug-in-owned document JSON. At present that JSON contains display visibility, not relationship records.
2. Schedule restoration
	- Plug-in startup and `EndOpenDocument` call [`ScheduleRestore()`](csharp/TackScriptPlugin/ProjectPlugin.Startup.cs#L129), which asynchronously invokes [`actions.restore_open_documents()`](tack/actions.py#L161).
3. Rebuild each open document's runtime tracking
	- [`runtime.restore_document()`](tack/links/runtime.py#L233) clears temporary state, then calls [`observed_metadata()`](tack/links/repository.py#L51) once over all document objects.
	- Agreed Parent record/Child reference pairs are resolved with [`new_state()`](tack/links/state.py#L168), including persisted `valid=False` Links.
	- A formerly invalid Link that resolves is persisted as valid and queued for reconciliation.
	- Dangling or unresolvable records log every known endpoint ID with [`remember_object_ids()`](tack/links/state.py#L44).
4. Restore session services
	- Active states install the shared conduit. Active states or recovery IDs keep lifecycle events subscribed.
	- The document's saved display preference is restored using [`preferences.display_enabled()`](tack/links/preferences.py#L13), and the Tack panel is refreshed.

Current restoration is effectively:

```python
parents, child_owners = repository.observed_metadata(doc.Objects)
links = repository.active_observed_links(
    parents,
    child_owners,
    include_invalid=True,
)
for link in links.values():
    link_state = state.new_state(doc, link)
    if link_state is None:
        state.remember_object_ids(doc, link.parent_id, link.child_id)
    else:
        state.set_state(doc, link_state)
```

The complete implementation is [`runtime.restore_document()`](tack/links/runtime.py#L233).

### Dynamic Draw:
1. See if the current command is one that we are allowed to do tack dynamic drawing in.
2. If so, see if the object in question (one being moved) is a parent. 
3. If so, move the child too (doing the display conduit magic that makes it look like both are being moved natively) Note that this "movement" should be filtered by the tack type.

> **Contradictory summary — what Tack does now:** This is broadly correct, except the preview also understands cascading Tacks, ignores a linked Child that Rhino is already transforming directly, and is display-only. The actual Child object is corrected by EndCommand after Rhino commits the Parent transform. Preview is limited to `Drag`, `Move`, `Rotate`, and `Rotate3D`, and is suppressed when the command prompt reports `Copy=Yes`.

#### Dynamic Draw (Current):
1. Track the active native command
	- [`begin_command_handler()`](tack/links/lifecycle.py#L88) passes the English command name to [`LinkedPlaneConduit.command_began()`](tack/display/link_conduit.py#L129).
	- [`NativeTransformPreview._preview_allowed()`](tack/dynamic/native_preview.py#L66) accepts only `drag`, `move`, `rotate`, and `rotate3d`, with Copy off.
2. Read Rhino's live transforms
	- Every `PreDrawObjects`, [`LinkedPlaneConduit.PreDrawObjects()`](tack/display/link_conduit.py#L139) calls [`NativeTransformPreview.update()`](tack/dynamic/native_preview.py#L106).
	- `GetDynamicTransform()` is checked for both Parent and Child endpoints. A Parent's live transform can drive a preview; a Child already being transformed directly is not replaced by a parent-driven preview.
3. Calculate filtered Child previews
	- Every Tack resolves `current_transform` against the transformed Parent plane.
	- Translation/Rotation are filtered with the same transform functions used by the final solver.
4. Settle preview chains
	- [`NativeTransformPreview.update()`](tack/dynamic/native_preview.py#L106) uses the same [`ordered_states()`](tack/links/state.py#L111) result as the final solver.
	- One Parent-to-Child pass makes each previewed Child transform available to its outgoing Tack, allowing Parent → Child → Grandchild drawing without changing document geometry.
5. Draw the result
	- [`suppresses_object()`](tack/dynamic/native_preview.py#L192) prevents Rhino from drawing the Child at its old normal location.
	- [`draw_objects()`](tack/dynamic/native_preview.py#L220) draws the old Child as a locked wireframe and the transformed Child in its preview location.
	- [`LinkedPlaneConduit.DrawOverlay()`](tack/display/link_conduit.py#L227) also draws Tack crosshairs at previewed planes.

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

> **Contradictory summary — what Tack does now:** Relationship definitions travel with Rhino objects in the `.3dm`. Tack's plug-in document archive currently saves only display visibility. Resolved planes, runtime serials, and recent endpoint IDs are disposable per-session data.

1. Parent object metadata
	- [`parent.set_links()`](tack/object_metadata/parent.py#L35) stores a compact JSON map under `Tack.Link`.
	- Each [`Link`](tack/links/schema.py#L16) stores ID, creation time, endpoint IDs, both analytic plane definitions, Translation, Rotation, Allow Child Movement, validity, and both parent-local transforms. A flipped Child plane is represented by its plane definition, not the Link.
2. Child object metadata
	- [`child.set_link_ids()`](tack/object_metadata/child.py#L29) stores a compact JSON list of Tack IDs under `Tack.LinkRef`.
	- A Link is active only when the Parent's complete record and the expected Child's ID reference agree.
3. Plug-in document data
	- [`preferences.set_display_enabled()`](tack/links/preferences.py#L19) stores `display_enabled` in Tack's C# document archive.
	- [`WriteDocument()`](csharp/TackScriptPlugin/ProjectPlugin.Startup.cs#L89) writes that generic JSON archive into the `.3dm`.
4. Per-user plug-in settings
	- [`plugin_data.settings()`](tack/core/plugin_data.py#L49) reads the Add options, default visibility, crosshair appearance, and panel display options from the plug-in settings.
5. Temporary session state
	- [`LinkState`](tack/links/state.py#L18) caches resolved planes, endpoint serials, and the busy flag.
	- [`recent_object_ids()`](tack/links/state.py#L37) stores only `{object ID: age}` entries for broken or removed Tack endpoints.
	- [`documents.get_value()`](tack/core/documents.py#L20) keeps these disposable values isolated per open document.

The object metadata has this logical shape (the actual values are compact JSON strings):

```text
Parent.Attributes.UserDictionary["Tack.Link"]
    -> {"a1b2c3d4": {complete Link record}}

Child.Attributes.UserDictionary["Tack.LinkRef"]
    -> ["a1b2c3d4"]
```

### Invalid Tack State (Current):

> **Contradictory summary — what Tack does now:** No invalid Link definition is cached in runtime state. Tack retains only recently associated object IDs for 200 EndCommands, then reads any restored relationship definition from object metadata. Persisted `valid=False` records remain the file's source of truth and are actively retried.

1. Missing or changed metadata
	- [`remember_state()`](tack/links/state.py#L54) removes the derived state and logs its Parent and Child object IDs at age zero.
	- If Undo restores an endpoint and its metadata, the next EndCommand scan finds it through those IDs and creates a fresh `LinkState`.
2. Missing endpoint or unresolvable plane during maintenance
	- [`_show_invalid_alert()`](tack/links/solver.py#L12) attempts to persist `valid=False`, logs both endpoint IDs, and shows a Rhino warning.
	- The Link stops solving and drawing, but [`_reconcile_runtime_with_metadata()`](tack/links/lifecycle.py#L42) retries it while its IDs remain in the log.
3. Expiration and startup
	- [`age_recent_object_ids()`](tack/links/state.py#L100) removes stale IDs at 200 EndCommands; it does not delete persisted object metadata.
	- Startup performs a full scan with [`active_observed_links(..., include_invalid=True)`](tack/links/repository.py#L72), so resolvable invalid Links can become valid again after reopening.

### Display State (Current):

> **Contradictory summary — what Tack does now:** The same shared conduit hosts persistent crosshairs, panel selection highlighting, and native transform previews across open documents. Each draw event is still filtered back to that event's document and its own runtime states.

1. One shared [`LinkedPlaneConduit`](tack/display/link_conduit.py#L14) hosts a [`NativeTransformPreview`](tack/dynamic/native_preview.py#L26) for each document serial number.
2. Every Tack draws both endpoint crosshairs and a dotted line between distinct endpoint origins. Attached endpoint crosshairs overlap, and the zero-length line is omitted.
3. Tack visibility changes crosshairs/highlighting, but the conduit still runs native movement previews while active states exist.
4. Closing a document calls [`close_document_handler()`](tack/links/lifecycle.py#L129), removes that document's runtime/display data, forgets its panel, and unsubscribes globally when no tracked states or recovery IDs remain.
