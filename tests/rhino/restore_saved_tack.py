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

    doc = sc.doc
    assert doc is not None
    runtime.stop_runtime(doc)
    assert not runtime.states(doc, create=False)

    command = runpy.run_path(COMMAND_PATH, run_name="tack_restore_test_command")
    result = command["RunCommand"](False)
    assert result == Rhino.Commands.Result.Success

    from tack import metadata
    from tack import runtime

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
        "parent_id": saved_link["parent_id"],
        "child_id": saved_link["child_id"],
        "runtime_count": len(states),
    }


run_step("restore_saved_tack", restore_saved_tack, send_done=True)
