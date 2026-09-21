"""Verify endpoint object metadata owns the relationship graph."""

import sys

import Rhino
import scriptcontext as sc
import System

sys.modules.pop("common", None)
from common import add_circle, circular_plane_definition, cleanup, run_test


def verify_metadata_index():
    from tack.core import plugin_data
    from tack.links import object_store, repository, schema

    doc = sc.doc
    cleanup(doc)
    try:
        parent_a = add_circle(doc, Rhino.Geometry.Point3d(0, 0, 0))
        child_a = add_circle(doc, Rhino.Geometry.Point3d(8, 0, 0))
        parent_b = add_circle(doc, Rhino.Geometry.Point3d(0, 8, 0))
        child_b = add_circle(doc, Rhino.Geometry.Point3d(8, 8, 0))
        unrelated = add_circle(doc, Rhino.Geometry.Point3d(20, 20, 0))
        unrelated_object = doc.Objects.Find(unrelated)
        attributes = unrelated_object.Attributes.Duplicate()
        attributes.UserDictionary.Set("Tack.Test.Unrelated", "preserve")
        assert doc.Objects.ModifyAttributes(unrelated, attributes, True)

        links = [
            repository.create(
                doc,
                parent_a,
                child_a,
                circular_plane_definition(parent_a),
                circular_plane_definition(child_a),
                False,
            ),
            repository.create(
                doc,
                parent_b,
                child_b,
                circular_plane_definition(parent_b),
                circular_plane_definition(child_b),
                True,
            ),
        ]
        assert all(links), "Could not persist analytic-plane links"

        for link in links:
            assert schema.validate(link)
            parent = doc.Objects.Find(System.Guid.Parse(str(link["parent_id"])))
            child = doc.Objects.Find(System.Guid.Parse(str(link["child_id"])))
            assert parent.Attributes.UserDictionary.ContainsKey(object_store.LINKS_KEY)
            assert object_store.read_parent_links(parent)[link["link_id"]] == link
            assert child.Attributes.UserDictionary.ContainsKey(
                object_store.LINK_REFS_KEY
            )
            assert link["link_id"] in object_store.read_link_refs(child)
            assert not child.Attributes.UserDictionary.ContainsKey(
                object_store.LINKS_KEY
            )

        indexed = repository.all_links(doc)
        assert {link["link_id"] for link in indexed} == {
            link["link_id"] for link in links
        }
        document_data = plugin_data.document_data(doc)
        assert "links" not in document_data
        assert all("version" not in link for link in links)

        assert repository.clear(doc)
        assert not repository.all_links(doc)
        for object_id in (parent_a, child_a, parent_b, child_b):
            obj = doc.Objects.Find(System.Guid.Parse(str(object_id)))
            assert not obj.Attributes.UserDictionary.ContainsKey(object_store.LINKS_KEY)
            assert not obj.Attributes.UserDictionary.ContainsKey(
                object_store.LINK_REFS_KEY
            )
        assert (
            str(
                doc.Objects.Find(unrelated).Attributes.UserDictionary[
                    "Tack.Test.Unrelated"
                ]
            )
            == "preserve"
        )
        return {"link_count": len(links), "index_entries": len(indexed)}
    finally:
        cleanup(doc)


if __name__ == "__main__":
    run_test("metadata_index", verify_metadata_index)
