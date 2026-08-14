"""Benchmark moving non-Tack objects in a disposable Rhino document.

Run with: uv run demos/benchmark_non_tack_move.py
"""

import argparse
import json
import time
from pathlib import Path

from run_in_rhino.app_control.instance import launch_rhino
from run_in_rhino.orchestration import run_rhino_command
from run_in_rhino.orchestration import run_rhino_python_til_done
from run_in_rhino.server import RunContext


PROJECT_ROOT = Path(__file__).parents[1]
BLANK_FILE = PROJECT_ROOT / "tests" / "blank_file.3dm"
SETUP_SCRIPT = (
    Path(__file__).with_name("rhino") / "setup_non_tack_move_benchmark.py"
)


def _command_seconds(instance, command):
    started = time.perf_counter()
    result = run_rhino_command(command, pipe_path=instance.pipe_path)
    elapsed = time.perf_counter() - started
    if not result["succeeded"]:
        raise RuntimeError("Rhino command failed: {}".format(result))
    return elapsed


def _set_handlers(instance, subscribed):
    action = "subscribe" if subscribed else "unsubscribe"
    script = """from run_in_rhino.rhino_env.client import SocketConnection
from tack import handlers
connection = SocketConnection()
handlers.{action}()
connection.send_data({{"handlers": {subscribed!r}}})
connection.send_done()
""".format(action=action, subscribed=subscribed)
    reason, _ = run_rhino_python_til_done(
        script=script,
        pipe_path=instance.pipe_path,
    )
    if reason != "done":
        raise RuntimeError("Handler setup ended with {!r}".format(reason))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--count", type=int, default=1000)
    args = parser.parse_args()

    with launch_rhino(BLANK_FILE, disposable=True) as instance:
        reason, payloads = run_rhino_python_til_done(
            script_path=SETUP_SCRIPT,
            context=RunContext(
                env={"TACK_BENCHMARK_COUNT": str(args.count)}
            ),
            pipe_path=instance.pipe_path,
        )
        if reason != "done":
            raise RuntimeError("Benchmark setup ended with {!r}".format(reason))
        setup = payloads[-1]

        _command_seconds(instance, "_Move 0,0,0 1,0,0")
        without_handlers = _command_seconds(instance, "_Move 0,0,0 2,0,0")
        _set_handlers(instance, True)
        with_handlers = _command_seconds(instance, "_Move 0,0,0 3,0,0")
        _set_handlers(instance, False)
        without_handlers_again = _command_seconds(
            instance,
            "_Move 0,0,0 4,0,0",
        )

        mean_without = (without_handlers + without_handlers_again) / 2
        print(
            json.dumps(
                {
                    "setup": setup,
                    "without_handlers_seconds": without_handlers,
                    "with_handlers_seconds": with_handlers,
                    "without_handlers_again_seconds": without_handlers_again,
                    "slowdown_vs_mean_without": with_handlers / mean_without,
                },
                indent=2,
            )
        )


if __name__ == "__main__":
    main()
