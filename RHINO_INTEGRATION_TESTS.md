.# Rhino integration tests for Tack

## Goal

Test Tack through Rhino's real document and command pipeline rather than only testing isolated Python functions.

The important case is:

1. Install Tack's event handlers.
2. Create or open a known parent/child fixture.
3. Run a real Rhino command such as `Move` through `rhinoscriptsyntax.Command`.
4. Let Tack's callbacks respond normally.
5. Assert that the child geometry moved correctly.
6. Capture Tack's debug output.
7. Shut down the watcher cleanly.

This tests the actual `BeforeTransformObjects`, replacement, add, delete, and undo-related paths.

## `run-in-rhino` workflow

`run-in-rhino` provides a controllable server API:

```python
from run_in_rhino import start_server

watcher = start_server()
try:
    watcher.run_file("tests/rhino/install_tack.py")
    watcher.run_file("tests/rhino/test_move.py")
finally:
    watcher.finish()
    watcher.wait()
```

`start_server()` starts the WebSocket server without running a file. `run_file()` executes a Python file inside Rhino. `finish()` runs the Rhino-side `send_done.py` utility, which sends the completion message and allows the server to close.

## Rhino-side test shape

A test file can use real Rhino commands:

```python
import rhinoscriptsyntax as rs

rs.SelectObject(parent_id)
assert rs.Command("_Move 0,0,0 10,0,0", echo=False)
```

The test should then read the child vertex or frame and assert its expected position using Rhino's model tolerance.

Use `rs.Command` rather than `doc.Objects.Transform` when testing user-command behavior. `BeforeTransformObjects` is intended for Rhino transform commands and is not guaranteed to fire for direct `ObjectTable.Transform` calls.

## Output and diagnostics

Tack's callbacks can report debug output while the watcher is live:

```python
from rhino_watcher import websocket_output_sync

with websocket_output_sync():
    print("running parent move test")
    # Install or invoke Tack code here.
```

For synchronous Rhino event callbacks, `websocket_output_sync()` is the simplest option. `websocket_output_deferred()` avoids waiting on the network in the callback, but the deferred queue must be drained before sending the final done message.

Tests should print explicit result markers, for example:

```text
PASS test_parent_move_translates_child
FAIL test_parent_replace_preserves_link: ...
```

## Suggested test groups

### Pure RhinoCommon tests

- Vertex matching and tolerance behavior
- Frame construction from vertices and edges
- Plane and transform calculations
- Metadata serialization and deserialization
- Topology-based vertex remapping

### Document integration tests

- Parent `Move` translates the child
- Parent `Rotate` carries the child frame
- Multiple objects transformed together
- Parent replacement preserves the relationship
- Child replacement preserves the relationship
- Deleting either object breaks or removes the relationship cleanly
- Undo and redo do not create duplicate handlers or duplicate corrections
- Topology changes remap a linked vertex when possible
- Ambiguous or missing vertices break the link safely

## Fixture and cleanup rules

Each test should use deterministic geometry and record its object IDs. Cleanup belongs in `finally` blocks:

1. Stop Tack's runtime.
2. Delete test objects or restore the document state.
3. Disable any display conduits.
4. Clear temporary metadata if necessary.
5. Only then send the server done message.

A fresh test document is preferable. If tests use the active document, they should use unique layers or object names and never delete unrelated user geometry.

## Recommended layout

```text
tests/
  test_pure.py
  rhino/
    install_tack.py
    test_parent_move.py
    test_parent_rotate.py
    test_replacement.py
    test_undo_redo.py
    fixtures.py
```

Normal Python tests can cover pure calculations. Rhino-side tests should be reserved for behavior requiring RhinoCommon, `RhinoDoc`, real commands, document events, object replacement, or display conduits.

## Known limitations

- Rhino must be running with RhinoCode available.
- Rhino event handlers execute on Rhino's UI thread; callbacks must stay short.
- `BeforeTransformObjects` does not cover every possible geometry edit or undo/redo path.
- Output transport is diagnostic; numerical assertions are the actual test result.
- A future runner could send structured JSON results and return a non-zero external status for failed Rhino tests.
