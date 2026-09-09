using System;
using System.Collections.Generic;

using Rhino;
using Rhino.Commands;

namespace RhinoCodePlatform.Rhino3D.Projects.Plugin
{
  public static class PluginDocumentData
  {
    const string EmptyJson = "{}";
    static readonly Dictionary<uint, string> s_jsonByDocument =
      new Dictionary<uint, string>();
    static readonly HashSet<uint> s_documentsWithData = new HashSet<uint>();

    public static bool HasData(uint documentSerialNumber)
    {
      lock (s_jsonByDocument)
        return s_documentsWithData.Contains(documentSerialNumber);
    }

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
      return document != null && SetJson(document, json, recordUndo: true);
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
        s_documentsWithData.Remove(document.RuntimeSerialNumber);
      }
    }

    static bool SetJson(RhinoDoc document, string json, bool recordUndo)
    {
      json = Normalize(json);
      var previous = GetJson(document.RuntimeSerialNumber);
      if (previous == json && HasData(document.RuntimeSerialNumber))
        return true;

      if (recordUndo)
        document.AddCustomUndoEvent("Tack document data", RestoreJson, previous);
      Set(document.RuntimeSerialNumber, json);
      document.Modified = true;
      return true;
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
        s_documentsWithData.Add(documentSerialNumber);
      }
    }

    static void RestoreJson(object sender, CustomUndoEventArgs eventArgs)
    {
      var document = eventArgs.Document;
      if (document == null)
        return;

      var current = GetJson(document.RuntimeSerialNumber);
      SetJson(document, eventArgs.Tag as string, recordUndo: false);
      document.AddCustomUndoEvent(
        eventArgs.ActionDescription,
        RestoreJson,
        current);
      ProjectPlugin.SchedulePanelRefresh(document.RuntimeSerialNumber);
    }
  }
}
