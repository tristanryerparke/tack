"""Optional output forwarding for scripts run by the Rhino watcher.

All imports of ``run_in_rhino`` stay inside these functions so Tack remains
usable in an ordinary Rhino session where that package is not installed.
"""

from contextlib import contextmanager


@contextmanager
def output(enabled):
    if not enabled:
        yield
        return

    from run_in_rhino.rhino_env.client import SocketConnection
    from run_in_rhino.rhino_env.env import install_os_environment
    from run_in_rhino.rhino_env.parasite import OutputParasite

    connection = SocketConnection()
    install_os_environment(connection)
    with OutputParasite(connection):
        yield


def send_quit(enabled):
    if not enabled:
        return
    from run_in_rhino.rhino_env.client import SocketConnection

    SocketConnection().send_quit()


def run_entrypoint(function, enabled):
    """Run a Rhino command and finish its watcher connection when debugging."""
    if not enabled:
        return function()

    try:
        from run_in_rhino.rhino_env.client import SocketConnection
        from run_in_rhino.rhino_env.env import install_os_environment
        from run_in_rhino.rhino_env.parasite import OutputParasite

        connection = SocketConnection()
        install_os_environment(connection)
    except Exception as error:
        print(
            "Tack watcher connection could not be established; continuing normally: {}".format(
                error
            )
        )
        return function()

    result = None
    with OutputParasite(connection):
        result = function()
    if result is not None:
        if str(result) == "Success":
            connection.send_done()
        else:
            connection.send_quit()
    return result
