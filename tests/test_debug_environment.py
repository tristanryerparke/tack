import io
import runpy
import sys
from contextlib import redirect_stdout
from pathlib import Path


UTILS = Path(__file__).parents[1] / "tack" / "utils.py"


def _utils_namespace(monkeypatch, environment):
    monkeypatch.setitem(sys.modules, "System", object())
    monkeypatch.delenv("debug", raising=False)
    monkeypatch.delenv("TACK_DEBUG", raising=False)
    for name, value in environment.items():
        monkeypatch.setenv(name, value)
    return runpy.run_path(str(UTILS))


def test_tack_debug_is_disabled_without_watcher_environment(monkeypatch):
    utils = _utils_namespace(monkeypatch, {})
    output = io.StringIO()

    with redirect_stdout(output):
        utils["debug"]("hidden")

    assert utils["DEBUG"] is False
    assert output.getvalue() == ""


def test_tack_debug_accepts_watcher_and_named_environment(monkeypatch):
    for environment in ({"debug": "true"}, {"TACK_DEBUG": "1"}):
        utils = _utils_namespace(monkeypatch, environment)
        output = io.StringIO()

        with redirect_stdout(output):
            utils["debug"]("visible")

        assert utils["DEBUG"] is True
        assert output.getvalue() == "visible\n"
