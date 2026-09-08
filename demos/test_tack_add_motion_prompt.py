"""Preview TackAdd's proposed degrees-of-freedom command-line prompt.

    uv run rhino-watch demos/test_tack_add_motion_prompt.py --debug
"""

import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import Rhino
from run_in_rhino.rhino_env.client import SocketConnection
from run_in_rhino.rhino_env.env import install_os_environment
from run_in_rhino.rhino_env.parasite import OutputParasite


def choose_degrees_of_freedom():
    child_movement = Rhino.Input.Custom.OptionToggle(True, "Off", "On")
    translation = Rhino.Input.Custom.OptionToggle(True, "Off", "On")
    rotation = Rhino.Input.Custom.OptionToggle(True, "Off", "On")
    getter = Rhino.Input.Custom.GetOption()
    getter.SetCommandPrompt("Tack Degrees of Freedom")
    getter.AcceptNothing(True)
    getter.AddOptionToggle("Translation", translation)
    getter.AddOptionToggle("Rotation", rotation)
    getter.AddOptionToggle("ChildMovement", child_movement)

    while True:
        result = getter.Get()
        if result == Rhino.Input.GetResult.Nothing:
            enabled = []
            if child_movement.CurrentValue:
                enabled.append("Child Movement")
            if translation.CurrentValue:
                enabled.append("Translation")
            if rotation.CurrentValue:
                enabled.append("Rotation")
            return " + ".join(enabled) or "None"
        if result != Rhino.Input.GetResult.Option:
            return None


if __name__ == "__main__":
    connection = SocketConnection()
    install_os_environment(connection)
    with OutputParasite(connection, done_msg=True):
        choice = choose_degrees_of_freedom()
        print("TackAdd degrees of freedom: {}".format(choice or "cancelled"))
