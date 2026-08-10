import ast
from pathlib import Path


HANDLERS = Path(__file__).parents[1] / "tack" / "handlers.py"
LINK = Path(__file__).parents[1] / "tack" / "link.py"
SCHEDULER = Path(__file__).parents[1] / "tack" / "scheduler.py"
RUNTIME = Path(__file__).parents[1] / "tack" / "runtime.py"


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


def test_event_handler_defers_maintenance_to_the_command_scheduler():
    handler = _function(ast.parse(HANDLERS.read_text()), "_HandleRhinoObjectEvent")
    calls = _called_attributes(handler)

    assert "expire_link_ids" in calls
    assert "maintain_link" not in calls


def test_scheduler_lives_with_tack_handlers():
    tree = ast.parse(HANDLERS.read_text())
    assert "arm" in _called_attributes(_function(tree, "subscribe"))
    assert "disarm" in _called_attributes(_function(tree, "unsubscribe"))


def test_scheduler_always_listens_for_command_end_and_exposes_synchronous_drain():
    tree = ast.parse(SCHEDULER.read_text())

    arm = _function(tree, "arm")
    targets = {
        node.target.attr
        for node in ast.walk(arm)
        if isinstance(node, ast.AugAssign) and isinstance(node.target, ast.Attribute)
    }
    assert targets == {"EndCommand"}

    names = {
        node.name
        for node in tree.body
        if isinstance(node, ast.FunctionDef)
    }
    assert "_ensure_armed" not in names
    assert {"arm", "_on_end_command", "expire_link_ids", "solve_now"} <= names


def test_parent_events_override_the_allowed_child_movement_setting():
    handler = _function(ast.parse(HANDLERS.read_text()), "_HandleRhinoObjectEvent")
    assert "mark_roles_dirty" in _called_attributes(handler)
    source = LINK.read_text()
    assert '"child" in dirty_roles' in source
    assert '"parent" not in dirty_roles' in source
    assert "parent_was_stationary" not in source
    assert "def mark_roles_dirty" in RUNTIME.read_text()


def test_final_shape_maintenance_accepts_no_replace_objects():
    tree = ast.parse(LINK.read_text())
    for name in ("event_may_affect_link", "maintain_link"):
        function = _function(tree, name)
        arguments = {argument.arg for argument in function.args.args}
        assert "old_obj" not in arguments
        assert "new_obj" not in arguments
