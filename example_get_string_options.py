import Rhino
import rhinoscriptsyntax as rs


def get_anchor_type():
    """Prompt for a choice using Rhino's command-line options."""
    return rs.GetString(
        "Choose an anchor type",
        "BoundingBox",
        ("BoundingBox", "Vertex", "Face"),
    )


def main():
    choice = get_anchor_type()
    if choice is None:
        print("Selection cancelled.")
        return Rhino.Commands.Result.Cancel

    print("Selected anchor type: {}".format(choice))
    return Rhino.Commands.Result.Success


if __name__ == "__main__":
    main()
