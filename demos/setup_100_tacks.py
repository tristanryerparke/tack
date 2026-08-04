import os
import traceback


RELATIONSHIP_COUNT = 100
COLUMNS = 10
PARENT_RADIUS = 2
CHILD_OFFSET = 8
COLUMN_SPACING = 30
ROW_SPACING = 20
GROUP_NAME = "Tack Playground 100"


def _debug_enabled():
    return any(
        os.getenv(name, "").strip().lower() in ("1", "true", "yes", "on")
        for name in ("debug", "TACK_DEBUG")
    )


try:
    import importlib
    import sys

    sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

    import Rhino
    import System
    import rhinoscriptsyntax as rs
    from Rhino.Commands import Result

    import tack

    importlib.reload(tack).reload()

    import tack.analysis.bbox as bbox_analysis
    from tack import handlers
    from tack import metadata
    from tack import runtime
    from tack import utils


    def _anchor(obj):
        return (
            bbox_analysis.ANCHOR_TYPE,
            bbox_analysis.CENTER_INDEX,
            dict(bbox_analysis.anchors(obj))[bbox_analysis.CENTER_INDEX],
        )


    def _name(object_id, value):
        obj = Rhino.RhinoDoc.ActiveDoc.Objects.Find(object_id)
        assert obj is not None
        attributes = obj.Attributes.Duplicate()
        attributes.Name = value
        assert Rhino.RhinoDoc.ActiveDoc.Objects.ModifyAttributes(
            obj.Id,
            attributes,
            True,
        )


    def RunCommand(is_interactive):
        doc = Rhino.RhinoDoc.ActiveDoc
        if doc is None:
            return Result.Cancel

        # Existing Tack relationships stay in runtime state; callbacks are
        # paused only while this fixture's objects and metadata are created.
        handlers.unsubscribe()
        object_ids = []
        link_ids = []
        try:
            for index in range(RELATIONSHIP_COUNT):
                column = index % COLUMNS
                row = index // COLUMNS
                x = column * COLUMN_SPACING
                y = row * ROW_SPACING
                parent_id = rs.AddCircle((x, y, 0), PARENT_RADIUS)
                child_id = rs.AddCircle(
                    (x + CHILD_OFFSET, y, 0),
                    PARENT_RADIUS,
                )
                assert parent_id is not None and child_id is not None

                _name(parent_id, "Tack Playground parent {:03d}".format(index + 1))
                _name(child_id, "Tack Playground child {:03d}".format(index + 1))
                rs.ObjectColor(parent_id, System.Drawing.Color.IndianRed)
                rs.ObjectColor(child_id, System.Drawing.Color.SteelBlue)
                object_ids.extend((parent_id, child_id))

                parent = doc.Objects.Find(parent_id)
                child = doc.Objects.Find(child_id)
                link_id = metadata.write_link(
                    doc,
                    parent_id,
                    child_id,
                    _anchor(parent),
                    _anchor(child),
                )
                assert link_id is not None
                assert runtime.start_runtime(
                    doc,
                    parent_id,
                    child_id,
                    link_id,
                    redraw=False,
                )
                link_ids.append(link_id)

            if not rs.IsGroup(GROUP_NAME):
                rs.AddGroup(GROUP_NAME)
            assert rs.AddObjectsToGroup(object_ids, GROUP_NAME)
            handlers.subscribe()
            doc.Views.Redraw()
            utils.debug(
                "[Tack playground] created {} relationships / {} objects; "
                "group={!r}".format(
                    len(link_ids),
                    len(object_ids),
                    GROUP_NAME,
                )
            )
            return Result.Success
        except Exception:
            handlers.subscribe()
            raise


    if __name__ == "__main__":
        from rhino_watcher import try_send_end_sync
        from rhino_watcher import try_send_quit_sync
        from rhino_watcher import websocket_output_if_available_sync

        with websocket_output_if_available_sync():
            result = RunCommand(True)
        if result == Result.Success:
            try_send_end_sync()
        else:
            try_send_quit_sync()
except Exception:
    from rhino_watcher import try_send_quit_sync
    from rhino_watcher import websocket_output_if_available_sync

    if _debug_enabled():
        with websocket_output_if_available_sync():
            traceback.print_exc()
    try_send_quit_sync()
