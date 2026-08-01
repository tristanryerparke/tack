import traceback


try:
    import importlib
    import os
    import sys

    sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

    import Rhino
    from Rhino.Commands import Result

    import tack

    importlib.reload(tack).reload()

    from tack import handlers
    from tack import metadata
    from tack import runtime
    from tack.prompting import picking


    def RunCommand(is_interactive):
        doc = Rhino.RhinoDoc.ActiveDoc
        if doc is None:
            return Result.Cancel

        handlers.unsubscribe()
        runtime.stop_runtime()

        picked = picking.pick_link(doc)
        if picked is None:
            return Result.Cancel

        (
            parent_id,
            child_id,
            parent_vertex_type,
            parent_vertex_index,
            child_vertex_type,
            child_vertex_index,
            parent_point,
            child_point,
        ) = picked
        if not metadata.write_link(
            doc,
            parent_id,
            child_id,
            (parent_vertex_type, parent_vertex_index),
            (child_vertex_type, child_vertex_index),
            parent_point,
            child_point,
        ):
            print("Could not write coincident vertex relationship metadata.")
            return Result.Failure

        if not runtime.start_runtime(parent_id, child_id):
            print("Could not start coincident vertex relationship.")
            return Result.Failure
        handlers.subscribe()
        print("Coincident vertex relationship active.")
        print("Parent GUID: {}".format(parent_id))
        print("Child GUID: {}".format(child_id))
        return Result.Success


    if __name__ == "__main__":
        from rhino_watcher import send_end_sync
        from rhino_watcher import send_quit_sync
        from rhino_watcher import websocket_output_sync

        with websocket_output_sync():
            result = RunCommand(True)
        if result == Result.Success:
            send_end_sync()
        else:
            send_quit_sync()
except Exception:
    from rhino_watcher import send_quit_sync
    from rhino_watcher import websocket_output_sync

    with websocket_output_sync():
        traceback.print_exc()
    send_quit_sync()
