"""Print one DrawOverlay event-argument sample for each Rhino command.

uv run rhino-log tack/dynamic/handler.py --nostop
"""

import Rhino
import scriptcontext as sc

from run_in_rhino.rhino_env.jsonl_logger import JsonlLogger
from tack.dynamic.command_state import (
    get_current_command_name,
    has_selected_subobjects,
)

logger = JsonlLogger(globals().get("RUN_IN_RHINO_LOG"))


HANDLERS_KEY = "tack.dynamic_draw_handler"
_printed_for_command = False


ALLOWED_COMMANDS = ["Drag", "Move", "Rotate", "Rotate3D"]


def on_draw_overlay(sender, event):

    # Determine if we should be dynamically drawing tack children during this command
    # If not, return early to prevent lag
    if (
        get_current_command_name(event) not in ALLOWED_COMMANDS
        or has_selected_subobjects(event.RhinoDoc)
        or event.RhinoDoc.Objects.GetSelectedObjectCount(False) == 0
    ):
        return
    logger.log("Allowed")


with logger:
    previous_handler = sc.sticky.get(HANDLERS_KEY)
    if previous_handler is not None:
        Rhino.Display.DisplayPipeline.DrawOverlay -= previous_handler
    Rhino.Display.DisplayPipeline.DrawOverlay += on_draw_overlay
    sc.sticky[HANDLERS_KEY] = on_draw_overlay
    logger.log("Subscribed to Rhino.Display.DisplayPipeline.DrawOverlay")
