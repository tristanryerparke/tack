"""Python-owned Eto content for Tack's per-document dockable panel."""

import System

import Eto.Drawing as drawing
import Eto.Forms as forms
import Rhino


PANEL_ID = System.Guid("F793A6F1-E37C-4F3C-A39A-65D4F720E8D2")
_ICON_SIZE = 20
_PANEL_VIEWS = {}


def _svg_icon(panel, name, color, size=_ICON_SIZE):
    resource_name = "Tack.Resources.{}.svg".format(name)
    stream = panel.GetType().Assembly.GetManifestResourceStream(resource_name)
    if stream is None:
        raise RuntimeError("Missing panel icon: {}".format(resource_name))
    reader = System.IO.StreamReader(stream)
    try:
        svg = reader.ReadToEnd()
    finally:
        reader.Dispose()
        stream.Dispose()
    if name not in ("plus", "x"):
        svg = svg.replace("currentColor", color)
    else:
        opening_end = svg.index(">") + 1
        opening = svg[:opening_end]
        paths = svg[opening_end : svg.rindex("</svg>")]
        outline_width = 2.0 + 2.0 * 24.0 / size
        outlined_opening = opening.replace(
            "currentColor",
            "#000000",
        ).replace(
            'stroke-width="2"',
            'stroke-width="{}"'.format(outline_width),
        )
        colored_opening = opening.replace("currentColor", color)
        svg = outlined_opening + paths + colored_opening + paths + "</svg>"
    bitmap = Rhino.UI.DrawingUtilities.BitmapFromSvg(svg, size, size)
    return Rhino.UI.EtoExtensions.ToEto(bitmap)


def _icon_button(panel, name, color, tooltip, icon_size=_ICON_SIZE):
    button = Rhino.UI.Controls.ImageButton()
    button.Image = _svg_icon(panel, name, color, icon_size)
    button.Size = drawing.Size(22, 22)
    button.ToolTip = tooltip
    return button


def _short_id(object_id):
    return str(object_id).split("-", 1)[0]


