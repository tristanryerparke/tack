from contextlib import contextmanager
import importlib
import os
import sys
import traceback

from run_in_rhino.rhino_env.client import SocketConnection
from run_in_rhino.rhino_env.env import install_os_environment
from run_in_rhino.rhino_env.parasite import OutputParasite

import Rhino
import rhinoscriptsyntax as rs
import scriptcontext as sc


STATE_KEY = "Tack.IntegrationTest.ParentMove"
TEST_OBJECT_KEY = "Tack.IntegrationTest.Object"
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


def tack_modules(reload_modules=False):
    import tack

    if reload_modules:
        importlib.reload(tack).reload()

    from tack import handlers
    from tack import metadata
    from tack import runtime
    from tack import utils

    return handlers, metadata, runtime, utils


def pause(label):
    # Deferred solving (tack.scheduler) only drains on RhinoApp.Idle, which
    # never fires while a test script holds the UI thread. Pump it here so
    # assertions made after a pause see the solved state.
    try:
        from tack import scheduler

        scheduler.solve_now(sc.doc)
    except Exception:
        pass


connection = SocketConnection()
install_os_environment(connection)


def run_step(name, action, *, send_done=False):
    with OutputParasite(connection):
        print("START {}".format(name))
        data = action()
        print("PASS {}".format(name))

    # Send completion only after OutputParasite has flushed. The parent can
    # safely launch the next Rhino script once this message is acknowledged.
    connection.send_data(
        {"__run_step__": name} if data is None else data
    )
    if send_done:
        connection.send_done()


@contextmanager
def suppress_break_alerts():
    from tack import link

    breaks = []
    original_break_link = link.break_link

    def record_break(state, reason):
        state["broken"] = True
        breaks.append(reason)

    link.break_link = record_break
    try:
        yield breaks
    finally:
        link.break_link = original_break_link


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
