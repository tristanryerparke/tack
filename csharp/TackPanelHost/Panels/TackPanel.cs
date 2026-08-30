using System;
using Eto.Forms;
using Rhino;
using Rhino.UI;

namespace TackPanelHost.Panels;

[System.Runtime.InteropServices.Guid("F793A6F1-E37C-4F3C-A39A-65D4F720E8D2")]
public sealed class TackPanel : Panel, IPanel
{
    private readonly uint _documentSerialNumber;
    private bool _bootstrapScheduled;
    private Control? _pythonContent;

    public TackPanel(uint documentSerialNumber)
    {
        _documentSerialNumber = documentSerialNumber;
        Title = "Tack";
        Content = new Label
        {
            Text = "Tack Python panel is not initialized.",
        };
    }

    public static Guid PanelId => typeof(TackPanel).GUID;

    public string Title { get; }

    public uint DocumentSerialNumber => _documentSerialNumber;

    public void SetPythonContent(Control content)
    {
        _pythonContent = content ?? throw new ArgumentNullException(nameof(content));
        Content = _pythonContent;
    }

    public void PanelShown(uint documentSerialNumber, ShowPanelReason reason)
    {
        SchedulePythonBootstrap();
    }

    public void PanelHidden(uint documentSerialNumber, ShowPanelReason reason)
    {
    }

    public void PanelClosing(uint documentSerialNumber, bool onCloseDocument)
    {
        _bootstrapScheduled = false;
        _pythonContent = null;
    }

    private void SchedulePythonBootstrap()
    {
        if (_pythonContent != null || _bootstrapScheduled)
        {
            return;
        }

        _bootstrapScheduled = true;
        Application.Instance.AsyncInvoke(() =>
        {
            if (_pythonContent != null)
            {
                return;
            }

            if (!PythonStartup.InitializePanel())
            {
                _bootstrapScheduled = false;
                RhinoApp.WriteLine("Tack panel: Python initialization script failed.");
            }
        });
    }
}
