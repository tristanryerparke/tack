import sys
import time
from contextlib import nullcontext
from contextlib import redirect_stderr
from contextlib import redirect_stdout
from io import StringIO

import Rhino

sys.modules.pop("common", None)

from common import assert_close
from common import point_data
from common import rs
from common import run_step
from common import sc
from common import tack_modules
from common import translated


RELATIONSHIP_COUNT = 100
OBJECT_COUNT = RELATIONSHIP_COUNT * 2
TEST_OBJECT_KEY = "Tack.StressTest.100Relationships"
MOVE = Rhino.Geometry.Vector3d(3, 5, 2)


def _anchor(bbox_analysis, obj):
    return (
        bbox_analysis.ANCHOR_TYPE,
        bbox_analysis.CENTER_INDEX,
        dict(bbox_analysis.anchors(obj))[bbox_analysis.CENTER_INDEX],
    )


def _mark_test_object(doc, object_id):
    obj = doc.Objects.Find(object_id)
    assert obj is not None, "Could not find stress-test object {}".format(object_id)
    attributes = obj.Attributes.Duplicate()
    attributes.UserDictionary.Set(TEST_OBJECT_KEY, True)
    assert doc.Objects.ModifyAttributes(obj.Id, attributes, True), (
        "Could not mark stress-test object {}".format(object_id)
    )


def _is_test_object(obj):
    try:
        return bool(obj.Attributes.UserDictionary[TEST_OBJECT_KEY])
    except Exception:
        return False


def _delete_test_objects(doc):
    object_ids = [
        obj.Id
        for obj in doc.Objects
        if obj is not None and _is_test_object(obj)
    ]
    for object_id in object_ids:
        if doc.Objects.Find(object_id) is not None:
            assert doc.Objects.Delete(object_id, True), (
                "Could not delete stress-test object {}".format(object_id)
            )
    remaining = [
        obj.Id
        for obj in doc.Objects
        if obj is not None and _is_test_object(obj)
    ]
    assert not remaining, "Stress-test objects remain: {}".format(remaining)
    return len(object_ids)


def _restore_existing_tacks(doc, metadata, runtime):
    restored = 0
    for saved_link in metadata.all_links(doc):
        if runtime.start_runtime(
            doc,
            saved_link["parent_id"],
            saved_link["child_id"],
            saved_link["link_id"],
        ):
            restored += 1
    return restored


