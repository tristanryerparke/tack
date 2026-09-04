"""Python-owned Eto content for Tack's per-document dockable panel."""

import System

import Eto.Drawing as drawing
import Eto.Forms as forms
import Rhino


PANEL_ID = System.Guid("F793A6F1-E37C-4F3C-A39A-65D4F720E8D2")


def _action_button(panel, label, action):
    button = forms.Button()
    button.Text = label

    def run_action(sender, event):
        panel.RunTackCommand(action)

    button.Click += run_action
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


def _display_toggle(panel, doc):
    from tack import plane_link

    button = forms.Button()

    def update_label():
        button.Text = (
            "Hide Tacks" if plane_link.display_enabled(doc) else "Show Tacks"
        )

    def toggle_display(sender, event):
        action = "hide" if plane_link.display_enabled(doc) else "show"
        panel.RunTackCommand(action)
        update_label()

    update_label()
    button.Click += toggle_display
    return button


def _content(panel, doc):
    layout = forms.DynamicLayout()
    layout.Padding = drawing.Padding(5)
    layout.DefaultSpacing = drawing.Size(6, 6)
    crosshair_slider, crosshair_label_container = _crosshair_size_slider(
        panel,
        doc,
    )
    crosshair_layout = forms.DynamicLayout()
    crosshair_layout.DefaultSpacing = drawing.Size(0, 2)
    crosshair_layout.AddRow(crosshair_label_container)
    crosshair_layout.AddRow(crosshair_slider)
    layout.AddRow(_action_button(panel, "Add Tack", "add"))
    layout.AddRow(_display_toggle(panel, doc))
    layout.AddRow(_action_button(panel, "Clear", "clear"))
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
