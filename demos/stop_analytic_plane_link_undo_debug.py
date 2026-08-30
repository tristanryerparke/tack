"""Stop the persistent analytic-plane-link undo diagnostic watcher.

Run this from Rhino with ``RunPythonScript`` after reaching the undo state that
should be inspected.
"""

import scriptcontext as sc


STOP_CALLBACK_KEY = "Tack.AnalyticPlaneLink.UndoDiagnosticStopCallback"


stop = sc.sticky.get(STOP_CALLBACK_KEY)
if stop is not None:
    stop()
else:
    from run_in_rhino.rhino_env.client import SocketConnection

    SocketConnection().send_quit()
