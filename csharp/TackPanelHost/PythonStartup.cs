using System.Reflection;
using Rhino;
using Rhino.PlugIns;

namespace TackPanelHost;

internal static class PythonStartup
{
    private static readonly Guid TackPluginId = new(
        "E59443D4-AB7B-4E21-8AA3-66A7CED1AE27");
    private const string PythonLanguageId = "mcneel.pythonnet.python";
    private static object? _pythonLanguage;

    internal static bool InitializePanel()
    {
        return ExecuteFile("initialize_panel.py");
    }

    internal static bool RestoreAnalyticPlaneLinks()
    {
        return ExecuteFile("restore_analytic_plane_links.py");
    }

    private static bool ExecuteFile(string scriptName)
    {
        var scriptPath = Path.Combine(
            Path.GetDirectoryName(Assembly.GetExecutingAssembly().Location)!,
            "Python",
            scriptName);
        if (!File.Exists(scriptPath))
        {
            RhinoApp.WriteLine($"Tack Python 3: script was not found at {scriptPath}.");
            return false;
        }

        try
        {
            var language = GetPythonLanguage();
            if (language == null)
            {
                RhinoApp.WriteLine(
                    $"Tack Python 3: language {PythonLanguageId} is unavailable.");
                return false;
            }

            var runtimeAssembly = AppDomain.CurrentDomain.GetAssemblies()
                .First(assembly =>
                    assembly.GetName().Name == "Rhino.Runtime.Code");
            var languageType = runtimeAssembly.GetType(
                "Rhino.Runtime.Code.Languages.ILanguage",
                throwOnError: true)!;
            var codeType = runtimeAssembly.GetType(
                "Rhino.Runtime.Code.Code",
                throwOnError: true)!;
            var createCode = languageType.GetMethod(
                "CreateCode",
                new[] { typeof(Uri) })!;
            var code = createCode.Invoke(
                language,
                new object[] { new Uri(scriptPath) });
            if (code == null)
            {
                RhinoApp.WriteLine(
                    $"Tack Python 3: could not create code for {scriptPath}.");
                return false;
            }

            RhinoApp.WriteLine($"Tack Python 3: executing {scriptPath}.");
            codeType.GetMethod("Run", Type.EmptyTypes)!.Invoke(code, null);
            RhinoApp.WriteLine($"Tack Python 3: completed {scriptName}.");
            return true;
        }
        catch (Exception exception)
        {
            RhinoApp.WriteLine(
                $"Tack Python 3: {scriptName} failed: {Innermost(exception)}");
            return false;
        }
    }

    private static object? GetPythonLanguage()
    {
        if (_pythonLanguage != null)
        {
            return _pythonLanguage;
        }

        if (!PlugIn.LoadPlugIn(TackPluginId, false, true))
        {
            RhinoApp.WriteLine("Tack Python 3: could not load the Tack Python plugin.");
            return null;
        }

        var projectAssembly = AppDomain.CurrentDomain.GetAssemblies()
            .FirstOrDefault(assembly => assembly.GetName().Name == "Tack");
        var projectPluginType = projectAssembly?.GetType(
            "RhinoCodePlatform.Rhino3D.Projects.Plugin.ProjectPlugin");
        var initialize = projectPluginType?.GetMethod(
            "Initialize",
            BindingFlags.Public | BindingFlags.Static);
        if (initialize == null)
        {
            RhinoApp.WriteLine("Tack Python 3: project initializer was not found.");
            return null;
        }

        RhinoApp.WriteLine("Tack Python 3: initializing the RhinoCode project.");
        initialize.Invoke(null, null);

        var runtimeAssembly = AppDomain.CurrentDomain.GetAssemblies()
            .FirstOrDefault(
                assembly => assembly.GetName().Name == "Rhino.Runtime.Code");
        var rhinoCodeType = runtimeAssembly?.GetType(
            "Rhino.Runtime.Code.RhinoCode");
        var languageSpecType = runtimeAssembly?.GetType(
            "Rhino.Runtime.Code.Languages.LanguageSpec");
        if (rhinoCodeType == null || languageSpecType == null)
        {
            RhinoApp.WriteLine("Tack Python 3: RhinoCode runtime types were not found.");
            return null;
        }

        var languages = rhinoCodeType.GetProperty(
            "Languages",
            BindingFlags.Public | BindingFlags.Static)!.GetValue(null);
        var languageSpec = Activator.CreateInstance(
            languageSpecType,
            new object[] { PythonLanguageId });
        _pythonLanguage = languages?.GetType().GetMethod(
            "QueryLatest",
            new[] { languageSpecType })?.Invoke(
                languages,
                new[] { languageSpec });

        return _pythonLanguage;
    }

    private static Exception Innermost(Exception exception)
    {
        while (exception.InnerException != null)
        {
            exception = exception.InnerException;
        }
        return exception;
    }
}
