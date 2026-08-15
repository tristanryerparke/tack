# AssemblyGH framework

Goal: create SolidWorks-style mate commands that prompt for Rhino objects/sub-objects, record mate data, generate a Grasshopper/Kangaroo definition, then use Rhino Content Cache to replace moving Rhino objects.

## Current source of truth

Body and mate records live in the active session:

```python
scriptcontext.sticky["AssemblyGH.ActiveSession"]
```

A body record is a Rhino object plus feature metadata:

```text
object_id + circular Brep edge index/indices
```

A mate record references body features and declares the relationship to maintain. The generated GH document is an output artifact. Individual commands should not hand-edit existing GH graphs directly. They should:

1. get/create the active session
2. prompt for body/sub-object features
3. append one mate record
4. merge involved bodies/features into the body registry
5. rebuild the GH definition from body + mate records
6. save/solve the generated definition

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

## Tack ethos

The Brep shape is payload, not source of truth. Mates are defined by metadata and live feature resolution:

```text
object_id + edge_indices -> current circular edge center/axis -> mate feature
```

Content Cache should write absolute solved poses derived from live feature locations, not incremental transforms or stale geometry snapshots.

## Next implementation step

Generalize `generate_definition.py` so every mate emits goals against body feature refs instead of bespoke eccentric-joint wiring:

```text
body feature refs -> mate goals -> shared solver -> per-body absolute transforms -> one Content Cache push
```
