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

    public static string GetSettingsJson()
    {
      return ProjectPlugin.GetSettingsJson();
    }

    public static void SetSettingsJson(string json)
    {
      ProjectPlugin.SetSettingsJson(json);
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
