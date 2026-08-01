import importlib
import sys


_MODULES = (
    "utils",
    "metadata",
    "analysis",
    "link",
    "conduit",
    "runtime",
    "handlers",
    "prompting.command_menu",
    "prompting.picking",
)


def reload():
    """Reload Tack's loaded modules in dependency order."""
    for name in _MODULES:
        module = sys.modules.get(__name__ + "." + name)
        if module is not None:
            importlib.reload(module)
