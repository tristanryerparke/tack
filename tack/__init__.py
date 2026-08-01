import importlib
import sys


_MODULES = (
    "utils",
    "metadata",
    "analysis.bbox",
    "analysis.vertex",
    "link",
    "conduit",
    "runtime",
    "handlers",
    "prompting.anchor_pick_conduit",
    "prompting.picking",
    "prompting.command_menu",
)


def reload():
    """Reload Tack's loaded modules in dependency order."""
    analysis_name = __name__ + ".analysis"
    loaded_analysis = sys.modules.get(analysis_name)
    if loaded_analysis is not None and not hasattr(loaded_analysis, "__path__"):
        del sys.modules[analysis_name]
    importlib.invalidate_caches()

    for name in _MODULES:
        module = sys.modules.get(__name__ + "." + name)
        if module is not None:
            importlib.reload(module)
