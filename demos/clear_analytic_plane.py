"""Run TackClear from source for interactive development.

    uv run rhino-watch demos/clear_analytic_plane.py --debug
"""

import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from run_in_rhino.rhino_env.client import SocketConnection
from run_in_rhino.rhino_env.env import install_os_environment
from run_in_rhino.rhino_env.parasite import OutputParasite

from tack import actions


if __name__ == "__main__":
    connection = SocketConnection()
    install_os_environment(connection)
    with OutputParasite(connection, done_msg=True):
        result = actions.run("clear")
        print("TackClear result: {}".format(result))
