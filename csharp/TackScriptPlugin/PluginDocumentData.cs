using System.Collections.Generic;

using Rhino;

namespace RhinoCodePlatform.Rhino3D.Projects.Plugin
{
  public static class PluginDocumentData
  {
    const string EmptyJson = "{}";
    static readonly Dictionary<uint, string> s_jsonByDocument =
      new Dictionary<uint, string>();

    public static string GetJson(uint documentSerialNumber)
    {
      lock (s_jsonByDocument)
      {
        return s_jsonByDocument.TryGetValue(documentSerialNumber, out var json)
          ? json
          : EmptyJson;
      }
    }

    public static bool SetJson(uint documentSerialNumber, string json)
    {
      var document = RhinoDoc.FromRuntimeSerialNumber(documentSerialNumber);
      if (document == null)
        return false;

      Set(document.RuntimeSerialNumber, Normalize(json));
      document.Modified = true;
      return true;
    }

    internal static void LoadJson(RhinoDoc document, string json)
    {
      if (document != null)
        Set(document.RuntimeSerialNumber, Normalize(json));
    }

    internal static void Remove(RhinoDoc document)
    {
      if (document == null)
        return;
      lock (s_jsonByDocument)
      {
        s_jsonByDocument.Remove(document.RuntimeSerialNumber);
      }
    }

    static string Normalize(string json)
    {
      return string.IsNullOrWhiteSpace(json) ? EmptyJson : json;
    }

    static void Set(uint documentSerialNumber, string json)
    {
      lock (s_jsonByDocument)
      {
        s_jsonByDocument[documentSerialNumber] = json;
      }
    }
  }
}
