import ast
from pathlib import Path


ROOT = Path(__file__).parents[1]
ANALYZER = ROOT / "tack" / "analysis" / "polyline_vertex.py"
COMMAND_MENU = ROOT / "tack" / "prompting" / "command_menu.py"
INIT = ROOT / "tack" / "__init__.py"
LINK = ROOT / "tack" / "link.py"
METADATA = ROOT / "tack" / "metadata.py"
RUNTIME = ROOT / "tack" / "runtime.py"


def _function(path, name):
    return next(
        node
        for node in ast.parse(path.read_text()).body
        if isinstance(node, ast.FunctionDef) and node.name == name
    )


def test_polyline_vertex_analyzer_exposes_the_anchor_contract():
    source = ANALYZER.read_text()
    functions = {
        node.name
        for node in ast.parse(source).body
        if isinstance(node, ast.FunctionDef)
    }

    assert {
        "supports_vertex_anchors",
        "anchors",
        "resolve",
        "replacement_anchor",
        "remap_anchor",
    } <= functions
    assert 'ANCHOR_TYPE = "PolylineVertex"' in source
    assert "Rhino.Geometry.PolylineCurve" in source


def test_closed_polyline_duplicate_endpoint_is_not_an_anchor():
    vertex_count = ast.unparse(_function(ANALYZER, "_vertex_count"))

    assert "polyline.IsClosed" in vertex_count
    assert "EpsilonEquals" in vertex_count
    assert "count -= 1" in vertex_count


def test_polyline_vertex_is_registered_everywhere_anchors_are_resolved():
    assert '"PolylineVertex"' in METADATA.read_text()
    assert "polyline_vertex_analysis.ANCHOR_TYPE" in LINK.read_text()
    assert "polyline_vertex_analysis.ANCHOR_TYPE" in RUNTIME.read_text()
    assert '"analysis.polyline_vertex"' in INIT.read_text()


def test_prompting_selects_the_geometry_specific_vertex_analyzer():
    source = COMMAND_MENU.read_text()
    vertex_analyzer = ast.unparse(_function(COMMAND_MENU, "_vertex_analyzer"))
    pick_anchor = ast.unparse(_function(COMMAND_MENU, "_pick_anchor"))

    assert "polyline_vertex_analysis" in source
    assert "polyline_vertex_analysis" in vertex_analyzer
    assert "vertex_analyzer.ANCHOR_TYPE" in pick_anchor
    assert "analyzer.anchors(obj)" in pick_anchor
