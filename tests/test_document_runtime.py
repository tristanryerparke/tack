import importlib.util
from pathlib import Path
import sys
import types


MODULE_PATH = Path(__file__).parents[1] / "tack" / "document_runtime.py"


class FakeDocument:
    def __init__(self, serial):
        self.RuntimeSerialNumber = serial


def _module(monkeypatch):
    scriptcontext = types.SimpleNamespace(sticky={})
    monkeypatch.setitem(sys.modules, "scriptcontext", scriptcontext)
    spec = importlib.util.spec_from_file_location(
        "test_document_runtime_module",
        MODULE_PATH,
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module, scriptcontext


def test_values_are_isolated_by_document_runtime_serial(monkeypatch):
    runtime, scriptcontext = _module(monkeypatch)
    first = FakeDocument(101)
    second = FakeDocument(202)

    first_links = runtime.get_value(first, "links", lambda _: {})
    second_links = runtime.get_value(second, "links", lambda _: {})
    first_links["shared-link-id"] = "first"
    second_links["shared-link-id"] = "second"

    assert runtime.get_value(first, "links", lambda _: None) is first_links
    assert runtime.try_get_value(first, "links")["shared-link-id"] == "first"
    assert runtime.try_get_value(second, "links")["shared-link-id"] == "second"
    assert set(scriptcontext.sticky[runtime.REGISTRY_KEY]) == {101, 202}


def test_missing_lookup_does_not_create_document_state(monkeypatch):
    runtime, scriptcontext = _module(monkeypatch)

    assert runtime.try_get_value(FakeDocument(303), "links") is None
    assert runtime.REGISTRY_KEY not in scriptcontext.sticky


def test_removal_preserves_other_documents_and_cleans_empty_registry(monkeypatch):
    runtime, scriptcontext = _module(monkeypatch)
    first = FakeDocument(101)
    second = FakeDocument(202)
    runtime.set_value(first, "links", {"first": True})
    runtime.set_value(second, "links", {"second": True})

    assert runtime.remove_document(first) == {"links": {"first": True}}
    assert runtime.try_get_value(second, "links") == {"second": True}
    assert runtime.has_nonempty_value("links")

    assert runtime.remove_value(second, "links") == {"second": True}
    assert runtime.REGISTRY_KEY not in scriptcontext.sticky
    assert not runtime.has_nonempty_value("links")
