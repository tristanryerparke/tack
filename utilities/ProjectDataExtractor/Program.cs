using System;
using System.IO;
using System.Reflection;

using var input = Assembly.LoadFile(Path.GetFullPath(args[0]))
  .GetManifestResourceStream("Plugin.Data.resources")
  ?? throw new InvalidOperationException("Generated plug-in has no project data resource.");
using var output = File.Create(args[1]);
input.CopyTo(output);
