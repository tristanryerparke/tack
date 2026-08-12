import time

from run_in_rhino.pipe import run_command, run_script
from run_in_rhino.server import RunContext, server


def run_flow(actions, *, environment=None):
    """Run filename-based Rhino scripts and commands through one server."""
    events = server(context=RunContext(env=environment or {}))
    results = []
    position = 0
    last_data = {}
    current_kind = None

    def advance():
        nonlocal last_data, current_kind
        nonlocal position
        while position < len(actions):
            kind, value = actions[position]
            position += 1
            current_kind = kind
            if kind in ("command", "command_async"):
                command = value.format(**last_data)
                print("DEBUG parent sending command: {}".format(command), flush=True)
                run_command(command, block=kind != "command_async")
                print("DEBUG parent waiting 1s for Rhino command", flush=True)
                time.sleep(1.0)
                continue
            print("DEBUG parent sending script: {}".format(value), flush=True)
            run_script(script_path=value)
            return

    try:
        for status, data in events:
            if status == "ready":
                print("DEBUG parent saw ready", flush=True)
                advance()
            elif status == "terminal":
                print("DEBUG Rhino terminal: {}".format(data), flush=True)
            elif status == "data":
                print("DEBUG parent received data: {}".format(data), flush=True)
                is_step_marker = isinstance(data, dict) and (
                    "__run_step__" in data or "__command_done__" in data
                )
                if isinstance(data, dict) and not is_step_marker:
                    last_data.clear()
                    last_data.update(data)
                if not is_step_marker:
                    results.append(data)
                if position < len(actions):
                    advance()
            elif status == "done":
                print("DEBUG parent saw done", flush=True)
    finally:
        events.close()
    return results
