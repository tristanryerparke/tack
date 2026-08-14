import importlib
import os
import sys
import time

import Rhino
import System
import scriptcontext as sc

from run_in_rhino.rhino_env.client import SocketConnection
from run_in_rhino.rhino_env.parasite import OutputParasite


PROJECT_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

connection = SocketConnection()
with OutputParasite(connection):
    import tack

    importlib.reload(tack).reload()
    from tack import handlers
    from tack import metadata
    from tack import runtime

    doc = sc.doc
    handlers.unsubscribe()
    runtime.stop_runtime(doc)

    object_count = int(os.environ.get("TACK_BENCHMARK_COUNT", "1000"))
    object_ids = []
    started = time.perf_counter()
    for index in range(object_count):
        object_id = doc.Objects.AddPoint(
            Rhino.Geometry.Point3d(
                float(index % 50),
                float(index // 50),
                0.0,
            )
        )
        if object_id == System.Guid.Empty:
            raise RuntimeError("Failed to create point {}".format(index))
        object_ids.append(object_id)

    selected_count = doc.Objects.Select(object_ids)
    connection.send_data(
        {
            "object_count": object_count,
            "selected_count": selected_count,
            "setup_seconds": time.perf_counter() - started,
            "saved_link_count": len(metadata.all_links(doc)),
            "runtime_count": len(runtime.states(doc, create=False)),
        }
    )
connection.send_done()
