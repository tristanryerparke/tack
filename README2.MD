> In welding, you can loosely attach parts together with a set of small welds called tacks. Tack allows the same functionality in rhino.

Tack is a Rhino plugin that allows you to connect objects through analytical means. In some ways it mirrors the parent-child system we see in blender and other animation softwares (and Bongo). The core difference is that tack maintains a plane-to-plane tranformation matrix between two rhino objects. Each of those planes is derived analytically from the object. For instance: A Brep or Polyline vertex defines the plane center, and two other vertices tell Tack where to find those planes when a command ends. These vertcies are referenced by their saved indices, so tack finds those points your model and then performs its calculation to update the child's location. If you move the parent, the child will be moved to maintain the plane-to-plane relationship you originally set.

Tack aims to be totally compatible with rhino's non-parametric editing workflow, while providing the most basic functionalities of assembly linkage. For instance, when adding a tack between a bolt (child) and a hole in a polysurface (parent), the following apply:
- Use `_Move` on the polysurface, the bolt will move with it.
- Use `_MoveHole` on that hole, and the bolt will move with the hole.

 