"""Sequence Python inspection scripts and completed native Rhino commands."""

import json

from run_in_rhino.pipe import run_script
from run_in_rhino.server import RunContext, server
from run_in_rhino.utils import command_script


def run_flow(actions, rhino_instance):
    """Run a native-command flow in one disposable Rhino document."""
    events = server(context=RunContext(stop=False))
    results = []
    position = 0
    last_data = {}
    command_callback = None

    def advance():
        nonlocal command_callback, position
        if position >= len(actions):
            return True
        kind, value = actions[position]
        position += 1
        if kind == "command":
            command = value.format(**last_data)
            command_callback = "tack_rhino_flow_{}".format(position)
            run_script(
                script=command_script(command, callback=command_callback),
                pipe_path=rhino_instance.pipe_path,
            )
            return False
        if kind != "script":
            raise ValueError("Unknown Rhino flow action: {}".format(kind))
        run_script(script_path=value, pipe_path=rhino_instance.pipe_path)
        return False

    try:
        for status, data in events:
            if status == "ready":
                if advance():
                    return results
            elif status == "data":
                payload = json.loads(data)
                if command_callback is not None:
                    if payload.get("callback") != command_callback:
                        continue
                    assert payload["succeeded"], (
                        "Rhino command failed: {}".format(payload["command"])
                    )
                    command_callback = None
                    if advance():
                        return results
                    continue
                last_data.clear()
                last_data.update(payload)
                results.append(payload)
                if advance():
                    return results
            elif status == "terminal":
                continue
    finally:
        events.close()
    return results
