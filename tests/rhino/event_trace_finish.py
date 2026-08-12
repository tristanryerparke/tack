import sys

sys.modules.pop("common", None)

from common import run_step
from event_command_traces import finish_trace


run_step("event_trace_finish", finish_trace, send_done=True)
