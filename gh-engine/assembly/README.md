# AssemblyGH framework

Goal: create SolidWorks-style mate commands that prompt for Rhino objects/sub-objects, record mate data, generate a Grasshopper/Kangaroo definition, then use Rhino Content Cache to replace moving Rhino objects.

## Current source of truth

Mate records live in the active session:

```python
scriptcontext.sticky["AssemblyGH.ActiveSession"]
```

The generated GH document is an output artifact. Individual commands should not hand-edit existing GH graphs directly. They should:

1. get/create the active session
2. prompt for mate references
3. append one mate record
4. rebuild the GH definition from all records
5. save/solve the generated definition

## Commands

Run only when ready to test in Rhino:

```bash
uv run rhino-watch gh-engine/assembly_start.py --debug
uv run rhino-watch gh-engine/assembly_add_eccentric_joint.py --debug
uv run rhino-watch gh-engine/assembly_show.py --debug
uv run rhino-watch gh-engine/assembly_solve.py --debug
uv run rhino-watch gh-engine/assembly_reset.py --debug
```

## Eccentric joint mate intent

This represents a linked crank-slider, not cam contact:

```text
shaft axis + angle driver
↓
rotating eccentric pin
↓
fixed-length connecting rod
↓
piston pin constrained to slider axis
↓
Content Cache writes the piston and optionally the rod
```

## Next implementation step

Replace the current mate-plan panels in `generate_definition.py` with real per-mate emitters:

```text
eccentric_joint record -> Kangaroo goals + solver + Content Cache writeback
```
