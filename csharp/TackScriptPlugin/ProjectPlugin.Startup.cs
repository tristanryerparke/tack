using System;
using System.IO;
using System.Reflection;

using Eto.Forms;

using Rhino;
using Rhino.FileIO;
using Rhino.PlugIns;
using Rhino.UI;

namespace RhinoCodePlatform.Rhino3D.Projects.Plugin
{
  public partial class ProjectPlugin
  {
    const string DevelopmentRootFile = "development-python-root.txt";
    static readonly Guid RhinoCodePluginId =
      new Guid("c9cba87a-23ce-4f15-a918-97645c05cde7");
    static bool s_restoreScheduled;

    public override PlugInLoadTime LoadTime => PlugInLoadTime.AtStartup;

    public static bool IsDevelopmentMode =>
      File.Exists(Path.Combine(PluginDirectory(), DevelopmentRootFile));

    public static string PythonRoot => ResolvePythonRoot();

    public static string GetDocumentDataJson(uint documentSerialNumber)
    {
      return PluginDocumentData.GetJson(documentSerialNumber);
    }

    public static bool SetDocumentDataJson(
      uint documentSerialNumber,
      string json)
    {
      return PluginDocumentData.SetJson(documentSerialNumber, json);
    }

    public static bool DefaultDisplayEnabled
    {
      get => Instance == null || Instance.Settings.GetBool("DefaultDisplayEnabled", true);
    }

    public static void SaveDisplayPreference(string action)
    {
      if (Instance != null && (action == "show" || action == "hide"))
        Instance.Settings.SetBool("DefaultDisplayEnabled", action == "show");
    }

    public static bool ShowSelectedTacksOnly
    {
      get => Instance != null
        && Instance.Settings != null
        && Instance.Settings.GetBool("ShowSelectedTacksOnly", false);
    }

    public static void SaveShowSelectedTacksOnly(bool enabled)
    {
      if (Instance != null && Instance.Settings != null)
        Instance.Settings.SetBool("ShowSelectedTacksOnly", enabled);
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
      archive.WriteString(PluginDocumentData.GetJson(document.RuntimeSerialNumber));
    }

    protected override void ReadDocument(
      RhinoDoc document,
      BinaryArchiveReader archive,
      FileReadOptions options)
    {
      PluginDocumentData.LoadJson(document, archive.ReadString());
    }

    internal static bool InstallPythonPanel(uint documentSerialNumber)
    {
      return RunPython(
        "from tack import panel\n"
        + "panel.install(" + documentSerialNumber + ")\n",
        "Tack panel initialization failed");
    }

    internal static void SchedulePanelRefresh(uint documentSerialNumber)
    {
      Application.Instance.AsyncInvoke(() => RunPython(
        "from tack import panel\n"
        + "import Rhino\n"
        + "_document = Rhino.RhinoDoc.FromRuntimeSerialNumber("
        + documentSerialNumber + ")\n"
        + "if _document is not None:\n"
        + "    panel.refresh(_document)\n",
        "Tack panel refresh failed"));
    }

    static void OnEndOpenDocument(object sender, DocumentOpenEventArgs eventArgs)
    {
      ScheduleRestore();
    }

    static void OnCloseDocument(object sender, DocumentEventArgs eventArgs)
    {
      PluginDocumentData.Remove(eventArgs.Document);
    }

    static void ScheduleRestore()
    {
      if (s_restoreScheduled)
        return;

      s_restoreScheduled = true;
      Application.Instance.AsyncInvoke(() =>
      {
        s_restoreScheduled = false;
        if (!RestoreOpenDocuments())
          RhinoApp.WriteLine("Tack: saved relationships could not be restored.");
      });
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
        var scripting = RhinoApp.GetPlugInObject(RhinoCodePluginId);
        var createPython = scripting?.GetType().GetMethod(
          "CreatePython3Script",
          BindingFlags.Public | BindingFlags.Instance,
          null,
          Type.EmptyTypes,
          null);
        var python = createPython?.Invoke(scripting, null)
          as Rhino.Runtime.PythonScript;
        if (python == null)
          throw new InvalidOperationException(
            "Rhino's Python 3 service could not be loaded.");

        var source = "#! python 3\n"
          + "import sys\n"
          + "import Rhino\n"
          + "_tack_python_root = " + PythonString(PythonRoot) + "\n"
          + "if _tack_python_root in sys.path:\n"
          + "    sys.path.remove(_tack_python_root)\n"
          + "sys.path.insert(0, _tack_python_root)\n"
          + "try:\n"
          + IndentPython(body)
          + "except Exception:\n"
          + "    import traceback\n"
          + "    Rhino.RhinoApp.WriteLine("
          + PythonString(failurePrefix + ":\\n")
          + " + traceback.format_exc())\n"
          + "    raise\n";
        return python.ExecuteScript(source);
      }
      catch (Exception exception)
      {
        while (exception.InnerException != null)
          exception = exception.InnerException;
        RhinoApp.WriteLine(failurePrefix + ": " + exception.Message);
        return false;
      }
    }

    static string ResolvePythonRoot()
    {
      var marker = Path.Combine(PluginDirectory(), DevelopmentRootFile);
      if (File.Exists(marker))
      {
        var developmentRoot = File.ReadAllText(marker).Trim();
        if (Directory.Exists(developmentRoot))
          return developmentRoot;
        RhinoApp.WriteLine(
          "Tack: development Python root is missing: " + developmentRoot);
      }
      return Path.Combine(PluginDirectory(), "Python");
    }

    static string PluginDirectory()
    {
      return Path.GetDirectoryName(Assembly.GetExecutingAssembly().Location);
    }

    static string IndentPython(string source)
    {
      return "    " + source.TrimEnd('\n').Replace("\n", "\n    ") + "\n";
    }

    static string PythonString(string value)
    {
      return "\"" + value.Replace("\\", "\\\\").Replace("\"", "\\\"") + "\"";
    }
  }
}
