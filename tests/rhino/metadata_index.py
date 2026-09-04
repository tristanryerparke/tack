"""Verify the document relationship index owns restore and clear traversal."""

import sys

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
        self.RuntimeSerialNumber = doc.RuntimeSerialNumber
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
        for object_id in (parent_a, child_a, parent_b, child_b):
            assert not doc.Objects.Find(object_id).Attributes.UserDictionary.ContainsKey(
                "Tack.PlaneLinks.v1"
            )

        indexed = plane_link_metadata.all_links(_NoScanDocument(doc))
        assert {link["link_id"] for link in indexed} == {
            link["link_id"] for link in links
        }
        for link in links:
            assert plane_link_metadata.validate(link)
            assert link in indexed

        assert plane_link_metadata.clear(_NoScanDocument(doc))
        assert not plane_link_metadata.all_links(_NoScanDocument(doc))
        assert not doc.Objects.Find(unrelated).Attributes.UserDictionary.ContainsKey(
            "Tack.PlaneLinks.v1"
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
