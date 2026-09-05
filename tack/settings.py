"""Tack's per-user display settings dialog."""

import Eto.Drawing as drawing
import Eto.Forms as forms
import Rhino

from tack import analytic_plane
from tack import plane_link


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
    dialog.ClientSize = drawing.Size(280, 180)
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
        plane_link.crosshair_size(doc),
        lambda size: plane_link.set_crosshair_size(doc, size),
    )
    thickness_label, thickness_slider = _slider(
        dialog,
        "Crosshair line width",
        analytic_plane.CROSSHAIR_THICKNESS_MIN,
        analytic_plane.CROSSHAIR_THICKNESS_MAX,
        plane_link.crosshair_thickness(doc),
        lambda thickness: plane_link.set_crosshair_thickness(doc, thickness),
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
    layout.Add(None)
    layout.Add(close_row, True)
    dialog.Content = layout
    dialog.ShowModal(Rhino.UI.RhinoEtoApp.MainWindow)
    return Rhino.Commands.Result.Success
