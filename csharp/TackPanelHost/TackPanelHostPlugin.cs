using Rhino;
using Rhino.PlugIns;
using Rhino.UI;
using TackPanelHost.Panels;

namespace TackPanelHost;

[System.Runtime.InteropServices.Guid("D0C7DFB7-9C10-4CF5-9F47-99E786C6C3F0")]
public sealed class TackPanelHostPlugin : PlugIn
{
    private static bool _analyticPlaneRestoreScheduled;

    public TackPanelHostPlugin()
    {
        Instance = this;
    }

    public static TackPanelHostPlugin? Instance { get; private set; }

    public override PlugInLoadTime LoadTime => PlugInLoadTime.AtStartup;

    protected override LoadReturnCode OnLoad(ref string errorMessage)
    {
        RhinoApp.WriteLine("Tack host: loading and registering the dockable panel.");
        Rhino.UI.Panels.RegisterPanel(
            this,
            typeof(TackPanel),
            "Tack",
            typeof(TackPanelHostPlugin).Assembly,
            "TackPanelHost.Resources.TackPanelIcon.ico",
            PanelType.PerDoc);

        RhinoDoc.EndOpenDocument += OnEndOpenDocument;
        RhinoApp.WriteLine("Tack host: subscribed to EndOpenDocument.");
        ScheduleAnalyticPlaneRestore();
        return LoadReturnCode.Success;
    }

    protected override void OnShutdown()
    {
        RhinoDoc.EndOpenDocument -= OnEndOpenDocument;
        base.OnShutdown();
    }

    private static void OnEndOpenDocument(object? sender, DocumentOpenEventArgs eventArgs)
    {
        RhinoApp.WriteLine("Tack host: EndOpenDocument received.");
        ScheduleAnalyticPlaneRestore();
    }

    private static void ScheduleAnalyticPlaneRestore()
    {
        if (_analyticPlaneRestoreScheduled)
        {
            return;
        }

        _analyticPlaneRestoreScheduled = true;
        RhinoApp.WriteLine("Tack host: queued analytic-plane restoration.");
        Eto.Forms.Application.Instance.AsyncInvoke(() =>
        {
            _analyticPlaneRestoreScheduled = false;
            RhinoApp.WriteLine("Tack host: running queued analytic-plane restoration.");
            if (!PythonStartup.RestoreAnalyticPlaneLinks())
            {
                RhinoApp.WriteLine("Tack startup: analytic-plane restore script failed.");
            }
        });
    }
}
