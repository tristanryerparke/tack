using System;

using Eto.Forms;

using Rhino;
using Rhino.Commands;
using Rhino.UI;

namespace RhinoCodePlatform.Rhino3D.Projects.Plugin
{
  [System.Runtime.InteropServices.Guid("F793A6F1-E37C-4F3C-A39A-65D4F720E8D2")]
  public sealed class TackPanel : Panel, IPanel
  {
    readonly uint m_documentSerialNumber;
    bool m_bootstrapScheduled;
    Control m_pythonContent;

    public TackPanel(uint documentSerialNumber)
    {
      m_documentSerialNumber = documentSerialNumber;
      Title = "Tack";
      Content = new Label { Text = "Initializing Tack panel..." };
      SchedulePythonBootstrap();
    }

    public static Guid PanelId => typeof(TackPanel).GUID;

    public string Title { get; private set; }

    public void SetPythonContent(Control content)
    {
      m_pythonContent = content ?? throw new ArgumentNullException(nameof(content));
      Content = m_pythonContent;
    }

    public Result RunTackCommand(string action)
    {
      var doc = RhinoDoc.FromRuntimeSerialNumber(m_documentSerialNumber);
      if (doc == null)
        return Result.Cancel;

      if (action == "add")
        return RunProjectCommand(
          ProjectCommand_19f84da7.Instance,
          "19f84da7-2ccd-4827-b61b-60faad1186aa",
          doc);
      if (action == "show")
        return RunProjectCommand(
          ProjectCommand_5d9721b6.Instance,
          "5d9721b6-fbac-42b1-8159-bd5d4fb1b724",
          doc);
      if (action == "hide")
        return RunProjectCommand(
          ProjectCommand_e243b98c.Instance,
          "e243b98c-ba38-41ba-8461-5765b437964e",
          doc);
      if (action == "clear")
        return RunProjectCommand(
          ProjectCommand_e3e23181.Instance,
          "e3e23181-99dc-4872-9488-b2b59d06c07e",
          doc);
      return Result.Cancel;
    }

    public void PanelShown(uint documentSerialNumber, ShowPanelReason reason)
    {
      SchedulePythonBootstrap();
    }

    public void PanelHidden(uint documentSerialNumber, ShowPanelReason reason) { }

    public void PanelClosing(uint documentSerialNumber, bool onCloseDocument)
    {
      m_pythonContent = null;
    }

    void SchedulePythonBootstrap()
    {
      if (m_pythonContent != null || m_bootstrapScheduled)
        return;

      m_bootstrapScheduled = true;
      Application.Instance.AsyncInvoke(() =>
      {
        m_bootstrapScheduled = false;
        if (!ProjectPlugin.InstallPythonPanel(m_documentSerialNumber))
          RhinoApp.WriteLine("Tack panel: Python initialization failed.");
      });
    }

    static Result RunProjectCommand(
      Rhino.Commands.Command command,
      string commandId,
      RhinoDoc doc)
    {
      if (command == null)
        return Result.Cancel;
      ProjectPlugin.Initialize();
      return ProjectPlugin.RunCode(
        command,
        new Guid(commandId),
        doc,
        RunMode.Interactive);
    }
  }
}
