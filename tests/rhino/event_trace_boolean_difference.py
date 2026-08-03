import sys

sys.modules.pop("common", None)

from common import run_step
from event_command_traces import arm_boolean_difference_parent


def run():
    arm_boolean_difference_parent()


run_step(
    "event_trace_arm_boolean_difference_parent",
    run,
)
