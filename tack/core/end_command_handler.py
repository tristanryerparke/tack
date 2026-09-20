"""Print the data supplied by Rhino's ``Command.EndCommand`` event."""

import Rhino
import scriptcontext as sc
from run_in_rhino.rhino_env.client import SocketConnection
from run_in_rhino.rhino_env.parasite import OutputParasite


HANDLER_KEY = "tack.end_command_handler"


def on_end_command(sender, event):
    # The setup connection has sent its ``done`` message. Open a new connection
    # so output from commands run later reaches a ``rhino-watch --nostop`` session.
    connection = SocketConnection()
    with OutputParasite(connection):
        print("EndCommand")
        print("  sender: {}".format(sender))
        for label, attribute in (
            ("command English name", "CommandEnglishName"),
            ("command local name", "CommandLocalName"),
            ("command ID", "CommandId"),
            ("command help URL", "CommandHelpURL"),
            ("command plug-in name", "CommandPluginName"),
            ("command hidden from user", "CommandIsHiddenFromUser"),
            ("command result", "CommandResult"),
            ("document", "Document"),
            ("document runtime serial number", "DocumentRuntimeSerialNumber"),
        ):
            if hasattr(event, attribute):
                print("  {}: {}".format(label, getattr(event, attribute)))


connection = SocketConnection()
with OutputParasite(connection, done_msg=True):
    previous_handler = sc.sticky.get(HANDLER_KEY)
    if previous_handler is not None:
        Rhino.Commands.Command.EndCommand -= previous_handler
    Rhino.Commands.Command.EndCommand += on_end_command
    sc.sticky[HANDLER_KEY] = on_end_command
    print("Subscribed to Rhino.Commands.Command.EndCommand")
