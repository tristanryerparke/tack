using System;
using System.IO;
using System.Reflection;

using Rhino;
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

    protected override LoadReturnCode OnLoad(ref string errorMessage)
    {
      Panels.RegisterPanel(
        this,
        typeof(TackPanel),
        "Tack",
        typeof(ProjectPlugin).Assembly,
        "Tack.Resources.projectIcon.ico",
        PanelType.PerDoc);
      RhinoDoc.EndOpenDocument += OnEndOpenDocument;
      ScheduleRestore();
      return LoadReturnCode.Success;
    }

    protected override void OnShutdown()
    {
      RhinoDoc.EndOpenDocument -= OnEndOpenDocument;
      base.OnShutdown();
    }

    static void OnEndOpenDocument(object sender, DocumentOpenEventArgs eventArgs)
    {
      ScheduleRestore();
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

    static bool RestoreOpenDocuments()
    {
      try
      {
        var pythonRoot = Path.Combine(
          Path.GetDirectoryName(Assembly.GetExecutingAssembly().Location),
          "Python");
        var source = "#! python 3\n"
          + "import sys\n"
          + "_tack_python_root = " + PythonString(pythonRoot) + "\n"
          + "if _tack_python_root not in sys.path:\n"
          + "    sys.path.insert(0, _tack_python_root)\n"
          + "from tack import actions\n"
          + "actions.restore_open_documents(default_display_enabled="
          + (DefaultDisplayEnabled ? "True" : "False") + ")\n";
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
        RhinoApp.WriteLine("Tack startup restore failed: " + exception.Message);
        return false;
      }
    }

    static string PythonString(string value)
    {
      return "\"" + value.Replace("\\", "\\\\").Replace("\"", "\\\"") + "\"";
    }
  }
}
