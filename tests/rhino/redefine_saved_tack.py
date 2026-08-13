import os
import sys

sys.modules.pop("common", None)

from common import run_step
from common import sc


PARENT_NAME = "Tack Restore Parent"
CHILD_NAME = "Tack Restore Child"
OUTPUT_PATH_KEY = "TACK_RESTORE_FIXTURE_PATH"


def _named_object(doc, name):
    matches = [
        obj
        for obj in doc.Objects
        if obj is not None and obj.Attributes.Name == name
    ]
    assert len(matches) == 1, "Expected one {!r} object, found {}".format(
        name,
        len(matches),
    )
    return matches[0]


def _clear_tack_metadata(doc, obj, metadata):
    attributes = obj.Attributes.Duplicate()
    changed = False
    for key in (metadata.LINKS_KEY, metadata.PARENT_LINKS_KEY):
        if attributes.UserDictionary.ContainsKey(key):
            attributes.UserDictionary.Remove(key)
            changed = True
    if changed:
        assert doc.Objects.ModifyAttributes(obj.Id, attributes, True)


def _bbox_anchor(obj, bbox_analysis):
    anchors = dict(bbox_analysis.anchors(obj))
    return (
        bbox_analysis.ANCHOR_TYPE,
        bbox_analysis.CENTER_INDEX,
        anchors[bbox_analysis.CENTER_INDEX],
    )


def redefine_saved_tack():
    import Rhino
    import tack

    tack.reload()
    import tack.analysis.bbox as bbox_analysis
    from tack import metadata
    from tack import runtime
    from tack import utils

    doc = sc.doc
    assert doc is not None
    output_path = os.environ[OUTPUT_PATH_KEY]
    parent = _named_object(doc, PARENT_NAME)
    child = _named_object(doc, CHILD_NAME)

    runtime.stop_runtime(doc)
    _clear_tack_metadata(doc, parent, metadata)
    _clear_tack_metadata(doc, child, metadata)

    link_id = metadata.write_link(
        doc,
        parent.Id,
        child.Id,
        _bbox_anchor(parent, bbox_analysis),
        _bbox_anchor(child, bbox_analysis),
    )
    assert link_id is not None
    saved_link = metadata.read_link(child, link_id)
    assert saved_link is not None

    settings = {
        "advanced_reconciliation": True,
        "debug": False,
        "allow_child_movement": True,
    }
    utils.set_document_settings(doc, settings)
    utils.set_document_display_enabled(doc, False)

    options = Rhino.FileIO.FileWriteOptions()
    options.SuppressDialogBoxes = True
    assert doc.Write3dmFile(output_path, options)
    assert os.path.isfile(output_path)

    return {
        "name": "redefine_saved_tack",
        "fixture_path": output_path,
        "link_id": link_id,
        "link_version": saved_link["version"],
        "parent_id": str(parent.Id),
        "child_id": str(child.Id),
        "settings": settings,
        "display_enabled": False,
    }


run_step("redefine_saved_tack", redefine_saved_tack, send_done=True)
