import ast
from pathlib import Path


HANDLERS = Path(__file__).parents[1] / "tack" / "handlers.py"
LINK = Path(__file__).parents[1] / "tack" / "link.py"


def _function(tree, name):
    return next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == name
    )


def test_tack_subscribes_only_to_final_object_callbacks():
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
    }


def test_final_shape_maintenance_accepts_no_replace_objects():
    tree = ast.parse(LINK.read_text())
    for name in ("event_may_affect_link", "maintain_link"):
        function = _function(tree, name)
        arguments = {argument.arg for argument in function.args.args}
        assert "old_obj" not in arguments
        assert "new_obj" not in arguments
