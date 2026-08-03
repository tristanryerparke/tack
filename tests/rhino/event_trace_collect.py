import sys

sys.modules.pop("common", None)

from common import run_step
from event_command_traces import collect_deferred_scenario


def run():
    collect_deferred_scenario()


run_step("event_trace_collect_deferred_scenario", run)
