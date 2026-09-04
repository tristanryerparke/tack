using System;
using System.Collections.Generic;

using Rhino;
using Rhino.Commands;

namespace RhinoCodePlatform.Rhino3D.Projects.Plugin
{
  /// <summary>Private, per-document Tack relationship data for the plug-in archive.</summary>
  public static class TackDocumentData
  {
    const string EmptyLinksJson = "{\"version\":1,\"links\":{}}";
    static readonly Dictionary<uint, string> s_linksByDocument =
      new Dictionary<uint, string>();
    static readonly HashSet<uint> s_documentsWithData = new HashSet<uint>();

    public static bool HasDocumentData(uint documentSerialNumber)
    {
      lock (s_linksByDocument)
        return s_documentsWithData.Contains(documentSerialNumber);
    }

    public static string GetLinksJson(uint documentSerialNumber)
    {
      lock (s_linksByDocument)
        return s_linksByDocument.TryGetValue(documentSerialNumber, out var linksJson)
          ? linksJson
          : EmptyLinksJson;
    }

    public static bool SetLinksJson(uint documentSerialNumber, string linksJson)
    {
      var document = RhinoDoc.FromRuntimeSerialNumber(documentSerialNumber);
      return document != null && SetLinksJson(document, linksJson, true);
    }

    /// <summary>Imports legacy data without creating an undo record.</summary>
    public static bool ImportLinksJson(uint documentSerialNumber, string linksJson)
    {
      var document = RhinoDoc.FromRuntimeSerialNumber(documentSerialNumber);
      return document != null && SetLinksJson(document, linksJson, false);
    }

    internal static void LoadLinksJson(RhinoDoc document, string linksJson)
    {
      if (document == null)
        return;
      Set(document.RuntimeSerialNumber, linksJson);
    }

    internal static void RemoveDocument(RhinoDoc document)
    {
      if (document == null)
        return;
      lock (s_linksByDocument)
      {
        s_linksByDocument.Remove(document.RuntimeSerialNumber);
        s_documentsWithData.Remove(document.RuntimeSerialNumber);
      }
    }

    static bool SetLinksJson(RhinoDoc document, string linksJson, bool recordUndo)
    {
      if (document == null)
        return false;

      linksJson = string.IsNullOrWhiteSpace(linksJson) ? EmptyLinksJson : linksJson;
      var previous = GetLinksJson(document.RuntimeSerialNumber);
      if (previous == linksJson && HasDocumentData(document.RuntimeSerialNumber))
        return true;

      if (recordUndo)
        document.AddCustomUndoEvent("Tack links", RestoreLinks, previous);
      Set(document.RuntimeSerialNumber, linksJson);
      document.Modified = true;
      return true;
    }

    static void Set(uint documentSerialNumber, string linksJson)
    {
      lock (s_linksByDocument)
      {
        s_linksByDocument[documentSerialNumber] = linksJson;
        s_documentsWithData.Add(documentSerialNumber);
      }
    }

    static void RestoreLinks(object sender, CustomUndoEventArgs eventArgs)
    {
      var document = eventArgs.Document;
      if (document == null)
        return;

      var current = GetLinksJson(document.RuntimeSerialNumber);
      SetLinksJson(document, eventArgs.Tag as string, false);
      document.AddCustomUndoEvent(eventArgs.ActionDescription, RestoreLinks, current);
    }
  }
}
