import System
import sys
import traceback

import Eto.Drawing as drawing
import Eto.Forms as forms
import Rhino
from Rhino.Commands import Result


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


def RunCommand(is_interactive):
    try:
        doc = Rhino.RhinoDoc.ActiveDoc
        if doc is None:
            return Result.Cancel

        panel = Rhino.UI.Panels.GetPanel(PANEL_ID, doc)
        if panel is None:
            Rhino.UI.Panels.OpenPanel(PANEL_ID)
            panel = Rhino.UI.Panels.GetPanel(PANEL_ID, doc)

        if panel is None:
            Rhino.RhinoApp.WriteLine(
                "TackPanelPython: panel instance was not available."
            )
            return Result.Failure

        panel.SetPythonContent(_build_panel_content(doc))
        Rhino.RhinoApp.WriteLine("TackPanelPython: Python content installed.")
        return Result.Success
    except Exception:
        Rhino.RhinoApp.WriteLine(
            "TackPanelPython failed:\n{}".format(traceback.format_exc())
        )
        return Result.Failure


if __name__ == "__main__":
    RunCommand(True)
