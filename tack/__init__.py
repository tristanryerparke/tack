import importlib
import sys


_MODULES = (
    "utils",
    "document_runtime",
    "metadata",
    "anchor_definitions",
    "analysis.bbox",
    "analysis.polyline_vertex",
    "analysis.vertex",
    "link",
    "conduit",
    "runtime",
    "scheduler",
    "handlers",
    "prompting.anchor_pick_conduit",
    "prompting.osnap_anchor_picker",
    "prompting.picking",
    "prompting.command_menu",
)


def _reload_module(name):
    module = sys.modules.get(name)
    if module is None:
        return
    try:
        importlib.reload(module)
    except ModuleNotFoundError as error:
        if error.name != name:
            raise
        del sys.modules[name]
        importlib.import_module(name)


def reload():
    """Reload Tack's loaded modules in dependency order."""
    analysis_name = __name__ + ".analysis"
    loaded_analysis = sys.modules.get(analysis_name)
    if loaded_analysis is not None and not hasattr(loaded_analysis, "__path__"):
        del sys.modules[analysis_name]
    importlib.invalidate_caches()

    for name in _MODULES:
        _reload_module(__name__ + "." + name)
