import os
import sys
import time
import traceback

import Rhino
import rhinoscriptsyntax as rs
import scriptcontext as sc
from rhino_watcher import send_data_sync
from rhino_watcher import websocket_output_sync


# Set to 0 for fast runs; leave positive to watch each step in Rhino.
SLOW_SECONDS = 1.0
STATE_KEY = "Tack.IntegrationTest.ParentMove"
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
TACK_DIR = os.path.join(PROJECT_ROOT, "tack")
if TACK_DIR not in sys.path:
    sys.path.insert(0, TACK_DIR)


def tack_modules():
    import handlers
    import metadata
    import runtime
    import tack_frame_picker
    import utils

    return handlers, metadata, runtime, tack_frame_picker, utils


def pause(label):
    if SLOW_SECONDS:
        print("waiting {} seconds: {}".format(SLOW_SECONDS, label))
        time.sleep(SLOW_SECONDS)


def run_step(name, action):
    try:
        with websocket_output_sync():
            print("START {}".format(name))
            data = action()
            if data is not None:
                send_data_sync(data)
            print("PASS {}".format(name))
    except Exception:
        with websocket_output_sync():
            print("FAIL {}".format(name))
            traceback.print_exc()
        raise


def box(minimum, maximum):
    x0, y0, z0 = minimum
    x1, y1, z1 = maximum
    return rs.AddBox(
        [
            (x0, y0, z0),
            (x1, y0, z0),
            (x1, y1, z0),
            (x0, y1, z0),
            (x0, y0, z1),
            (x1, y0, z1),
            (x1, y1, z1),
            (x0, y1, z1),
        ]
    )


def point_data(point):
    return (point.X, point.Y, point.Z)


def point_from_data(data):
    return Rhino.Geometry.Point3d(*data)


def translated(point, vector):
    return Rhino.Geometry.Point3d(
        point.X + vector.X, point.Y + vector.Y, point.Z + vector.Z
    )


def assert_close(actual, expected, tolerance, label):
    distance = actual.DistanceTo(expected)
    assert distance <= tolerance, "{}: expected {}, got {}, distance {}".format(
        label, expected, actual, distance
    )
