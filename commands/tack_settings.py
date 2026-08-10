import traceback

import Eto.Drawing as drawing
import Eto.Forms as forms
import Rhino
from Rhino.Commands import Result

from tack import utils


class _SettingsDialog(forms.Dialog[bool]):
    def __init__(self):
        super(_SettingsDialog, self).__init__()
        self.Title = "Tack Settings"
        self.Resizable = False
        self.Padding = drawing.Padding(8)
        self.ClientSize = drawing.Size(350, 115)
        self.accepted = False

        self.advanced = forms.CheckBox()
        self.advanced.Text = "Advanced reconciliation"
        self.advanced.Checked = bool(utils.ADVANCED_RECONCILIATION)

        self.debug = forms.CheckBox()
        self.debug.Text = "Debug output"
        self.debug.Checked = bool(utils.DEBUG)

        self.allow_child_movement = forms.CheckBox()
        self.allow_child_movement.Text = (
            "Allow child movement (update Tack offset)"
        )
        self.allow_child_movement.Checked = bool(
            utils.ALLOW_CHILD_MOVEMENT
        )

        ok = forms.Button()
        ok.Text = "OK"
        ok.Size = drawing.Size(80, 24)
        ok.MinimumSize = drawing.Size(80, 24)
        ok.MaximumSize = drawing.Size(80, 24)
        ok.Click += self._accept

        cancel = forms.Button()
        cancel.Text = "Cancel"
        cancel.Size = drawing.Size(80, 24)
        cancel.MinimumSize = drawing.Size(80, 24)
        cancel.MaximumSize = drawing.Size(80, 24)
        cancel.Click += self._cancel

        def row(*cells):
            result = forms.TableRow()
            for cell in cells:
                result.Cells.Add(cell)
            return result

        layout = forms.TableLayout()
        layout.Padding = drawing.Padding(0)
        layout.Spacing = drawing.Size(6, 6)
        layout.Rows.Add(
            row(forms.TableCell(self.advanced, True))
        )
        layout.Rows.Add(
            row(forms.TableCell(self.debug, True))
        )
        layout.Rows.Add(
            row(forms.TableCell(self.allow_child_movement, True))
        )

        spacer = forms.TableRow()
        spacer.ScaleHeight = True
        spacer.Cells.Add(forms.TableCell(forms.Panel(), True))
        layout.Rows.Add(spacer)

        layout.Rows.Add(
            row(
                forms.TableCell(forms.Panel(), True),
                forms.TableCell(cancel),
                forms.TableCell(ok),
            )
        )
        self.Content = layout

    def _accept(self, sender, event):
        utils.set_setting("advanced_reconciliation", bool(self.advanced.Checked))
        utils.set_setting("debug", bool(self.debug.Checked))
        utils.set_setting(
            "allow_child_movement",
            bool(self.allow_child_movement.Checked),
        )
        self.accepted = True
        self.Close()

    def _cancel(self, sender, event):
        self.Close()


def RunCommand(is_interactive):
    doc = Rhino.RhinoDoc.ActiveDoc
    if doc is None:
        return Result.Cancel

    dialog = _SettingsDialog()
    dialog.ShowModal(Rhino.UI.RhinoEtoApp.MainWindow)
    if not dialog.accepted:
        return Result.Cancel
    doc.Views.Redraw()
    print(
        "Tack settings updated: advanced_reconciliation={} debug={}".format(
            utils.ADVANCED_RECONCILIATION,
            utils.DEBUG,
        )
    )
    return Result.Success


if __name__ == "__main__":
    if not utils.DEBUG:
        RunCommand(True)
    else:
        try:
            from rhino_watcher import try_send_end_sync
            from rhino_watcher import try_send_quit_sync
            from rhino_watcher import websocket_output_if_available_sync
        except ImportError:
            RunCommand(True)
        else:
            try:
                with websocket_output_if_available_sync():
                    result = RunCommand(True)
            except Exception:
                with websocket_output_if_available_sync():
                    traceback.print_exc()
                try_send_quit_sync()
            else:
                if result == Result.Success:
                    try_send_end_sync()
                else:
                    try_send_quit_sync()
