"""Verify endpoint object metadata owns the relationship graph."""

import sys

import Rhino
import System
import scriptcontext as sc

sys.modules.pop("common", None)
from common import add_circle, circular_plane_definition, cleanup, run_test


def verify_metadata_index():
    from tack import plane_link_metadata
    from tack import plugin_data

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
            plane_link_metadata.create(
                doc,
                parent_a,
                child_a,
                circular_plane_definition(parent_a),
                circular_plane_definition(child_a),
                False,
            ),
            plane_link_metadata.create(
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
            assert plane_link_metadata.validate(link)
            for object_id in (link["parent_id"], link["child_id"]):
                obj = doc.Objects.Find(System.Guid.Parse(str(object_id)))
                assert obj.Attributes.UserDictionary.ContainsKey(
                    plane_link_metadata.LINKS_KEY
                )
                assert plane_link_metadata.read_links(obj)[link["link_id"]] == link

        indexed = plane_link_metadata.all_links(doc)
        assert {link["link_id"] for link in indexed} == {
            link["link_id"] for link in links
        }
        document_data = plugin_data.document_data(doc)
        assert "links" not in document_data
        assert all("version" not in link for link in links)

        assert plane_link_metadata.clear(doc)
        assert not plane_link_metadata.all_links(doc)
        for object_id in (parent_a, child_a, parent_b, child_b):
            obj = doc.Objects.Find(System.Guid.Parse(str(object_id)))
            assert not obj.Attributes.UserDictionary.ContainsKey(
                plane_link_metadata.LINKS_KEY
            )
        assert str(
            doc.Objects.Find(unrelated).Attributes.UserDictionary[
                "Tack.Test.Unrelated"
            ]
        ) == "preserve"
        return {"link_count": len(links), "index_entries": len(indexed)}
    finally:
        cleanup(doc)


if __name__ == "__main__":
    run_test("metadata_index", verify_metadata_index)
