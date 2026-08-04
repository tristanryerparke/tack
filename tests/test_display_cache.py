import ast
from pathlib import Path


ROOT = Path(__file__).parents[1]
CONDUIT = ROOT / "tack" / "conduit.py"
RUNTIME = ROOT / "tack" / "runtime.py"
CLEAR = ROOT / "tack_clear.py"
RESTORE = ROOT / "tack_restore.py"


def _function(path, name):
    tree = ast.parse(path.read_text())
    return next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == name
    )


def _called_attributes(node):
    return {
        call.func.attr
        for call in ast.walk(node)
        if isinstance(call, ast.Call)
        and isinstance(call.func, ast.Attribute)
    }


def test_conduit_draws_only_from_runtime_cache():
    draw = next(
        node
        for node in ast.walk(ast.parse(CONDUIT.read_text()))
        if isinstance(node, ast.FunctionDef) and node.name == "DrawForeground"
    )
    names = {node.id for node in ast.walk(draw) if isinstance(node, ast.Name)}
    calls = _called_attributes(draw)

    assert "metadata" not in names
    assert "link" not in names
    assert "all_links" not in calls
    assert "inspect_link" not in calls
    assert "display" in CONDUIT.read_text()


def test_runtime_builds_clean_cache_and_discards_it_on_stop():
    source = RUNTIME.read_text()
    assert "set_display_clean" in source
    assert 'sc.sticky.pop(utils.RUNTIME_KEY, None)' in source
    assert 'sc.sticky.pop(utils.CONDUIT_KEY, None)' in source


def test_clear_and_restore_use_cache_lifecycle_entry_points():
    clear_calls = _called_attributes(_function(CLEAR, "RunCommand"))
    restore_calls = _called_attributes(_function(RESTORE, "RunCommand"))

    assert "stop_runtime" in clear_calls
    assert {"stop_runtime", "start_runtime"} <= restore_calls
