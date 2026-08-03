import sys

sys.modules.pop("common", None)

from common import run_step
from event_command_traces import arm_move_parent


def run():
    arm_move_parent()


run_step("event_trace_arm_move_parent", run)
