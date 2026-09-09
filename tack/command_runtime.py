"""Shared dispatcher used by Tack's generated commands and panel buttons."""

import importlib
import sys

from Rhino.Commands import Result

from TackRhinoPlugin import PluginBridge


_PACKAGE_NAME = "tack"
_PRESERVED_MODULES = {
    _PACKAGE_NAME + ".command_runtime",
    _PACKAGE_NAME + ".panel",
}


def _reload_action_modules():
    """Forget action-side modules so the next import reads current source."""
    module_names = sorted(
        (
            name
            for name in tuple(sys.modules)
            if name.startswith(_PACKAGE_NAME + ".")
            and not any(
                name == preserved or name.startswith(preserved + ".")
                for preserved in _PRESERVED_MODULES
            )
        ),
        key=lambda name: name.count("."),
        reverse=True,
    )
    for module_name in module_names:
        module = sys.modules.get(module_name)
        parent_name, _, child_name = module_name.rpartition(".")
        parent = sys.modules.get(parent_name)
        if parent is not None and getattr(parent, child_name, None) is module:
            delattr(parent, child_name)
        sys.modules.pop(module_name, None)
    importlib.invalidate_caches()


def run(action, doc, reload_modules=False):
    """Run one Tack action using the plug-in's persisted display preference."""
    if doc is None:
        return Result.Cancel
    if reload_modules:
        _reload_action_modules()

    if action == "settings":
        settings = importlib.import_module(_PACKAGE_NAME + ".settings")
        return settings.show(doc)

    actions = importlib.import_module(_PACKAGE_NAME + ".actions")
    result = actions.run(
        action,
        doc=doc,
        default_display_enabled=PluginBridge.DefaultDisplayEnabled,
    )
    if result == Result.Success and action in ("add", "clear"):
        PluginBridge.SaveDisplayPreference(action)
    return result
