import json

from run_in_rhino.pipe import run_script
from run_in_rhino.server import RunContext, server
from run_in_rhino.utils import command_script


def run_flow(actions, *, environment=None):
    """Run filename-based Rhino scripts and commands through one server."""
    events = server(context=RunContext(env=environment or {}))
    results = []
    position = 0
    last_data = {}
    command_callback = None

    def advance():
        nonlocal command_callback, position
        if position >= len(actions):
            return

        kind, value = actions[position]
        position += 1
        if kind == "command":
            command = value.format(**last_data)
            command_callback = "rhino_flow_command_{}".format(position)
            print(
                "DEBUG parent sending command {}: {}".format(
                    command_callback,
                    command,
                ),
                flush=True,
            )
            run_script(
                script=command_script(
                    command,
                    callback=command_callback,
                )
            )
            return

        print("DEBUG parent sending script: {}".format(value), flush=True)
        run_script(script_path=value)

    try:
        for status, data in events:
            if status == "ready":
                print("DEBUG parent saw ready", flush=True)
                advance()
            elif status == "terminal":
                # server() already prints forwarded Rhino terminal output.
                continue
            elif status == "data":
                payload = json.loads(data) if isinstance(data, str) else data
                callback = payload.get("callback") if isinstance(payload, dict) else None
                if isinstance(payload, dict):
                    summary = (
                        callback
                        or payload.get("__run_step__")
                        or payload.get("name")
                        or sorted(payload)
                    )
                else:
                    summary = payload
                print("DEBUG parent received data: {}".format(summary), flush=True)
                if command_callback is not None:
                    if callback != command_callback:
                        continue
                    assert payload["succeeded"], "Rhino command failed: {}".format(
                        payload["command"]
                    )
                    print(
                        "DEBUG parent received command callback: {}".format(callback),
                        flush=True,
                    )
                    command_callback = None
                    advance()
                    continue

                is_step_marker = isinstance(payload, dict) and "__run_step__" in payload
                if isinstance(payload, dict) and not is_step_marker:
                    last_data.clear()
                    last_data.update(payload)
                if not is_step_marker:
                    results.append(payload)
                advance()
            elif status == "done":
                print("DEBUG parent saw done", flush=True)
    finally:
        events.close()
    return results
