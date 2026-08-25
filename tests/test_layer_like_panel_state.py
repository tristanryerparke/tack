from layer_like_panel.state import demo_state


def test_demo_state_has_nested_and_collapsed_nodes():
    state = demo_state()

    assert state.find("frame-columns").name == "Columns"
    assert state.find("building-frame").expanded is False
    assert state.find("details").expanded is False

    state.set_expanded(True)
    assert all(node.expanded for node in state.walk())

    added = state.add_layer("building-frame")
    assert state.find(added.key) is added
    assert state.find("building-frame").expanded is True
    assert state.remove_layer(added.key) is True
    assert state.find(added.key) is None
