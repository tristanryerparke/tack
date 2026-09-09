using System;

using Eto.Forms;

using Rhino;
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
  }
}
