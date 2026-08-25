"""Floating Eto view for the standalone layer-panel mock."""

import Eto.Drawing as drawing
import Eto.Forms as forms


class LayerLikePanel(forms.Form):
    def __init__(self, state):
        super(LayerLikePanel, self).__init__()
        self._state = state
        self._items = {}
        self._root_items = []

        self.Title = "Layer Panel Mock"
        self.Resizable = True
        self.Padding = drawing.Padding(4)
        self.ClientSize = drawing.Size(*state.window_size)
        if state.window_location is not None:
            self.Location = drawing.Point(*state.window_location)

        self._tree = forms.TreeGridView()
        self._tree.ShowHeader = True
        self._tree.AllowMultipleSelection = False
        self._tree.Columns.Add(self._column("Name", forms.TextBoxCell(0), 220))
        self._tree.Columns.Add(
            self._column("Visible", forms.CheckBoxCell(1), 58)
        )
        self._tree.Columns.Add(
            self._column("Lock", forms.CheckBoxCell(2), 48)
        )
        self._tree.SelectionChanged += self._selection_changed

        layout = forms.DynamicLayout()
        layout.DefaultSpacing = drawing.Size(2, 2)
        layout.AddSeparateRow(
            self._button("+", "New layer", self._add_layer),
            self._button("−", "Delete selected layer", self._remove_layer),
            self._button("Expand", "Expand every branch", self._expand_all),
            self._button("Collapse", "Collapse every branch", self._collapse_all),
            None,
            self._button("Show/Hide", "Toggle selected layer visibility", self._toggle_visible),
            self._button("Lock", "Toggle selected layer lock", self._toggle_locked),
        )
        layout.Add(self._tree, yscale=True)
        self.Content = layout
        self.Closing += self._save_state
        self._refresh()

    @staticmethod
    def _column(title, cell, width):
        column = forms.GridColumn()
        column.HeaderText = title
        column.DataCell = cell
        column.Width = width
        return column

    @staticmethod
    def _button(text, tooltip, handler):
        button = forms.Button()
        button.Text = text
        button.ToolTip = tooltip
        button.Click += handler
        return button

    def _tree_item(self, node):
        item = forms.TreeGridItem()
        item.Values = [node.name, node.visible, node.locked]
        item.Tag = node
        item.Expanded = node.expanded
        self._items[node.key] = item
        for child in node.children:
            item.Children.Add(self._tree_item(child))
        return item

    def _refresh(self):
        self._items = {}
        self._root_items = []
        root = forms.TreeGridItem()
        for node in self._state.roots:
            item = self._tree_item(node)
            self._root_items.append(item)
            root.Children.Add(item)
        self._tree.DataStore = root
        self._tree.SelectedItem = self._items.get(self._state.selected_key)

    def _selected_node(self):
        item = self._tree.SelectedItem
        return None if item is None else item.Tag

    def _selection_changed(self, sender, event):
        node = self._selected_node()
        self._state.selected_key = None if node is None else node.key

    def _add_layer(self, sender, event):
        parent = self._selected_node()
        self._state.add_layer(None if parent is None else parent.key)
        self._refresh()

    def _remove_layer(self, sender, event):
        node = self._selected_node()
        if node is not None and self._state.remove_layer(node.key):
            self._refresh()

    def _toggle_visible(self, sender, event):
        node = self._selected_node()
        if node is not None:
            node.visible = not node.visible
            self._refresh()

    def _toggle_locked(self, sender, event):
        node = self._selected_node()
        if node is not None:
            node.locked = not node.locked
            self._refresh()

    def _expand_all(self, sender, event):
        self._state.set_expanded(True)
        self._refresh()

    def _collapse_all(self, sender, event):
        self._state.set_expanded(False)
        self._refresh()

    def _save_item_state(self, item):
        node = item.Tag
        if node is not None:
            node.expanded = item.Expanded
            node.visible = bool(item.Values[1])
            node.locked = bool(item.Values[2])
        for child in item.Children:
            self._save_item_state(child)

    def _save_state(self, sender, event):
        for item in self._root_items:
            self._save_item_state(item)
        self._state.window_location = (self.Location.X, self.Location.Y)
        self._state.window_size = (self.ClientSize.Width, self.ClientSize.Height)
