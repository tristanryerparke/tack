import ast
from pathlib import Path


ROOT = Path(__file__).parents[1]
CONDUIT = ROOT / "tack" / "conduit.py"
RUNTIME = ROOT / "tack" / "runtime.py"
CLEAR = ROOT / "commands" / "tack_clear.py"
RESTORE = ROOT / "commands" / "tack_restore.py"
HIDE = ROOT / "commands" / "tack_hide.py"
SHOW = ROOT / "commands" / "tack_show.py"
PAUSE = ROOT / "commands" / "tack_pause.py"
RESUME = ROOT / "commands" / "tack_resume.py"
COMMANDS = tuple(sorted((ROOT / "commands").glob("tack_*.py")))


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


def test_commands_import_watcher_only_on_demand_for_debug():
    assert COMMANDS
    for path in COMMANDS:
        tree = ast.parse(path.read_text())
        watcher_imports = [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom)
            and node.module == "rhino_watcher"
        ]
        assert watcher_imports, path

        debug_guard = next(
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.If)
            and isinstance(node.test, ast.UnaryOp)
            and isinstance(node.test.op, ast.Not)
            and isinstance(node.test.operand, ast.Attribute)
            and isinstance(node.test.operand.value, ast.Name)
            and node.test.operand.value.id == "utils"
            and node.test.operand.attr == "DEBUG"
        )
        debug_nodes = {
            descendant
            for statement in debug_guard.orelse
            for descendant in ast.walk(statement)
        }
        assert all(node in debug_nodes for node in watcher_imports), path
        assert any(
            isinstance(node, ast.ExceptHandler)
            and isinstance(node.type, ast.Name)
            and node.type.id == "ImportError"
            for node in debug_nodes
        ), path


def test_show_and_hide_control_only_the_runtime_conduit():
    runtime_source = RUNTIME.read_text()
    hide = _function(RUNTIME, "hide_display")
    show = _function(RUNTIME, "show_display")

    assert "active_conduit.Enabled = False" in runtime_source
    assert "_ensure_conduit()" in ast.unparse(show)
    assert "RUNTIME_KEY" in ast.unparse(show)

    hide_calls = _called_attributes(_function(HIDE, "RunCommand"))
    show_calls = _called_attributes(_function(SHOW, "RunCommand"))
    assert {"hide_display", "Redraw"} <= hide_calls
    assert {"show_display", "Redraw"} <= show_calls
    assert "return False" in ast.unparse(hide)


def test_pause_and_resume_control_only_the_handlers():
    pause_calls = _called_attributes(_function(PAUSE, "RunCommand"))
    resume_calls = _called_attributes(_function(RESUME, "RunCommand"))

    assert "unsubscribe" in pause_calls
    assert "subscribe" not in pause_calls
    assert "subscribe" in resume_calls
    assert not {
        "stop_runtime",
        "hide_display",
        "show_display",
    } & (pause_calls | resume_calls)


def test_clear_no_metadata_preserves_saved_link_metadata():
    clear = _function(CLEAR, "RunCommand")
    assert "no_metadata" in [arg.arg for arg in clear.args.args]

    metadata_removals = [
        call
        for call in ast.walk(clear)
        if isinstance(call, ast.Call)
        and isinstance(call.func, ast.Name)
        and call.func.id == "_clear_object_metadata"
    ]
    assert len(metadata_removals) == 1

    guard = next(
        node
        for node in ast.walk(clear)
        if isinstance(node, ast.If)
        and isinstance(node.test, ast.UnaryOp)
        and isinstance(node.test.op, ast.Not)
        and isinstance(node.test.operand, ast.Name)
        and node.test.operand.id == "no_metadata"
    )
    assert metadata_removals[0] in ast.walk(guard)
    assert "--no_metadata" in CLEAR.read_text()
