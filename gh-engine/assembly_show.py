"""Print the active AssemblyGH session summary."""

import os
import sys
import traceback

PROJECT_ROOT = os.path.dirname(os.path.dirname(__file__))
GH_ENGINE_DIR = os.path.dirname(__file__)
for path in (PROJECT_ROOT, GH_ENGINE_DIR):
    if path not in sys.path:
        sys.path.insert(0, path)

from Rhino.Commands import Result

from assembly.session import get_active_session, session_summary


def RunCommand(is_interactive):
    try:
        session = get_active_session(False)
        print(session_summary(session))
        if session is not None:
            debug = session.get("debug", {})
            print(
                "  debug end_commands={} scheduled={} idle={} solves={} skips={} last_command={} last_changed_triggers={}".format(
                    debug.get("end_command_count", 0),
                    debug.get("scheduled_count", 0),
                    debug.get("idle_count", 0),
                    debug.get("solve_count", 0),
                    debug.get("skip_count", 0),
                    debug.get("last_command"),
                    [str(value)[:8] for value in debug.get("last_changed_triggers", [])],
                )
            )
            for object_id, body in sorted(session.get("bodies", {}).items()):
                print(
                    "  body {} role={} features={} controls={}".format(
                        object_id[:8],
                        body.get("role"),
                        len(body.get("features", {})),
                        len(body.get("controls", {})),
                    )
                )
            for index, joint in enumerate(session.get("joints", []), 1):
                print("  joint {}. {} [{}] {}".format(index, joint.get("name"), joint.get("type"), joint.get("id", "")[:8]))
            for index, mate in enumerate(session.get("mates", []), 1):
                print("  mate {}. {} [{}] {}".format(index, mate.get("name"), mate.get("type"), mate.get("id", "")[:8]))
        return Result.Success
    except Exception:
        traceback.print_exc()
        return Result.Failure


if __name__ == "__main__":
    from tack.watcher import run_entrypoint

    run_entrypoint(lambda: RunCommand(True), True)
