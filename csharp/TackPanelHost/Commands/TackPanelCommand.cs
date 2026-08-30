using Rhino;
using Rhino.Commands;
using Rhino.UI;
using TackPanelHost.Panels;

namespace TackPanelHost.Commands;

[System.Runtime.InteropServices.Guid("A2E76F70-11DF-4A4C-B7F5-4C6B43891E6B")]
public sealed class TackPanelCommand : Command
{
    public override string EnglishName => "TackPanel";

    protected override Result RunCommand(RhinoDoc doc, RunMode mode)
    {
        Rhino.UI.Panels.OpenPanel(TackPanel.PanelId);
        return Result.Success;
    }
}
