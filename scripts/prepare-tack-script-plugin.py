"""Apply Tack's maintained C# extension to a generated Script Editor plugin."""

import shutil
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parent.parent
GENERATED_PROJECT = REPOSITORY_ROOT / "build" / "rh8" / "src" / "Tack"
EXTENSION_SOURCE = REPOSITORY_ROOT / "csharp" / "TackScriptPlugin"


def main():
    project_plugin = GENERATED_PROJECT / "ProjectPlugin.cs"
    source = project_plugin.read_text()
    source = source.replace(
        "public class ProjectPlugin : PlugIn",
        "public partial class ProjectPlugin : PlugIn",
    )
    if "public partial class ProjectPlugin : PlugIn" not in source:
        raise RuntimeError("Could not make generated ProjectPlugin partial.")
    project_plugin.write_text(source)

    project_data = GENERATED_PROJECT / "Plugin.Data.resources"
    if not project_data.is_file():
        raise RuntimeError("Generated project data resource is missing.")
    project_file = GENERATED_PROJECT / "Tack.csproj"
    project_source = project_file.read_text()
    resource_item = (
        "  <ItemGroup>\n"
        "    <EmbeddedResource Include=\"Plugin.Data.resources\" "
        "LogicalName=\"Plugin.Data.resources\" />\n"
        "  </ItemGroup>\n"
    )
    if "Plugin.Data.resources" not in project_source:
        project_source = project_source.replace(
            "</Project>",
            resource_item + "</Project>",
        )
        project_file.write_text(project_source)

    for extension in EXTENSION_SOURCE.glob("*.cs"): 
        shutil.copy2(extension, GENERATED_PROJECT / extension.name)


if __name__ == "__main__":
    main()
