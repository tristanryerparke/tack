# RhinoWorks Adjustable Hole Size — Research Summary

## Overview

RhinoWorks’ adjustable hole functionality appears to have been based on **history-free, constraint-aware direct modeling**, not on Rhino’s `MakeHole` command history or on replaying the original hole-creation operation.

The strongest evidence comes from LEDAS’ own descriptions of RhinoWorks and its underlying **LGS 3D geometric constraint solver**. RhinoWorks could resize cylindrical holes in geometry imported from other CAD systems, which means it could not depend on knowing how the hole was originally created.

In practice, the system seems to have:

1. Recognized analytic geometry in the current Rhino BRep.
2. Detected geometric relationships such as concentricity, tangency, perpendicularity, and equal radii.
3. Applied a radial driving dimension to the cylindrical hole surface.
4. Used LGS 3D to solve the updated geometric constraint system.
5. Locally modified the affected BRep faces, trims, and edges to match the solved geometry.

This is fundamentally different from a feature-history model such as SolidWorks or Fusion 360.

---

## Key Conclusion

A RhinoWorks hole was not treated as:

```text
Original solid
    +
MakeHole operation
    +
hole radius / depth
        ↓
replay MakeHole
        ↓
new solid
```

Instead, it was much closer to:

```text
Current BRep
    ↓
recognize cylindrical hole geometry
    ↓
infer geometric constraints
    ↓
change cylinder radius
    ↓
solve constraints
    ↓
locally update BRep topology
```

This allowed RhinoWorks to edit holes even when the object was imported from STEP or another CAD system and had no Rhino construction history.

---

## Evidence from LEDAS

LEDAS described RhinoWorks as a **variational direct modeling** system rather than a history-tree modeler.

The system was built around the LEDAS **LGS 3D** geometric constraint solver.

LGS 3D supported geometric entities including:

- planes
- cylinders
- spheres
- circles
- curves
- surfaces

It also supported dimensional and geometric constraints including:

- radius
- coincidence
- concentricity
- perpendicularity
- parallelism
- tangency
- equal radii

LEDAS specifically described radial driving dimensions that could modify the radii of:

- cylindrical surfaces
- fillets
- holes

This strongly indicates that a hole radius was handled as a geometric degree of freedom on the existing cylindrical surface rather than as a parameter of a stored `MakeHole` feature.

Sources:

- LEDAS press release on RhinoWorks / direct modeling:
  https://ledas.com/group/press_releases?press_num=144
- LGS 3D v3 / variational direct modeling:
  https://ledas.com/news/134-ledas-ships-lgs-3d-v3-for-variational-direct-modeling-developers/
- RhinoWorks announcement / variational direct modeling:
  https://ledas.com/news/153-rhinoworks-from-ledas-revolutionizes-direct-modeling/
- LEDAS / direct-modeling discussion:
  https://isicad.net/articles.php?article_num=14805

---

## Likely Internal Representation of a Simple Hole

Consider a through-hole in a solid:

```text
        planar top face
    ┌──────────────────────┐
    │        ╭────╮        │
    │        │    │        │
    │        │    │        │
    └────────╰────╯────────┘
        planar bottom face

              ↑
        cylindrical face
          radius = 5
```

RhinoWorks could inspect the BRep and recognize:

```text
Brep
 │
 ├── Plane A
 ├── Plane B
 ├── Cylinder C
 │      axis = (...)
 │      radius = 5
 │
 ├── circular trim edges
 │
 └── BRep topology
```

The system could then infer relationships such as:

```text
Cylinder C axis ⟂ Plane A
Cylinder C axis ⟂ Plane B

top trim circle concentric with Cylinder C
bottom trim circle concentric with Cylinder C

trim-circle radius = cylinder radius
```

The hole radius could then be represented by a driving dimensional constraint:

```text
R = 5 mm
```

Changing it to:

```text
R = 8 mm
```

would cause the geometric solver to find a new valid configuration.

---

## What Changes in the BRep

