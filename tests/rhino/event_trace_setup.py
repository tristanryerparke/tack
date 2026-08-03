import sys

sys.modules.pop("common", None)
sys.modules.pop("event_command_traces", None)

from common import run_step
from event_command_traces import setup_trace


run_step("event_trace_setup", setup_trace)
