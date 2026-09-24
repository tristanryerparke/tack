using System;
using System.Collections.Generic;

using Eto.Forms;

using Rhino;
using Rhino.UI;

namespace RhinoCodePlatform.Rhino3D.Projects.Plugin
{
  [System.Runtime.InteropServices.Guid("F793A6F1-E37C-4F3C-A39A-65D4F720E8D2")]
  public sealed class TackPanel : Panel, IPanel
  {
    static readonly Dictionary<Guid, TackPanel> s_instances =
      new Dictionary<Guid, TackPanel>();

    readonly uint m_documentSerialNumber;
    readonly Guid m_instanceId = Guid.NewGuid();
    bool m_bootstrapScheduled;
    Control m_pythonContent;

    public TackPanel(uint documentSerialNumber)
    {
      m_documentSerialNumber = documentSerialNumber;
      lock (s_instances)
        s_instances[m_instanceId] = this;
      Title = "Tack";
      Content = new Label { Text = "Initializing Tack panel..." };
      SchedulePythonBootstrap();
    }

    public static Guid PanelId => typeof(TackPanel).GUID;

    public static TackPanel GetInstance(string instanceId)
    {
      Guid parsedId;
      if (!Guid.TryParse(instanceId, out parsedId))
        return null;
      lock (s_instances)
      {
        TackPanel panel;
        return s_instances.TryGetValue(parsedId, out panel) ? panel : null;
      }
    }

    public static string[] GetInstanceIds(uint documentSerialNumber)
    {
      lock (s_instances)
      {
        var ids = new List<string>();
        foreach (var pair in s_instances)
          if (pair.Value.m_documentSerialNumber == documentSerialNumber)
            ids.Add(pair.Key.ToString());
        return ids.ToArray();
      }
    }

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
      lock (s_instances)
      {
        if (s_instances.ContainsKey(m_instanceId)
          && ReferenceEquals(s_instances[m_instanceId], this))
          s_instances.Remove(m_instanceId);
      }
    }

    void SchedulePythonBootstrap()
    {
      if (m_pythonContent != null || m_bootstrapScheduled)
        return;

      m_bootstrapScheduled = true;
      Application.Instance.AsyncInvoke(() =>
      {
        m_bootstrapScheduled = false;
        if (!ProjectPlugin.InstallPythonPanel(
          m_documentSerialNumber,
          m_instanceId.ToString()))
          RhinoApp.WriteLine("Tack panel: Python initialization failed.");
      });
    }
  }
}
