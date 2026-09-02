"""Python-owned Eto content for Tack's per-document dockable panel."""

import System

import Eto.Drawing as drawing
import Eto.Forms as forms
import Rhino


PANEL_ID = System.Guid("F793A6F1-E37C-4F3C-A39A-65D4F720E8D2")


def _action_button(panel, status, label, action):
    button = forms.Button()
    button.Text = label

    def run_action(sender, event):
        status.Text = "Running {}...".format(label)
        result = panel.RunTackCommand(action)
        status.Text = "{}: {}".format(label, result)

    button.Click += run_action
    return button


def _content(panel, doc):
    status = forms.Label()
    status.Text = "Ready"
    layout = forms.DynamicLayout()
    layout.Padding = drawing.Padding(10)
    layout.DefaultSpacing = drawing.Size(6, 6)
    layout.AddRow(_action_button(panel, status, "Add Tack", "add"))
    layout.AddRow(_action_button(panel, status, "Show", "show"))
    layout.AddRow(_action_button(panel, status, "Hide", "hide"))
    layout.AddRow(_action_button(panel, status, "Clear", "clear"))
    layout.AddRow(status)
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
