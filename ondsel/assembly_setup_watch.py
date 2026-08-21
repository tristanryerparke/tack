"""Run an assembly setup script in Rhino and save its data records to JSON.

Like rhino-watch, but persists every "data" message sent by the Rhino script:

    uv run python ondsel/assembly_setup_watch.py ondsel/assembly/assembly_add_revolute.py
    uv run python ondsel/assembly_setup_watch.py --reset ondsel/assembly/assembly_anchor_world.py
"""

import argparse
import json
import os

from run_in_rhino.orchestration import run_rhino_python_til_done
from run_in_rhino.server import RunContext

SETUP_JSON_PATH = "/tmp/ondsel_assembly_setup.json"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("script", help="Rhino Python script path")
    parser.add_argument("--nostop", action="store_true", help="keep watching after done")
    parser.add_argument("--debug", action="store_true", help="enable debug env")
    parser.add_argument("--reset", action="store_true", help="clear saved records first")
    args = parser.parse_args()

    if args.reset or not os.path.exists(SETUP_JSON_PATH):
        with open(SETUP_JSON_PATH, "w") as handle:
            json.dump({"records": []}, handle, indent=2)

    context = RunContext(
        stop=not args.nostop,
        quit=True,
        env={"debug": "true" if args.debug else "false"},
    )
    status, received = run_rhino_python_til_done(args.script, context=context)

    with open(SETUP_JSON_PATH) as handle:
        data = json.load(handle)
    for item in received:
        if isinstance(item, str):
            try:
                item = json.loads(item)
            except ValueError:
                pass
        data["records"].append(item)
    with open(SETUP_JSON_PATH, "w") as handle:
        json.dump(data, handle, indent=2)

    print(
        "[setup-watch] status={} received={} saved to {}".format(
            status, len(received), SETUP_JSON_PATH
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
