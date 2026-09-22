"""Verify a new Tack replaces an existing relationship between the same objects."""

import sys

import Rhino
import scriptcontext as sc

sys.modules.pop("common", None)
from common import add_circle, circular_plane_definition, cleanup, run_test


def verify_duplicate_link_replacement():
    from tack.links import (
        repository,
        runtime,
        state,
    )

    doc = sc.doc
    cleanup(doc)
    try:
        parent_id = add_circle(doc, Rhino.Geometry.Point3d(0, 0, 0))
        child_id = add_circle(doc, Rhino.Geometry.Point3d(8, 0, 0))
        first = repository.create(
            doc,
            parent_id,
            child_id,
            circular_plane_definition(parent_id),
            circular_plane_definition(child_id),
        )
        assert first is not None, "Could not create the first Tack"
        assert runtime.install(doc, first) is not None

        replacement = repository.create(
            doc,
            child_id,
            parent_id,
            circular_plane_definition(child_id),
            circular_plane_definition(parent_id),
            allow_child_movement=True,
        )
        assert replacement is not None, "Could not create the replacement Tack"
        assert runtime.install(doc, replacement) is not None

        links = repository.all_links(doc)
        assert links == [replacement]
        assert repository.read_link(doc, first["link_id"]) is None
        assert set(state.states(doc)) == {replacement["link_id"]}
        return {
            "link_count": len(links),
            "replacement_allows_child_movement": links[0]["allow_child_movement"],
        }
    finally:
        cleanup(doc)


if __name__ == "__main__":
    run_test("duplicate_link", verify_duplicate_link_replacement)
