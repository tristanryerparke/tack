import Rhino
import scriptcontext as sc


def get_current_command_name(event):
    """Return the active command name while handling a display event."""
    command_ids = Rhino.Commands.Command.GetCommandStack() or ()
    if not command_ids:
        return None
    return Rhino.Commands.Command.LookupCommandName(command_ids[-1], True)


def has_selected_subobjects(doc):
    """Returns true only if whole objects (not sub-objects) are selected
    In tack, we don't want to dynamically draw moving children or add any overhead
    when sub-objects are moved."""
    for obj in doc.Objects.GetSelectedObjects(False, False):
        if obj.GetSelectedSubObjects() is not None:
            return True
    return False
