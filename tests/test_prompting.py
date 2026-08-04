import ast
from pathlib import Path


ROOT = Path(__file__).parents[1]
COMMAND_MENU = ROOT / "tack" / "prompting" / "command_menu.py"
PICKING = ROOT / "tack" / "prompting" / "picking.py"
ANCHOR_PICK_CONDUIT = ROOT / "tack" / "prompting" / "anchor_pick_conduit.py"


def _function(path, name):
    tree = ast.parse(path.read_text())
    return next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == name
    )


def test_tack_add_disables_normal_osnaps_and_restores_the_user_setting():
    tree = ast.parse(COMMAND_MENU.read_text())
    flag = next(
        node.value
        for node in tree.body
        if isinstance(node, ast.Assign)
        and any(
            isinstance(target, ast.Name)
            and target.id == "DISABLE_NORMAL_OSNAPS"
            for target in node.targets
        )
    )
    pick_link = _function(COMMAND_MENU, "pick_link")
    source = ast.unparse(pick_link)

    assert flag.value is True
    assert "ModelAidSettings.Osnap = False" in source
    assert any(
        isinstance(node, ast.Try)
        and any(
            isinstance(final_node, ast.Assign)
            and "ModelAidSettings.Osnap" in ast.unparse(final_node)
            for final_node in node.finalbody
        )
        for node in ast.walk(pick_link)
    )


def test_hovered_anchor_highlight_uses_size_six():
    draw = next(
        node
        for node in ast.walk(ast.parse(ANCHOR_PICK_CONDUIT.read_text()))
        if isinstance(node, ast.FunctionDef) and node.name == "DrawForeground"
    )
    point_size = next(
        node
        for node in ast.walk(draw)
        if isinstance(node, ast.IfExp)
        and isinstance(node.body, ast.Constant)
        and isinstance(node.orelse, ast.Constant)
        and node.orelse.value == 4
    )

    assert point_size.body.value == 6


def test_prompted_anchor_construction_points_remain_available():
    pick_anchor = _function(PICKING, "pick_anchor")
    calls = {
        node.func.attr
        for node in ast.walk(pick_anchor)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
    }

    assert "AddConstructionPoints" in calls
    assert "AddSnapPoints" in calls
