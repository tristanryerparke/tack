using System;
using System.IO;
using System.Reflection;

using Rhino;
using Rhino.FileIO;
using Rhino.PlugIns;
using Rhino.UI;

namespace RhinoCodePlatform.Rhino3D.Projects.Plugin
{
  public partial class ProjectPlugin
  {
    static bool s_restoreScheduled;

    public override PlugInLoadTime LoadTime => PlugInLoadTime.AtStartup;

    public static bool DefaultDisplayEnabled
    {
      get => Instance == null || Instance.Settings.GetBool("DefaultDisplayEnabled", true);
    }

    public static void SaveDisplayPreference(string action)
    {
      if (Instance != null && (action == "show" || action == "hide"))
        Instance.Settings.SetBool("DefaultDisplayEnabled", action == "show");
    }

    public static double CrosshairSize
    {
      get => Instance == null || Instance.Settings == null
        ? 20.0
        : Instance.Settings.GetDouble("CrosshairSize", 20.0);
    }

    public static void SaveCrosshairSize(double size)
    {
      if (Instance != null && Instance.Settings != null)
        Instance.Settings.SetDouble("CrosshairSize", size);
    }

    public static double CrosshairThickness
    {
      get => Instance == null || Instance.Settings == null
        ? 2.0
        : Instance.Settings.GetDouble("CrosshairThickness", 2.0);
    }

    public static void SaveCrosshairThickness(double thickness)
    {
      if (Instance != null && Instance.Settings != null)
        Instance.Settings.SetDouble("CrosshairThickness", thickness);
    }

    protected override LoadReturnCode OnLoad(ref string errorMessage)
    {
      Panels.RegisterPanel(
        this,
        typeof(TackPanel),
        "Tack",
        typeof(ProjectPlugin).Assembly,
        "Tack.Resources.TackPanelIcon.ico",
        PanelType.PerDoc);
      RhinoDoc.EndOpenDocument += OnEndOpenDocument;
      RhinoDoc.CloseDocument += OnCloseDocument;
      ScheduleRestore();
      return LoadReturnCode.Success;
    }

    protected override void OnShutdown()
    {
      RhinoDoc.EndOpenDocument -= OnEndOpenDocument;
      RhinoDoc.CloseDocument -= OnCloseDocument;
      base.OnShutdown();
    }

    protected override bool ShouldCallWriteDocument(FileWriteOptions options)
    {
      return true;
    }

    protected override void WriteDocument(
      RhinoDoc document,
      BinaryArchiveWriter archive,
      FileWriteOptions options)
    {
      archive.WriteString(TackDocumentData.GetLinksJson(document.RuntimeSerialNumber));
    }

    protected override void ReadDocument(
      RhinoDoc document,
      BinaryArchiveReader archive,
      FileReadOptions options)
    {
      TackDocumentData.LoadLinksJson(document, archive.ReadString());
    }

    static void OnEndOpenDocument(object sender, DocumentOpenEventArgs eventArgs)
    {
      ScheduleRestore();
    }

    static void OnCloseDocument(object sender, DocumentEventArgs eventArgs)
    {
      TackDocumentData.RemoveDocument(eventArgs.Document);
    }

    static void ScheduleRestore()
    {
      if (s_restoreScheduled)
        return;

      s_restoreScheduled = true;
      Eto.Forms.Application.Instance.AsyncInvoke(() =>
      {
        s_restoreScheduled = false;
        Initialize();
        if (!RestoreOpenDocuments())
          RhinoApp.WriteLine("Tack: saved relationships could not be restored.");
      });
    }

    internal static bool InstallPythonPanel(uint documentSerialNumber)
    {
      Initialize();
      RhinoApp.WriteLine("Tack panel: starting Python content.");
      return RunPython(
        "from tack import panel\n"
        + "panel.install(" + documentSerialNumber + ")\n",
        "Tack panel initialization failed");
    }

    static bool RestoreOpenDocuments()
    {
      return RunPython(
        "from tack import actions\n"
        + "actions.restore_open_documents(default_display_enabled="
        + (DefaultDisplayEnabled ? "True" : "False") + ")\n",
        "Tack startup restore failed");
    }

    static bool RunPython(string body, string failurePrefix)
    {
      try
      {
        var source = "#! python 3\n"
          + "import sys\n"
          + "import Rhino\n"
          + "_tack_python_root = " + PythonString(PythonRoot()) + "\n"
          + "if _tack_python_root not in sys.path:\n"
          + "    sys.path.insert(0, _tack_python_root)\n"
          + "try:\n"
          + IndentPython(body)
          + "except Exception:\n"
          + "    import traceback\n"
          + "    Rhino.RhinoApp.WriteLine("
          + PythonString(failurePrefix + ":\\n")
          + " + traceback.format_exc())\n"
          + "    raise\n";
        var rhinoCode = Type.GetType(
          "Rhino.Runtime.Code.RhinoCode, Rhino.Runtime.Code");
        var runScript = rhinoCode?.GetMethod(
          "RunScript",
          BindingFlags.Public | BindingFlags.Static,
          null,
          new[] { typeof(string) },
          null);
        if (runScript == null)
          return false;

        runScript.Invoke(null, new object[] { source });
        return true;
      }
      catch (Exception exception)
      {
        while (exception.InnerException != null)
          exception = exception.InnerException;
        RhinoApp.WriteLine(failurePrefix + ": " + exception.Message);
        return false;
      }
    }

    static string IndentPython(string source)
    {
      return "    " + source.TrimEnd('\n').Replace("\n", "\n    ") + "\n";
    }

    static string PythonRoot()
    {
      return Path.Combine(
        Path.GetDirectoryName(Assembly.GetExecutingAssembly().Location),
        "Python");
    }

    static string PythonString(string value)
    {
      return "\"" + value.Replace("\\", "\\\\").Replace("\"", "\\\"") + "\"";
    }
  }
}
