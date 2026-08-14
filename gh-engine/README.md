# TackGH proof of concept

Goal: test a Tack relationship where a generated, hidden Grasshopper document owns the child update.

## Scripts

1. `add_tack_gh.py` — interactive wizard:
   - pick parent Brep/box
   - pick parent vertex index
   - pick child Brep/box
   - pick child vertex index
   - creates and activates a GH document

2. `example_translation_smoke.py` — non-interactive smoke script:
   - creates two boxes
   - creates a TackGH link on vertex `0 -> 0`
   - moves the parent
   - solves the GH document
   - verifies the child kept the same anchor vector

3. `check_active_link_after_parent_move.py` — active-document auto-update probe:
   - reads the most recent TackGH sticky link
   - moves the parent
   - waits for Grasshopper to notice naturally
   - reports `AUTO PASS` or `AUTO MISS`, then forces one GH solve for comparison

4. `check_hidden_command_move_update.py` — hidden-window command-move probe:
   - creates a hidden TackGH link
   - runs a real Rhino `_Move` command on the parent
   - verifies the hidden GH document updates the child without a manual solve

5. `reset_tack_gh.py` — reset script:
   - removes generated active GH documents
   - disables TackGH display conduit
   - unsubscribes TackGH runtime handlers
   - clears TackGH sticky records

## Current architecture

Grasshopper is hidden by default and all generated GH preview objects are disabled. Components keep their default names; readable metadata lives on one-component Grasshopper groups.

The only visible relationship display is a Tack-style Rhino display conduit drawing the parent vertex, child vertex, and dotted relationship line.

Generated `.ghx` definitions are saved next to the active `.3dm` file when the Rhino document has been saved. Unsaved Rhino documents fall back to `gh-engine/generated/`.

Child write-back is owned by Rhino/Grasshopper's native Content Cache component:

```text
Parent Brep + Index -> Deconstruct Brep vertices -> Parent point
Child Brep + Index  -> Deconstruct Brep vertices -> Child point
Parent point + stored initial vector -> target child anchor
Child point -> target child anchor -> correction vector
Correction vector -> translated child geometry
Child ModelObject(Guid) + translated child geometry -> Model Object
Model Object + ModelAction.Push -> Content Cache
```

Python still creates the hidden `GH_Document`, hides previews, keeps the Tack display conduit active, and expires the GH document after Rhino commands. Content Cache Push is scheduled from Rhino Idle because it cannot modify the model while another Rhino command is still running.

## Run

```bash
uv run rhino-watch gh-engine/add_tack_gh.py --debug
```

or:

```bash
uv run rhino-watch gh-engine/example_translation_smoke.py --debug
```

After creating an interactive link, probe automatic parent-change updates with:

```bash
uv run rhino-watch gh-engine/check_active_link_after_parent_move.py --debug
```

Probe hidden-window command updates with:

```bash
uv run rhino-watch gh-engine/check_hidden_command_move_update.py --debug
```

Reset the stage between interactive runs with:

```bash
uv run rhino-watch gh-engine/reset_tack_gh.py --debug
```
