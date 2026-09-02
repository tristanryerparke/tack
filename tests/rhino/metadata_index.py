"""Verify the document relationship index owns restore and clear traversal."""

import json
import sys

import System
import Rhino
import scriptcontext as sc

sys.modules.pop("common", None)
from common import add_circle, circular_plane_definition, cleanup, mark_test_object, run_test


class _NoScanObjects:
    def __init__(self, objects):
        self._objects = objects

    def Find(self, object_id):
        return self._objects.Find(object_id)

    def __getattr__(self, name):
        return getattr(self._objects, name)

    def __iter__(self):
        raise AssertionError("relationship index must not enumerate document objects")


class _NoScanDocument:
    def __init__(self, doc):
        self.Strings = doc.Strings
        self.Objects = _NoScanObjects(doc.Objects)



def verify_metadata_index():
    from tack import plane_link_metadata

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

        indexed = plane_link_metadata.all_links(_NoScanDocument(doc))
        assert {link["link_id"] for link in indexed} == {
            link["link_id"] for link in links
        }
        for link in links:
            assert plane_link_metadata.validate(link)
            assert link in indexed
            for object_id in (link["parent_id"], link["child_id"]):
                obj = doc.Objects.Find(System.Guid(str(object_id)))
                assert obj.Attributes.UserDictionary.ContainsKey(
                    plane_link_metadata.LINKS_KEY
                )
                assert plane_link_metadata.read_link(obj, link["link_id"]) == link

        raw_index = json.loads(
            doc.Strings.GetValue(
                plane_link_metadata.INDEX_SECTION,
                plane_link_metadata.INDEX_ENTRY,
            )
        )
        assert raw_index["version"] == plane_link_metadata.INDEX_VERSION
        assert raw_index["links"] == {link["link_id"]: link for link in links}

        assert plane_link_metadata.clear(_NoScanDocument(doc))
        assert not plane_link_metadata.all_links(_NoScanDocument(doc))
        assert not doc.Objects.Find(unrelated).Attributes.UserDictionary.ContainsKey(
            plane_link_metadata.LINKS_KEY
        )
        assert str(
            doc.Objects.Find(unrelated).Attributes.UserDictionary[
                "Tack.Test.Unrelated"
            ]
        ) == "preserve"
        return {"link_count": len(links), "index_entries": len(raw_index["links"])}
    finally:
        cleanup(doc)


run_test("metadata_index", verify_metadata_index)
