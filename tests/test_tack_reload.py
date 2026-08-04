import sys
import types

import tack


def test_reload_reimports_a_module_without_a_discoverable_spec(monkeypatch):
    module_name = "tack.utils"
    stale_module = types.ModuleType(module_name)
    fresh_module = types.ModuleType(module_name)
    reloads = []
    imports = []

    def reload_stale(module):
        reloads.append(module)
        raise ModuleNotFoundError(
            "spec not found for the module {!r}".format(module.__name__),
            name=module.__name__,
        )

    def import_fresh(name):
        imports.append(name)
        sys.modules[name] = fresh_module
        return fresh_module

    monkeypatch.setitem(sys.modules, module_name, stale_module)
    monkeypatch.setattr(tack, "_MODULES", ("utils",))
    monkeypatch.setattr(tack.importlib, "reload", reload_stale)
    monkeypatch.setattr(tack.importlib, "import_module", import_fresh)

    tack.reload()

    assert reloads == [stale_module]
    assert imports == [module_name]
    assert sys.modules[module_name] is fresh_module
