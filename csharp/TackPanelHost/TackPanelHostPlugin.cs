using Rhino.PlugIns;
using Rhino.UI;
using TackPanelHost.Panels;

namespace TackPanelHost;

[System.Runtime.InteropServices.Guid("D0C7DFB7-9C10-4CF5-9F47-99E786C6C3F0")]
public sealed class TackPanelHostPlugin : PlugIn
{
    private static readonly Guid TackPluginId = new("E59443D4-AB7B-4E21-8AA3-66A7CED1AE27");

    public TackPanelHostPlugin()
    {
        Instance = this;
    }

    public static TackPanelHostPlugin? Instance { get; private set; }

    public override PlugInLoadTime LoadTime => PlugInLoadTime.AtStartup;

    protected override LoadReturnCode OnLoad(ref string errorMessage)
    {
        Rhino.UI.Panels.RegisterPanel(
            this,
            typeof(TackPanel),
            "Tack",
            typeof(TackPanelHostPlugin).Assembly,
            "TackPanelHost.Resources.TackPanelIcon.ico",
            PanelType.PerDoc);

        return LoadReturnCode.Success;
    }

    internal static bool EnsureTackPythonPluginLoaded()
    {
        return PlugIn.LoadPlugIn(TackPluginId, false, true);
    }
}