class _PanelView:
    def __init__(self, panel, doc):
        self._panel = panel
        self._doc = doc

        self._tree = forms.TreeGridView()
        self._tree.ShowHeader = False
        self._tree.AllowMultipleSelection = False
        column = forms.GridColumn()
        column.DataCell = forms.TextBoxCell(0)
        column.Width = 260
        self._tree.Columns.Add(column)
        self._tree.SelectionChanged += self._selection_changed
        self._tree.MouseDown += self._tree_mouse_down

        self._context_object_id = None
        select_object = forms.ButtonMenuItem()
        select_object.Text = "Select object"
        select_object.Click += self._select_context_object
        context_menu = forms.ContextMenu()
        context_menu.Items.Add(select_object)
        context_menu.Opening += self._context_menu_opening
        self._tree.ContextMenu = context_menu
        self._select_object_menu_item = select_object

        self._remove = _icon_button(
            panel,
            "x",
            "#ef5350",
            "Delete selected Tack",
            _ICON_SIZE,
        )
        self._remove.Enabled = False
        self._remove.Click += self._remove_selected

        layout = forms.DynamicLayout()
        layout.Padding = drawing.Padding(5)
        layout.DefaultSpacing = drawing.Size(6, 6)
        layout.AddRow(self._button_bar())
        layout.Add(self._tree, yscale=True)
        self.control = layout
        self.refresh()

    def _button_bar(self):
        from tack import plane_link

        bar = forms.DynamicLayout()
        bar.DefaultSpacing = drawing.Size(2, 0)

        add = _icon_button(self._panel, "plus", "#4caf50", "Add Tack")
        add.Click += self._add

        self._display = _icon_button(
            self._panel,
            "eye-off",
            "#9e9e9e",
            "Show or hide Tacks",
            _ICON_SIZE - 4,
        )
        self._display.Click += self._toggle_display
        self._update_display_button(plane_link.display_enabled(self._doc))

        clear = _icon_button(
            self._panel,
            "trash",
            "#ef5350",
            "Clear all Tacks",
            _ICON_SIZE - 4,
        )
        clear.Click += self._clear

        settings = _icon_button(
            self._panel,
            "settings",
            "#9e9e9e",
            "Tack Settings",
            _ICON_SIZE - 4,
        )
        settings.Click += lambda sender, event: self._panel.RunTackCommand(
            "settings"
        )

        bar.AddRow(add, self._display, self._remove, clear, settings, None)
        return bar

    def _update_display_button(self, visible):
        self._display.Image = _svg_icon(
            self._panel,
            "eye-off" if visible else "eye",
            "#9e9e9e",
            _ICON_SIZE - 4,
        )

    def _add(self, sender, event):
        self._panel.RunTackCommand("add")
        self.refresh()

    def _toggle_display(self, sender, event):
        from tack import plane_link

        action = "hide" if plane_link.display_enabled(self._doc) else "show"
        self._panel.RunTackCommand(action)
        self._update_display_button(plane_link.display_enabled(self._doc))

    def _clear(self, sender, event):
        self._panel.RunTackCommand("clear")
        self.refresh()

    @staticmethod
    def _item_tag(item):
        return None if item is None else item.Tag

    def _selected_link_id(self):
        tag = self._item_tag(self._tree.SelectedItem)
        if tag is None or tag["role"] != "parent":
            return None
        return tag["link_id"]

    def _selection_changed(self, sender, event):
        tag = self._item_tag(self._tree.SelectedItem)
        self._remove.Enabled = tag is not None and tag["role"] == "parent"
        self._context_object_id = None if tag is None else tag["object_id"]

    def _tree_mouse_down(self, sender, event):
        cell = self._tree.GetCellAt(event.Location)
        tag = self._item_tag(cell.Item)
        self._context_object_id = None if tag is None else tag["object_id"]

    def _context_menu_opening(self, sender, event):
        self._select_object_menu_item.Enabled = self._context_object_id is not None

    def _select_context_object(self, sender, event):
        from tack import utils

        obj = utils.find_object(self._doc, self._context_object_id)
        if obj is None:
            Rhino.RhinoApp.WriteLine("The selected Tack object no longer exists.")
            return
        self._doc.Objects.UnselectAll()
        if not obj.Select(True):
            Rhino.RhinoApp.WriteLine("The Tack object could not be selected.")
        self._doc.Views.Redraw()

    def _remove_selected(self, sender, event):
        link_id = self._selected_link_id()
        if link_id is None:
            return
        confirmation = Rhino.UI.Dialogs.ShowMessage(
            "Delete Tack {}?".format(str(link_id)[:8]),
            "Delete Tack",
            Rhino.UI.ShowMessageButton.YesNo,
            Rhino.UI.ShowMessageIcon.Warning,
        )
        if confirmation != Rhino.UI.ShowMessageResult.Yes:
            return
        from tack import actions

        actions.remove(self._doc, link_id)
        self.refresh()

    def refresh(self):
        from tack import plane_link

        root = forms.TreeGridItem()
        active = sorted(
            plane_link.states(self._doc, create=False).values(),
            key=lambda state: str(state["parent_id"]),
        )
        for state in active:
            parent = forms.TreeGridItem()
            parent.Values = ["Parent {}".format(_short_id(state["parent_id"]))]
            parent.Tag = {
                "role": "parent",
                "link_id": state["link_id"],
                "object_id": state["parent_id"],
            }
            parent.Expanded = True

            child = forms.TreeGridItem()
            child.Values = ["Child {}".format(_short_id(state["child_id"]))]
            child.Tag = {
                "role": "child",
                "link_id": state["link_id"],
                "object_id": state["child_id"],
            }
            parent.Children.Add(child)
            root.Children.Add(parent)

        self._tree.DataStore = root
        self._remove.Enabled = False
        self._context_object_id = None


def refresh(doc):
    view = _PANEL_VIEWS.get(int(doc.RuntimeSerialNumber))
    if view is not None:
        view.refresh()


def forget(doc):
    _PANEL_VIEWS.pop(int(doc.RuntimeSerialNumber), None)


def install(document_serial_number):
    """Install the Python Eto content into one C#-registered panel instance."""
    doc = Rhino.RhinoDoc.FromRuntimeSerialNumber(document_serial_number)
    if doc is None:
        raise RuntimeError("Tack panel document is unavailable.")

    panel = Rhino.UI.Panels.GetPanel(PANEL_ID, doc)
    if panel is None:
        raise RuntimeError("Tack panel instance is unavailable.")

    view = _PanelView(panel, doc)
    _PANEL_VIEWS[int(doc.RuntimeSerialNumber)] = view
    panel.SetPythonContent(view.control)
