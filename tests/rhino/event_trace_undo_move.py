import sys

sys.modules.pop("common", None)

from common import run_step
from event_command_traces import arm_undo_move


def run():
    arm_undo_move()


run_step("event_trace_arm_undo_move", run)
