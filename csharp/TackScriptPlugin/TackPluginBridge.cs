using RhinoCodePlatform.Rhino3D.Projects.Plugin;

namespace TackRhinoPlugin
{
  /// <summary>
  /// Unique Python-visible name for Tack's generated plug-in services.
  /// </summary>
  public static class PluginBridge
  {
    public static bool IsDevelopmentMode => ProjectPlugin.IsDevelopmentMode;

    public static string PythonRoot => ProjectPlugin.PythonRoot;

    public static bool DefaultDisplayEnabled => ProjectPlugin.DefaultDisplayEnabled;

    public static void SaveDisplayPreference(string action)
    {
      ProjectPlugin.SaveDisplayPreference(action);
    }

    public static bool ShowSelectedTacksOnly => ProjectPlugin.ShowSelectedTacksOnly;

    public static void SaveShowSelectedTacksOnly(bool enabled)
    {
      ProjectPlugin.SaveShowSelectedTacksOnly(enabled);
    }

    public static double CrosshairSize => ProjectPlugin.CrosshairSize;

    public static void SaveCrosshairSize(double size)
    {
      ProjectPlugin.SaveCrosshairSize(size);
    }

    public static double CrosshairThickness => ProjectPlugin.CrosshairThickness;

    public static void SaveCrosshairThickness(double thickness)
    {
      ProjectPlugin.SaveCrosshairThickness(thickness);
    }

    public static string GetDocumentDataJson(uint documentSerialNumber)
    {
      return ProjectPlugin.GetDocumentDataJson(documentSerialNumber);
    }

    public static bool SetDocumentDataJson(
      uint documentSerialNumber,
      string json)
    {
      return ProjectPlugin.SetDocumentDataJson(documentSerialNumber, json);
    }

    public static TackPanel GetPanelInstance(string panelInstanceId)
    {
      return TackPanel.GetInstance(panelInstanceId);
    }

    public static string[] GetPanelInstanceIds(uint documentSerialNumber)
    {
      return TackPanel.GetInstanceIds(documentSerialNumber);
    }
  }
}
