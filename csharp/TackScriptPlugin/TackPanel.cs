using System;

using Eto.Drawing;
using Eto.Forms;

using Rhino;
using Rhino.Commands;
using Rhino.UI;

namespace RhinoCodePlatform.Rhino3D.Projects.Plugin
{
  [System.Runtime.InteropServices.Guid("F793A6F1-E37C-4F3C-A39A-65D4F720E8D2")]
  public sealed class TackPanel : Panel, IPanel
  {
    public TackPanel(uint documentSerialNumber)
    {
      Title = "Tack";
      Content = BuildContent();
    }

    public static Guid PanelId => typeof(TackPanel).GUID;

    public string Title { get; private set; }

    public void PanelShown(uint documentSerialNumber, ShowPanelReason reason) { }
    public void PanelHidden(uint documentSerialNumber, ShowPanelReason reason) { }
    public void PanelClosing(uint documentSerialNumber, bool onCloseDocument) { }

    Control BuildContent()
    {
      var buttons = new StackLayout
      {
        Orientation = Orientation.Horizontal,
        Spacing = 6,
        Items =
        {
          ActionButton("Add Tack", ProjectCommand_19f84da7.Instance, "19f84da7-2ccd-4827-b61b-60faad1186aa"),
          ActionButton("Show", ProjectCommand_5d9721b6.Instance, "5d9721b6-fbac-42b1-8159-bd5d4fb1b724"),
          ActionButton("Hide", ProjectCommand_e243b98c.Instance, "e243b98c-ba38-41ba-8461-5765b437964e"),
          ActionButton("Clear", ProjectCommand_e3e23181.Instance, "e3e23181-99dc-4872-9488-b2b59d06c07e"),
        },
      };
      var layout = new DynamicLayout
      {
        Padding = new Padding(10),
        DefaultSpacing = new Size(6, 6),
      };
      layout.AddRow(buttons);
      layout.AddRow(null);
      return layout;
    }

    static Button ActionButton(
      string text,
      Rhino.Commands.Command command,
      string commandId)
    {
      var button = new Button { Text = text };
      button.Click += (_, __) =>
      {
        var doc = RhinoDoc.ActiveDoc;
        if (doc == null || command == null)
          return;
        ProjectPlugin.Initialize();
        ProjectPlugin.RunCode(
          command,
          new Guid(commandId),
          doc,
          RunMode.Interactive);
      };
      return button;
    }
  }
}
