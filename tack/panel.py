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


def _panel_object(doc, object_id):
    try:
        return doc.Objects.Find(System.Guid.Parse(str(object_id)))
    except Exception:
        return None


def _object_display_name(doc, object_id):
    try:
        obj = _panel_object(doc, object_id)
        name = None if obj is None else obj.Attributes.Name
        return (
            str(name).strip()
            if name and str(name).strip()
            else _short_id(object_id)
        )
    except Exception:
        return _short_id(object_id)


def _object_type_label(doc, object_id):
    try:
        obj = _panel_object(doc, object_id)
        if obj is None:
            return "Obj"
        geometry = obj.Geometry
        object_type = obj.ObjectType
        if object_type == Rhino.DocObjects.ObjectType.Brep:
            return "Polysrf" if geometry.Faces.Count > 1 else "Srf"
        if object_type == Rhino.DocObjects.ObjectType.Curve:
            return "Crv"
        if object_type == Rhino.DocObjects.ObjectType.Surface:
            return "Srf"
        if object_type == Rhino.DocObjects.ObjectType.Extrusion:
            return "Extr"
        if object_type == Rhino.DocObjects.ObjectType.Mesh:
            return "Mesh"
        if object_type == Rhino.DocObjects.ObjectType.SubD:
            return "SubD"
        if object_type == Rhino.DocObjects.ObjectType.Point:
            return "Pnt"
        if object_type == Rhino.DocObjects.ObjectType.PointSet:
            return "Pts"
        if object_type == Rhino.DocObjects.ObjectType.Hatch:
            return "Htch"
        if object_type == Rhino.DocObjects.ObjectType.TextDot:
            return "Dot"
        if object_type == Rhino.DocObjects.ObjectType.Annotation:
            return (
                "Txt"
                if isinstance(geometry, Rhino.Geometry.TextEntity)
                else "Ann"
            )
        if object_type == Rhino.DocObjects.ObjectType.InstanceReference:
            return "Blk"
        if object_type == Rhino.DocObjects.ObjectType.Light:
            return "Lgt"
        if object_type == Rhino.DocObjects.ObjectType.ClipPlane:
            return "Clp"
    except Exception:
        pass
    return "Obj"


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

        self._context_item = None
        self._context_header = forms.ButtonMenuItem()
        self._context_header.Text = "Tack"
        self._context_header.Enabled = False
        select_object = forms.ButtonMenuItem()
        select_object.Text = "Select object"
        select_object.Click += self._select_context_object
        context_menu = forms.ContextMenu()
        context_menu.Items.Add(self._context_header)
        context_menu.Items.Add(select_object)
        context_menu.Opening += self._context_menu_opening
        self._tree.ContextMenu = context_menu
        self._select_object_menu_item = select_object

        self._remove = _icon_button(
            panel,
            "x",
            "#757575",
            "Delete Tacks associated with this object",
            _ICON_SIZE,
        )
        self._remove.Enabled = False
        self._remove.Click += self._remove_selected

        self._tack_details = forms.Label()
        self._tack_details.TextAlignment = forms.TextAlignment.Left
        self._reset_transform = forms.Button()
        self._reset_transform.Text = "Reset transform to original"
        self._reset_transform.Click += self._reset_selected_transform

        details_row = forms.DynamicLayout()
        details_row.DefaultSpacing = drawing.Size(0, 0)
        details_row.AddRow(self._tack_details, None)
        reset_row = forms.DynamicLayout()
        reset_row.DefaultSpacing = drawing.Size(0, 0)
        reset_row.AddRow(self._reset_transform, None)
        self._tack_inspector = forms.DynamicLayout()
        self._tack_inspector.Padding = drawing.Padding(4)
        self._tack_inspector.DefaultSpacing = drawing.Size(0, 2)
        self._tack_inspector.AddRow(details_row)
        self._tack_inspector.AddRow(reset_row)

        layout = forms.DynamicLayout()
        layout.Padding = drawing.Padding(5)
        layout.DefaultSpacing = drawing.Size(6, 6)
        layout.AddRow(self._button_bar())
        layout.Add(self._tree, yscale=True)
        layout.AddRow(self._tack_inspector)
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

    def _update_remove_button(self, enabled):
        self._remove.Enabled = enabled
        self._remove.Image = _svg_icon(
            self._panel,
            "x",
            "#ef5350" if enabled else "#757575",
            _ICON_SIZE,
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

    @staticmethod
    def _delete_link_id(tag):
        if tag is None:
            return None
        outgoing = tag["outgoing_link_ids"]
        if len(outgoing) == 1:
            return outgoing[0]
        if not outgoing:
            return tag["incoming_link_id"]
        return None

    def _selected_link_id(self):
        return self._delete_link_id(self._item_tag(self._tree.SelectedItem))

    def _selected_link_ids(self):
        tag = self._item_tag(self._tree.SelectedItem)
        return () if tag is None else tag["direct_link_ids"]

    def _apply_tree_selection(self, item):
        from tack import plane_link

        tag = self._item_tag(item)
        link_id = self._delete_link_id(tag)
        self._update_remove_button(
            bool(() if tag is None else tag["direct_link_ids"])
        )
        self._context_item = tag
        self._update_tack_inspector(link_id)
        plane_link.set_tree_selection(
            self._doc,
            None if tag is None else tag["object_id"],
            () if tag is None else tag["direct_link_ids"],
        )

    def _update_tack_inspector(self, link_id):
        from tack import plane_link_metadata

        link = (
            None
            if link_id is None
            else plane_link_metadata.read_link(self._doc, link_id)
        )
        if link is None:
            self._tack_details.Text = "Select a Tack to inspect"
            self._tack_details.ToolTip = ""
            self._reset_transform.Visible = False
            return
        mode = plane_link_metadata.link_mode(link)
        self._tack_details.Text = "Tack ID: {}\nMode: {}".format(
            _short_id(link["link_id"]),
            "Inherit Only" if mode == "inherit_only" else "Attached",
        )
        self._tack_details.ToolTip = str(link["link_id"])
        self._reset_transform.Visible = mode == "inherit_only"

    def _reset_selected_transform(self, sender, event):
        from tack import plane_link

        link_id = self._selected_link_id()
        if link_id is None or not plane_link.reset_inherit_transform(
            self._doc,
            link_id,
        ):
            Rhino.RhinoApp.WriteLine("The selected Tack cannot reset its transform.")
        self.refresh()

    def _selection_changed(self, sender, event):
        self._apply_tree_selection(self._tree.SelectedItem)

    def _tree_mouse_down(self, sender, event):
        cell = self._tree.GetCellAt(event.Location)
        self._context_item = self._item_tag(cell.Item)

    def _context_link_id(self):
        link_id = self._delete_link_id(self._context_item)
        if link_id is None and self._context_item is not None:
            direct = self._context_item["direct_link_ids"]
            link_id = direct[0] if direct else None
        return link_id

    def _context_menu_opening(self, sender, event):
        link_id = self._context_link_id()
        self._context_header.Text = (
            "Tack {}".format(_short_id(link_id)) if link_id is not None else "Tack"
        )
        self._select_object_menu_item.Enabled = self._context_item is not None

    def _select_context_object(self, sender, event):
        from tack import utils

        object_id = (
            None if self._context_item is None else self._context_item["object_id"]
        )
        obj = utils.find_object(self._doc, object_id)
        if obj is None:
            Rhino.RhinoApp.WriteLine("The selected Tack object no longer exists.")
            return
        self._doc.Objects.UnselectAll()
        if not obj.Select(True):
            Rhino.RhinoApp.WriteLine("The Tack object could not be selected.")
        self._doc.Views.Redraw()

    def _remove_selected(self, sender, event):
        link_ids = self._selected_link_ids()
        count = len(link_ids)
        if not count:
            return
        confirmation = Rhino.UI.Dialogs.ShowMessage(
            "Delete {} Tack{} associated with this object?".format(
                count,
                "" if count == 1 else "s",
            ),
            "Delete Tacks",
            Rhino.UI.ShowMessageButton.YesNo,
            Rhino.UI.ShowMessageIcon.Warning,
        )
        if confirmation != Rhino.UI.ShowMessageResult.Yes:
            return
        from tack import plane_link

        plane_link.remove_links(self._doc, link_ids)
        self.refresh()

    def refresh(self):
        from tack import link_graph
        from tack import plane_link

        selected_object_id = plane_link.selected_object_id(self._doc)
        active = list(plane_link.states(self._doc, create=False).values())
        children_by_parent = {}
        incoming_by_child = {}
        object_ids = {}
        incoming = set()
        for state in active:
            parent_key = link_graph.object_key(state["parent_id"])
            child_key = link_graph.object_key(state["child_id"])
            object_ids[parent_key] = state["parent_id"]
            object_ids[child_key] = state["child_id"]
            children_by_parent.setdefault(parent_key, []).append(state)
            incoming_by_child.setdefault(child_key, []).append(state)
            incoming.add(child_key)

        def link_sort_key(state):
            return (
                state["link"].get("created_at") or "",
                str(state["link_id"]),
            )

        for children in children_by_parent.values():
            children.sort(key=link_sort_key)
        for parents in incoming_by_child.values():
            parents.sort(key=link_sort_key)

        def object_sort_key(key):
            children = children_by_parent.get(key, ())
            return link_sort_key(children[0]) if children else ("", key)

        row_by_key = {}
        tree_rows = []

        def tree_item(key, incoming_link_id=None, path=()):
            outgoing = children_by_parent.get(key, ())
            direct = tuple(incoming_by_child.get(key, ())) + tuple(outgoing)
            item = forms.TreeGridItem()
            item.Values = [
                "{} {}".format(
                    _object_type_label(self._doc, object_ids[key]),
                    _object_display_name(self._doc, object_ids[key]),
                )
            ]
            item.Tag = {
                "object_id": object_ids[key],
                "incoming_link_id": incoming_link_id,
                "outgoing_link_ids": tuple(
                    state["link_id"] for state in outgoing
                ),
                "direct_link_ids": tuple(state["link_id"] for state in direct),
            }
            item.Expanded = True
            tree_rows.append(item)
            row_by_key.setdefault(key, len(tree_rows) - 1)
            if key in path:
                return item
            next_path = path + (key,)
            for state in outgoing:
                child_key = link_graph.object_key(state["child_id"])
                item.Children.Add(
                    tree_item(child_key, state["link_id"], next_path)
                )
            return item

        root = forms.TreeGridItem()
        root_keys = [key for key in children_by_parent if key not in incoming]
        if active and not root_keys:
            root_keys = list(children_by_parent)
        for key in sorted(root_keys, key=object_sort_key):
            root.Children.Add(tree_item(key))

        selected_row = None
        if selected_object_id is not None:
            selected_row = row_by_key.get(
                link_graph.object_key(selected_object_id)
            )
        self._tree.DataStore = root
        if selected_row is not None:
            self._tree.SelectRow(selected_row)
        self._apply_tree_selection(self._tree.SelectedItem)


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
