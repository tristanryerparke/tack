import ast
from pathlib import Path


HANDLERS = Path(__file__).parents[1] / "tack" / "handlers.py"
LINK = Path(__file__).parents[1] / "tack" / "link.py"
SCHEDULER = Path(__file__).parents[1] / "tack" / "scheduler.py"


def _function(tree, name):
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


def test_tack_subscribes_to_object_lifecycle_and_close_callbacks():
    subscribe = _function(ast.parse(HANDLERS.read_text()), "subscribe")
    subscriptions = {
        node.target.attr
        for node in ast.walk(subscribe)
        if isinstance(node, ast.AugAssign)
        and isinstance(node.target, ast.Attribute)
    }

    assert subscriptions == {
        "AddRhinoObject",
        "DeleteRhinoObject",
        "UndeleteRhinoObject",
        "CloseDocument",
    }


def test_event_handler_defers_maintenance_to_the_idle_scheduler():
    handler = _function(ast.parse(HANDLERS.read_text()), "_HandleRhinoObjectEvent")
    calls = _called_attributes(handler)

    assert "expire_link_ids" in calls
    assert "maintain_link" not in calls


def test_unsubscribe_disarms_the_idle_scheduler():
    unsubscribe = _function(ast.parse(HANDLERS.read_text()), "unsubscribe")
    calls = _called_attributes(unsubscribe)

    assert "disarm" in calls


def test_scheduler_pumps_on_rhino_app_idle_and_exposes_synchronous_drain():
    tree = ast.parse(SCHEDULER.read_text())

    ensure_armed = _function(tree, "_ensure_armed")
    targets = {
        node.target.attr
        for node in ast.walk(ensure_armed)
        if isinstance(node, ast.AugAssign) and isinstance(node.target, ast.Attribute)
    }
    assert "Idle" in targets

    assert hasattr(ast, "FunctionDef")
    names = {
        node.name
        for node in tree.body
        if isinstance(node, ast.FunctionDef)
    }
    assert "expire_link_ids" in names
    assert "solve_now" in names


def test_final_shape_maintenance_accepts_no_replace_objects():
    tree = ast.parse(LINK.read_text())
    for name in ("event_may_affect_link", "maintain_link"):
        function = _function(tree, name)
        arguments = {argument.arg for argument in function.args.args}
        assert "old_obj" not in arguments
        assert "new_obj" not in arguments