For a simple cylindrical through-hole, the planar faces do not need to move.

Instead, the affected geometry is approximately:

```text
BEFORE

Top plane
    inner trim loop = circle R=5

Cylinder
    radius = 5

Bottom plane
    inner trim loop = circle R=5
```

After changing the driving radius:

```text
AFTER

Top plane
    inner trim loop = circle R=8

Cylinder
    radius = 8

Bottom plane
    inner trim loop = circle R=8
```

The underlying planar surfaces can remain unchanged.

The cylindrical surface changes radius, and the intersections between the resized cylinder and the surrounding surfaces determine the new edges and trim curves.

This is a **local BRep modification**, not a reconstruction of the complete model from an earlier state.

---

## Split Cylindrical Hole Faces

One particularly useful clue from LEDAS is that RhinoWorks improved support for:

> cylindrical holes that consist of several parts

This implies that RhinoWorks did not simply resize a single selected cylinder face.

Imported CAD models frequently contain what is visually one hole but is topologically represented by multiple cylindrical faces:

```text
           ┌───────────────┐
           │               │
           │   Face C1     │
           │               │
           ├───────────────┤
           │               │
           │   Face C2     │
           │               │
           └───────────────┘
```

RhinoWorks could infer relationships such as:

```text
C1.axis == C2.axis

C1.radius == C2.radius
```

or equivalent concentric/equal-radius constraints.

A single radius change could therefore update all related cylindrical faces.

This is much closer to **design-intent recognition** than to simple surface scaling.

---

## Why Imported Geometry Could Be Edited

A major implication of the RhinoWorks architecture is that it did not require original CAD feature history.

A cylindrical hole imported from:

- SolidWorks
- Inventor
- CATIA
- STEP
- IGES
- another Rhino file

could still be recognized geometrically.

For a simple cylindrical hole, the final BRep already contains most of the information needed to infer the design intent:

```text
surface type = cylinder
axis = known
radius = known
adjacent surfaces = known
trim loops = known
```

RhinoWorks therefore did not need to know whether the original hole came from:

```text
MakeHole
```

or:

```text
Cylinder + BooleanDifference
```

or:

```text
HoleWizard
```

The resulting BRep geometry was enough.

---

## Comparison with Rhino `FilletEdge Edit`

Rhino’s editable `FilletEdge` behavior is closer to **feature replay**.

Conceptually:

```text
construction state
    +
selected edges
    +
radius = 5
    +
fillet options
        ↓
FilletEdge
        ↓
resulting Brep
```

Changing the radius causes Rhino to regenerate the fillet using stored construction information.

RhinoWorks worked differently:

```text
CURRENT BREP
    ↓
recognize cylinder / planes / constraints
    ↓
radius = 5
    ↓
change radius to 8
    ↓
constraint solver
    ↓
modify current BRep
```

The RhinoWorks method is therefore **history-free**.

---

## Comparison with Rhino `MakeHole`

Rhino’s built-in `MakeHole` does not appear to retain a reusable editable feature record comparable to `FilletEdge Edit`.

Rhino can manipulate holes later using commands such as:

- `MoveHole`
- `CopyHole`
- `RotateHole`
- `ArrayHole`
- `UntrimHoles`

but those commands largely operate on the resulting BRep topology and trim boundaries.

RhinoWorks went substantially further by recognizing the geometry of the hole and applying a dimensional constraint to it.

Thus:

```text
Rhino MakeHole:
    perform trim / Boolean operation
    resulting Brep contains hole topology

RhinoWorks:
    inspect existing hole topology
    recognize cylindrical geometry
    infer design relationships
    dimension / constrain it
    modify it directly
```

---

## Role of LGS 3D

The important subsystem was not merely a hole-resizing command.

RhinoWorks was built on top of the **LGS 3D variational geometric constraint solver**.

The likely architecture was:

