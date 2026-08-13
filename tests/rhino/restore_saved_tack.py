import os
import runpy
import sys

sys.modules.pop("common", None)

from common import PROJECT_ROOT
from common import run_step
from common import sc


COMMAND_PATH = os.path.join(PROJECT_ROOT, "commands", "tack_restore.py")
PARENT_NAME = "Tack Restore Parent"
CHILD_NAME = "Tack Restore Child"


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


def restore_saved_tack():
    import Rhino
    import tack

    tack.reload()
    from tack import runtime
    from tack import utils

    doc = sc.doc
    assert doc is not None
    runtime.stop_runtime(doc)
    assert not runtime.states(doc, create=False)

    settings_before = doc.Strings.GetValue(
        utils.DOCUMENT_SETTINGS_SECTION,
        utils.DOCUMENT_SETTINGS_ENTRY,
    )
    display_before = doc.Strings.GetValue(
        utils.DOCUMENT_SETTINGS_SECTION,
        utils.DOCUMENT_DISPLAY_ENTRY,
    )
    assert settings_before is not None
    assert display_before == "hidden"

    utils.set_setting("advanced_reconciliation", False)
    utils.set_setting("allow_child_movement", False)
    assert not utils.ADVANCED_RECONCILIATION
    assert not utils.ALLOW_CHILD_MOVEMENT

    command = runpy.run_path(COMMAND_PATH, run_name="tack_restore_test_command")
    result = command["RunCommand"](False)
    assert result == Rhino.Commands.Result.Success

    from tack import document_runtime
    from tack import metadata
    from tack import runtime
    from tack import utils

    settings_after = doc.Strings.GetValue(
        utils.DOCUMENT_SETTINGS_SECTION,
        utils.DOCUMENT_SETTINGS_ENTRY,
    )
    display_after = doc.Strings.GetValue(
        utils.DOCUMENT_SETTINGS_SECTION,
        utils.DOCUMENT_DISPLAY_ENTRY,
    )
    assert settings_after == settings_before
    assert display_after == display_before
    assert utils.ADVANCED_RECONCILIATION
    assert utils.ALLOW_CHILD_MOVEMENT
    assert not utils.get_setting("debug", doc)
    assert document_runtime.try_get_value(
        doc,
        utils.DISPLAY_ENABLED_KEY,
    ) is False

    saved_links = metadata.all_links(doc)
    assert len(saved_links) == 1
    saved_link = saved_links[0]
    parent = _named_object(doc, PARENT_NAME)
    child = _named_object(doc, CHILD_NAME)
    assert str(parent.Id) == saved_link["parent_id"]
    assert str(child.Id) == saved_link["child_id"]

    states = runtime.states(doc, create=False)
    assert len(states) == 1
    state = next(iter(states.values()))
    assert state["link_id"] == saved_link["link_id"]
    assert state["parent_id"] == saved_link["parent_id"]
    assert state["child_id"] == saved_link["child_id"]
    assert not state["broken"]

    return {
        "name": "restore_saved_tack",
        "document_path": doc.Path,
        "link_id": saved_link["link_id"],
        "link_version": saved_link["version"],
        "parent_id": saved_link["parent_id"],
        "child_id": saved_link["child_id"],
        "runtime_count": len(states),
        "settings": {
            "advanced_reconciliation": utils.get_setting(
                "advanced_reconciliation", doc
            ),
            "debug": utils.get_setting("debug", doc),
            "allow_child_movement": utils.get_setting(
                "allow_child_movement", doc
            ),
        },
        "display_enabled": document_runtime.try_get_value(
            doc,
            utils.DISPLAY_ENABLED_KEY,
        ),
        "document_strings_unchanged": (
            settings_after == settings_before
            and display_after == display_before
        ),
    }


run_step("restore_saved_tack", restore_saved_tack, send_done=True)
