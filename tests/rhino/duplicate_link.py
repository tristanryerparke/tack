"""Verify a new Tack replaces an existing relationship between the same objects."""

import sys

import Rhino
import scriptcontext as sc

sys.modules.pop("common", None)
from common import add_circle, circular_plane_definition, cleanup, run_test


def verify_duplicate_link_replacement():
    from tack import plane_link
    from tack import plane_link_metadata

    doc = sc.doc
    cleanup(doc)
    try:
        parent_id = add_circle(doc, Rhino.Geometry.Point3d(0, 0, 0))
        child_id = add_circle(doc, Rhino.Geometry.Point3d(8, 0, 0))
        first = plane_link_metadata.create(
            doc,
            parent_id,
            child_id,
            circular_plane_definition(parent_id),
            circular_plane_definition(child_id),
            False,
        )
        assert first is not None, "Could not create the first Tack"
        assert plane_link.install(doc, first) is not None

        replacement = plane_link_metadata.create(
            doc,
            child_id,
            parent_id,
            circular_plane_definition(child_id),
            circular_plane_definition(parent_id),
            True,
        )
        assert replacement is not None, "Could not create the replacement Tack"
        assert plane_link.install(doc, replacement) is not None

        links = plane_link_metadata.all_links(doc)
        assert links == [replacement]
        assert plane_link_metadata.read_link(doc, first["link_id"]) is None
        assert set(plane_link.states(doc)) == {replacement["link_id"]}
        return {"link_count": len(links), "replacement_inverted": links[0]["inverted"]}
    finally:
        cleanup(doc)


if __name__ == "__main__":
    run_test("duplicate_link", verify_duplicate_link_replacement)
