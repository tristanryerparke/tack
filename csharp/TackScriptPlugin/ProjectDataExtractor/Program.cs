using System;
using System.IO;
using System.Reflection;

var assembly = Assembly.LoadFile(Path.GetFullPath(args[0]));
using var input = assembly.GetManifestResourceStream("Plugin.Data.resources")
    ?? throw new InvalidOperationException("Generated plugin has no project data resource.");
using var output = File.Create(args[1]);
input.CopyTo(output);
