"""Python-owned Eto content for Tack's per-document dockable panel."""

import System

import Eto.Drawing as drawing
import Eto.Forms as forms
import Rhino


PANEL_ID = System.Guid("F793A6F1-E37C-4F3C-A39A-65D4F720E8D2")
_ICON_SIZE = 20


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
    if name != "plus":
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


def _crosshair_size_slider(panel, doc):
    from tack import analytic_plane
    from tack import plane_link

    slider = Rhino.UI.Controls.Slider(panel, False)
    slider.SetMinMax(
        analytic_plane.CROSSHAIR_SIZE_MIN,
        analytic_plane.CROSSHAIR_SIZE_MAX,
    )
    slider.Decimals = 0
    slider.Value1 = plane_link.crosshair_size(doc)
    label = forms.Label()
    label.Text = "Crosshair size"
    label.TextAlignment = forms.TextAlignment.Left
    label_container = forms.DynamicLayout()
    label_container.DefaultSpacing = drawing.Size(0, 0)
    label_container.AddRow(label, None)

    def set_size(sender, event):
        if event.PropertyName == "Value1":
            plane_link.set_crosshair_size(doc, sender.Value1)

    slider.PropertyChanged += set_size
    return slider, label_container


def _crosshair_thickness_slider(panel, doc):
    from tack import analytic_plane
    from tack import plane_link

    slider = Rhino.UI.Controls.Slider(panel, False)
    slider.SetMinMax(
        analytic_plane.CROSSHAIR_THICKNESS_MIN,
        analytic_plane.CROSSHAIR_THICKNESS_MAX,
    )
    slider.Decimals = 0
    slider.Value1 = plane_link.crosshair_thickness(doc)
    label = forms.Label()
    label.Text = "Crosshair line width"
    label.TextAlignment = forms.TextAlignment.Left
    label_container = forms.DynamicLayout()
    label_container.DefaultSpacing = drawing.Size(0, 0)
    label_container.AddRow(label, None)

    def set_thickness(sender, event):
        if event.PropertyName == "Value1":
            plane_link.set_crosshair_thickness(doc, sender.Value1)

    slider.PropertyChanged += set_thickness
    return slider, label_container


def _button_bar(panel, doc):
    from tack import plane_link

    bar = forms.DynamicLayout()
    bar.DefaultSpacing = drawing.Size(2, 0)

    add = _icon_button(panel, "plus", "#4caf50", "Add Tack")
    add.Click += lambda sender, event: panel.RunTackCommand("add")

    display = _icon_button(
        panel,
        "eye-off",
        "#9e9e9e",
        "Show or hide Tacks",
        _ICON_SIZE - 4,
    )

    def update_display_button():
        visible = plane_link.display_enabled(doc)
        display.Image = _svg_icon(
            panel,
            "eye-off" if visible else "eye",
            "#9e9e9e",
            _ICON_SIZE - 4,
        )

    def toggle_display(sender, event):
        action = "hide" if plane_link.display_enabled(doc) else "show"
        panel.RunTackCommand(action)
        update_display_button()

    display.Click += toggle_display
    update_display_button()

    clear = _icon_button(
        panel,
        "trash",
        "#ef5350",
        "Clear all Tacks",
        _ICON_SIZE - 4,
    )
    clear.Click += lambda sender, event: panel.RunTackCommand("clear")

    bar.AddRow(add, display, clear, None)
    return bar


def _content(panel, doc):
    layout = forms.DynamicLayout()
    layout.Padding = drawing.Padding(5)
    layout.DefaultSpacing = drawing.Size(6, 6)
    crosshair_slider, crosshair_label_container = _crosshair_size_slider(
        panel,
        doc,
    )
    thickness_slider, thickness_label_container = _crosshair_thickness_slider(
        panel,
        doc,
    )
    crosshair_layout = forms.DynamicLayout()
    crosshair_layout.DefaultSpacing = drawing.Size(0, 2)
    crosshair_layout.AddRow(crosshair_label_container)
    crosshair_layout.AddRow(crosshair_slider)
    crosshair_layout.AddRow(thickness_label_container)
    crosshair_layout.AddRow(thickness_slider)
    layout.AddRow(_button_bar(panel, doc))
    layout.AddRow(crosshair_layout)
    layout.AddRow(None)
    return layout


def install(document_serial_number):
    """Install the Python Eto content into one C#-registered panel instance."""
    doc = Rhino.RhinoDoc.FromRuntimeSerialNumber(document_serial_number)
    if doc is None:
        raise RuntimeError("Tack panel document is unavailable.")

    panel = Rhino.UI.Panels.GetPanel(PANEL_ID, doc)
    if panel is None:
        raise RuntimeError("Tack panel instance is unavailable.")

    panel.SetPythonContent(_content(panel, doc))