```text
                     RHINO BREP
                         │
                         ▼
              ┌─────────────────────┐
              │ Geometry recognition│
              │                     │
              │ plane               │
              │ cylinder            │
              │ sphere              │
              │ etc.                │
              └──────────┬──────────┘
                         │
                         ▼
              ┌─────────────────────┐
              │ Constraint inference│
              │                     │
              │ concentric          │
              │ tangent             │
              │ perpendicular       │
              │ equal-radius        │
              │ coincidence         │
              └──────────┬──────────┘
                         │
                         ▼
              ┌─────────────────────┐
              │       LGS 3D        │
              │                     │
              │ Radius = 5 → 8      │
              │ solve system        │
              └──────────┬──────────┘
                         │
                         ▼
              ┌─────────────────────┐
              │ Local BRep update   │
              │                     │
              │ resize surfaces     │
              │ recompute edges     │
              │ recompute trims     │
              └──────────┬──────────┘
                         │
                         ▼
                    UPDATED BREP
```

This is broadly similar to the class of systems later marketed as:

- variational direct modeling
- synchronous modeling
- constraint-aware direct editing

rather than traditional feature-tree parametric modeling.

---

## Could This Be Recreated in RhinoCommon?

For simple cases, probably yes.

A RhinoCommon prototype could:

1. Let the user select a cylindrical Brep face.
2. Use the selected `BrepFace` to identify the underlying cylinder.
3. Read:
   - axis
   - radius
   - neighboring faces
4. Construct a new cylinder with the same axis and a different radius.
5. Recompute intersections with adjacent faces.
6. Rebuild the affected trims / edges.
7. Replace the old Brep.

Conceptually:

```text
Select cylindrical face
        ↓
TryGetCylinder()
        ↓
axis + radius
        ↓
radius = new value
        ↓
construct replacement cylinder
        ↓
intersect with adjacent faces
        ↓
rebuild local BRep region
```

For a simple through-hole bounded by two planes, this is relatively constrained.

---

## Expected Difficulty by Hole Type

Approximate implementation difficulty:

```text
simple planar through-hole       relatively easy

blind cylindrical hole           moderate

counterbore                      moderate

countersink                      moderate

hole through angled faces        harder

split cylindrical faces          harder

hole intersecting fillets        much harder

hole bounded by freeform NURBS   substantially harder

changes causing topology change  very hard
```

The hard part is not changing the mathematical cylinder radius.

The difficult part is robustly rebuilding the surrounding BRep topology while preserving geometric relationships and handling topology changes.

That is where RhinoWorks’ constraint solver and direct-modeling layer provided most of their value.

---

## Confirmed vs. Inferred Details

### Strongly supported by LEDAS documentation

- RhinoWorks used history-free variational direct modeling.
- It used the LGS 3D geometric constraint solver.
- Cylindrical surface radii could be controlled by driving dimensions.
- Holes and fillets were specifically mentioned as editable cylindrical geometry.
- Imported geometry could be modified.
- Geometric relationships such as concentricity, perpendicularity, tangency, and equal radii were automatically recognized.
- Multi-part cylindrical holes were supported.

### Inferred implementation details

The exact internal RhinoWorks source code is not publicly available, so the following details are inferred from the documented behavior and standard BRep modeling techniques:

- exact format of its face/constraint graph
- exact method used to replace or re-trim Rhino BRep faces
- exact order in which surfaces, intersections, edges, and trims were reconstructed
- whether a complete local region was rebuilt or individual topology entities were mutated in place

The overall architecture, however, is strongly supported by LEDAS’ technical descriptions.

---

## Main Takeaway

The adjustable hole functionality in RhinoWorks was likely **not a hidden `MakeHole` feature**.

It was a general-purpose direct-modeling operation:

```text
recognize geometry
    +
recover geometric relationships
    +
apply dimensional constraint
    +
solve
    +
modify BRep locally
```

That is why RhinoWorks could resize holes in arbitrary and imported geometry without relying on construction history.

For reproducing similar behavior in modern Rhino, the most important technical problem is therefore not HistoryRecord access. It is building a robust **local BRep editing / face replacement system**, optionally combined with geometric constraint inference.
