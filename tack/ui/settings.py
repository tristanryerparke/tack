"""Tack's per-user display settings dialog."""

import Eto.Drawing as drawing
import Eto.Forms as forms
import Rhino

from tack.anchors import analytic_plane
from tack.links import runtime


def _slider(dialog, label_text, minimum, maximum, value, on_change):
    slider = Rhino.UI.Controls.Slider(dialog, False)
    slider.SetMinMax(minimum, maximum)
    slider.Decimals = 0
    slider.Value1 = value

    label = forms.Label()
    label.Text = label_text
    label.TextAlignment = forms.TextAlignment.Left
    label_container = forms.DynamicLayout()
    label_container.DefaultSpacing = drawing.Size(0, 0)
    label_container.AddRow(label, None)

    def change(sender, event):
        if event.PropertyName == "Value1":
            on_change(sender.Value1)

    slider.PropertyChanged += change
    return label_container, slider


def show(doc):
    if doc is None:
        return Rhino.Commands.Result.Cancel

    dialog = forms.Dialog[bool]()
    dialog.Title = "Tack Settings"
    dialog.ClientSize = drawing.Size(280, 230)
    dialog.Resizable = False
    Rhino.UI.EtoExtensions.UseRhinoStyle(dialog)

    layout = forms.DynamicLayout()
    layout.Padding = drawing.Padding(10)
    layout.DefaultSpacing = drawing.Size(0, 2)
    size_label, size_slider = _slider(
        dialog,
        "Crosshair size",
        analytic_plane.CROSSHAIR_SIZE_MIN,
        analytic_plane.CROSSHAIR_SIZE_MAX,
        runtime.crosshair_size(doc),
        lambda size: runtime.set_crosshair_size(doc, size),
    )
    thickness_label, thickness_slider = _slider(
        dialog,
        "Crosshair line width",
        analytic_plane.CROSSHAIR_THICKNESS_MIN,
        analytic_plane.CROSSHAIR_THICKNESS_MAX,
        runtime.crosshair_thickness(doc),
        lambda thickness: runtime.set_crosshair_thickness(doc, thickness),
    )
    selected_only = forms.CheckBox()
    selected_only.Text = "Show Selected Tacks Only"
    selected_only.Checked = runtime.show_selected_tacks_only(doc)
    selected_only.CheckedChanged += lambda sender, event: (
        runtime.set_show_selected_tacks_only(doc, bool(sender.Checked))
    )
    highlight_selected = forms.CheckBox()
    highlight_selected.Text = "Highlight Selected Objects"
    highlight_selected.Checked = runtime.highlight_selected_objects(doc)
    highlight_selected.CheckedChanged += lambda sender, event: (
        runtime.set_highlight_selected_objects(doc, bool(sender.Checked))
    )

    close = forms.Button()
    close.Text = "Close"
    close.Size = drawing.Size(80, 24)
    close.Click += lambda sender, event: dialog.Close(True)

    close_row = forms.StackLayout()
    close_row.Items.Add(
        forms.StackLayoutItem(close, forms.HorizontalAlignment.Right, False)
    )

    layout.AddRow(size_label)
    layout.AddRow(size_slider)
    layout.AddRow(thickness_label)
    layout.AddRow(thickness_slider)
    layout.AddRow(selected_only)
    layout.AddRow(highlight_selected)
    layout.Add(None)
    layout.Add(close_row, True)
    dialog.Content = layout
    dialog.ShowModal(Rhino.UI.RhinoEtoApp.MainWindow)
    return Rhino.Commands.Result.Success
