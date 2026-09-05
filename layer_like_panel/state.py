"""UI state for the standalone layer-panel mock."""

from dataclasses import dataclass, field


@dataclass
class LayerNode:
    key: str
    name: str
    visible: bool = True
    locked: bool = False
    expanded: bool = True
    children: list = field(default_factory=list)


@dataclass
class LayerPanelState:
    roots: list
    selected_key: str = None
    window_location: tuple = None
    window_size: tuple = (360, 480)
    _next_number: int = 1

    def find(self, key):
        for node in self.walk():
            if node.key == key:
                return node
        return None

    def walk(self, nodes=None):
        for node in self.roots if nodes is None else nodes:
            yield node
            yield from self.walk(node.children)

    def add_layer(self, parent_key=None):
        node = LayerNode(
            "mock-{}".format(self._next_number),
            "Layer {:02d}".format(self._next_number),
        )
        self._next_number += 1
        parent = self.find(parent_key)
        if parent is None:
            self.roots.append(node)
        else:
            parent.children.append(node)
            parent.expanded = True
        self.selected_key = node.key
        return node

    def remove_layer(self, key):
        for nodes in [self.roots] + [node.children for node in self.walk()]:
            for node in nodes:
                if node.key == key:
                    nodes.remove(node)
                    self.selected_key = None
                    return True
        return False

    def set_expanded(self, expanded):
        for node in self.walk():
            node.expanded = expanded


def demo_state():
    """Return a deliberately mixed tree: some branches begin collapsed."""
    return LayerPanelState(
        roots=[
            LayerNode(
                "site",
                "Site",
                children=[
                    LayerNode("site-topo", "Topography"),
                    LayerNode("site-grid", "Grid", visible=False),
                ],
            ),
            LayerNode(
                "building",
                "Building",
                children=[
                    LayerNode(
                        "building-shell",
                        "Shell",
                        children=[
                            LayerNode("shell-walls", "Walls"),
                            LayerNode("shell-roof", "Roof", locked=True),
                        ],
                    ),
                    LayerNode(
                        "building-frame",
                        "Frame",
                        expanded=False,
                        children=[
                            LayerNode("frame-columns", "Columns"),
                            LayerNode("frame-beams", "Beams"),
                        ],
                    ),
                ],
            ),
            LayerNode(
                "details",
                "Details",
                expanded=False,
                children=[
                    LayerNode("details-notes", "Notes"),
                    LayerNode("details-dimensions", "Dimensions"),
                ],
            ),
        ]
    )