def stress_100_relationships():
    handlers, metadata, runtime, utils = tack_modules(reload_modules=True)
    import tack.analysis.bbox as bbox_analysis
    from tack import link

    doc = sc.doc
    assert doc is not None, "Open a Rhino document before running this test"

    original_debug = utils.DEBUG
    original_websocket_output = handlers._websocket_output
    result = None
    restored = 0

    handlers.unsubscribe()
    runtime.stop_runtime(doc)
    _delete_test_objects(doc)
    utils.DEBUG = False
    # Exclude per-event watcher transport while retaining the Rhino command,
    # Tack callbacks, metadata writes, and redraws in the measured duration.
    handlers._websocket_output = nullcontext

    try:
        setup_started = time.perf_counter()
        parent_ids = []
        child_ids = []
        link_ids = []
        child_centers_before = []

        for index in range(RELATIONSHIP_COUNT):
            column = index % 10
            row = index // 10
            x = column * 30
            y = row * 20
            parent_id = rs.AddCircle((x, y, 0), 2)
            child_id = rs.AddCircle((x + 8, y, 0), 2)
            assert parent_id is not None and child_id is not None, (
                "Could not create relationship {} objects".format(index)
            )
            _mark_test_object(doc, parent_id)
            _mark_test_object(doc, child_id)

            parent = doc.Objects.Find(parent_id)
            child = doc.Objects.Find(child_id)
            link_id = metadata.write_link(
                doc,
                parent_id,
                child_id,
                _anchor(bbox_analysis, parent),
                _anchor(bbox_analysis, child),
            )
            assert link_id is not None, (
                "Could not create relationship {} metadata".format(index)
            )
            assert runtime.start_runtime(
                doc,
                parent_id,
                child_id,
                link_id,
                redraw=False,
            ), "Could not start relationship {}".format(index)

            parent_ids.append(parent_id)
            child_ids.append(child_id)
            link_ids.append(link_id)
            child_centers_before.append(
                dict(bbox_analysis.anchors(child))[bbox_analysis.CENTER_INDEX]
            )

        # Exercise the same cache lifecycle used by commands/tack_clear.py
        # and commands/tack_restore.py without clearing unrelated document metadata.
        runtime.stop_runtime(doc)
        assert not runtime.states(doc, create=False)
        assert utils.CONDUIT_KEY not in sc.sticky
        for parent_id, child_id, link_id in zip(
            parent_ids,
            child_ids,
            link_ids,
        ):
            assert runtime.start_runtime(
                doc,
                parent_id,
                child_id,
                link_id,
                redraw=False,
            )
        doc.Views.Redraw()

        handlers.subscribe()
        setup_seconds = time.perf_counter() - setup_started

        tagged_count = sum(
            1
            for obj in doc.Objects
            if obj is not None and _is_test_object(obj)
        )
        assert tagged_count == OBJECT_COUNT, (
            "Expected {} stress-test objects, found {}".format(
                OBJECT_COUNT,
                tagged_count,
            )
        )
        assert len(runtime.states(doc)) == RELATIONSHIP_COUNT, (
            "Expected {} active relationships, found {}".format(
                RELATIONSHIP_COUNT,
                len(runtime.states(doc)),
            )
        )
        assert all(
            not state["display"]["dirty"]
            for state in runtime.states(doc).values()
        ), "One or more display caches started dirty"

        rs.UnselectAllObjects()
        selected_count = rs.SelectObjects(parent_ids)
        assert selected_count == RELATIONSHIP_COUNT, (
            "Expected to select {} parents, selected {}".format(
                RELATIONSHIP_COUNT,
                selected_count,
            )
        )

        captured_output = StringIO()
        with redirect_stdout(captured_output), redirect_stderr(captured_output):
            update_started = time.perf_counter()
            moved = rs.Command("_Move 0,0,0 3,5,2", echo=False)
            # Deferred solving (tack.scheduler) drains on RhinoApp.Idle, which
            # does not fire while this script holds the UI thread.
            from tack import scheduler

            scheduler.solve_now(sc.doc)
            update_seconds = time.perf_counter() - update_started
        assert moved, "Rhino Move command failed: {}".format(
            captured_output.getvalue()
        )

        tolerance = max(doc.ModelAbsoluteTolerance, 1e-7)
        updated_child_count = 0
        saved_ids = {
            saved_link["link_id"]
            for saved_link in metadata.all_links(doc)
        }
        assert set(link_ids) <= saved_ids, (
            "One or more stress-test relationships disappeared from metadata"
        )

        for index, (link_id, child_before) in enumerate(
            zip(link_ids, child_centers_before)
        ):
            state = runtime.states(doc).get(link_id)
            assert state is not None, (
                "Relationship {} disappeared from runtime".format(index)
            )
            parent = utils.find_object(doc, state["parent_id"])
            child = utils.find_object(doc, state["child_id"])
            assert parent is not None, "Relationship {} lost its parent".format(index)
            assert child is not None, "Relationship {} lost its child".format(index)

            child_after = dict(bbox_analysis.anchors(child))[
                bbox_analysis.CENTER_INDEX
            ]
            assert_close(
                child_after,
                translated(child_before, MOVE),
                tolerance,
                "relationship {} child center".format(index),
            )
            updated_child_count += 1
            assert metadata.read_link(child, link_id) is not None, (
                "Relationship {} lost child metadata".format(index)
            )
            assert metadata.read_parent_links(parent).get(link_id) == str(child.Id), (
                "Relationship {} lost parent metadata".format(index)
            )
            display = state.get("display")
            assert display is not None and not display["dirty"], (
                "Relationship {} display cache stayed dirty".format(index)
            )
            inspection = link.inspect_link(doc, state)
            assert inspection is not None
            assert_close(
                display["parent_anchor"],
                inspection["parent_anchor"],
                tolerance,
                "relationship {} cached parent anchor".format(index),
            )
            assert_close(
                display["child_anchor"],
                inspection["child_anchor"],
                tolerance,
                "relationship {} cached child anchor".format(index),
            )

        redraw_started = time.perf_counter()
        for _ in range(10):
            doc.Views.Redraw()
        redraw_seconds = time.perf_counter() - redraw_started

        tagged_count_after = sum(
            1
            for obj in doc.Objects
            if obj is not None and _is_test_object(obj)
        )
        assert tagged_count_after == OBJECT_COUNT

        result = {
            "name": "stress_100_relationships_200_objects",
            "relationship_count": RELATIONSHIP_COUNT,
            "object_count": tagged_count_after,
            "updated_child_count": updated_child_count,
            "setup_seconds": setup_seconds,
            "update_seconds": update_seconds,
            "milliseconds_per_relationship": (
                update_seconds * 1000 / RELATIONSHIP_COUNT
            ),
            "ten_redraw_seconds": redraw_seconds,
            "milliseconds_per_redraw": redraw_seconds * 1000 / 10,
            "move": point_data(MOVE),
        }
    finally:
        handlers.unsubscribe()
        runtime.stop_runtime(doc)
        deleted = _delete_test_objects(doc)
        restored = _restore_existing_tacks(doc, metadata, runtime)
        handlers.subscribe()
        handlers._websocket_output = original_websocket_output
        utils.DEBUG = original_debug
        doc.Views.Redraw()
        print(
            "Stress cleanup removed {} object(s); restored {} existing Tack relationship(s).".format(
                deleted,
                restored,
            )
        )

    return result


run_step(
    "stress_100_relationships_200_objects",
    stress_100_relationships,
    send_done=True,
)
