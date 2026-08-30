import System
import os
import sys
import traceback

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import Eto.Drawing as drawing
import Eto.Forms as forms
import Rhino


PANEL_ID = System.Guid("F793A6F1-E37C-4F3C-A39A-65D4F720E8D2")


def _build_panel_content(doc):
    status = forms.Label()
    status.Text = "Python content is running inside the C# registered panel."

    document_label = forms.Label()
    document_label.Text = "Document serial number: {}".format(
        doc.RuntimeSerialNumber
    )

    python_version_button = forms.Button()
    python_version_button.Text = "Print Python Version"

    def print_python_version(sender, event):
        Rhino.RhinoApp.WriteLine(sys.version)

    python_version_button.Click += print_python_version

    layout = forms.DynamicLayout()
    layout.Padding = drawing.Padding(10)
    layout.DefaultSpacing = drawing.Size(6, 6)
    layout.AddRow(status)
    layout.AddRow(document_label)
    layout.AddRow(python_version_button)
    layout.AddRow(None)
    return layout


def initialize_panel():
    doc = Rhino.RhinoDoc.ActiveDoc
    if doc is None:
        raise RuntimeError("Tack panel requires an active Rhino document.")

    panel = Rhino.UI.Panels.GetPanel(PANEL_ID, doc)
    if panel is None:
        Rhino.UI.Panels.OpenPanel(PANEL_ID)
        panel = Rhino.UI.Panels.GetPanel(PANEL_ID, doc)

    if panel is None:
        raise RuntimeError("The C# Tack panel instance was not available.")

    panel.SetPythonContent(_build_panel_content(doc))
    Rhino.RhinoApp.WriteLine("Tack panel: Python content installed.")


try:
    initialize_panel()
except Exception:
    Rhino.RhinoApp.WriteLine(
        "Tack panel initialization failed:\n{}".format(traceback.format_exc())
    )
    raise
