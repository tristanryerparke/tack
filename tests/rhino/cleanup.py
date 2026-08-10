import sys

sys.modules.pop("common", None)

from common import STATE_KEY
from common import TEST_OBJECT_KEY
from common import pause
from common import rs
from common import run_step
from common import sc
from common import tack_modules


def _is_test_object(obj):
    try:
        return bool(obj.Attributes.UserDictionary[TEST_OBJECT_KEY])
    except Exception:
        return False


def cleanup():
    handlers, metadata, runtime, utils = tack_modules()
    doc = sc.doc
    handlers.unsubscribe()
    runtime.stop_runtime(doc)

    state = sc.sticky.pop(STATE_KEY, {})
    utils.set_setting(
        "allow_child_movement",
        state.get("original_allow_child_movement", False),
    )
    object_ids = []

    def add(object_id):
        if object_id is not None and object_id not in object_ids:
            object_ids.append(object_id)

    for key in (
        "parent_id",
        "child_id",
        "second_parent_id",
        "second_child_id",
    ):
        add(state.get(key))
    for obj in doc.Objects:
        if obj is not None and _is_test_object(obj):
            add(obj.Id)

    for object_id in object_ids:
        if doc.Objects.Find(object_id) is not None:
            rs.UnlockObject(object_id)
            assert rs.DeleteObject(object_id), "Could not delete test object {}".format(
                object_id
            )
    remaining = [
        obj.Id
        for obj in doc.Objects
        if obj is not None and _is_test_object(obj)
    ]
    assert not remaining, "Tagged test objects remain: {}".format(remaining)

    restored = 0
    for saved_link in metadata.all_links(doc):
        if runtime.start_runtime(
            doc,
            saved_link["parent_id"],
            saved_link["child_id"],
            saved_link["link_id"],
        ):
            restored += 1
    handlers.subscribe()

    doc.Views.Redraw()
    print(
        "Removed {} test object(s); restored {} existing Tack relationship(s).".format(
            len(object_ids),
            restored,
        )
    )
    pause("fixture removed")


run_step("cleanup_anchor_pair", cleanup)
