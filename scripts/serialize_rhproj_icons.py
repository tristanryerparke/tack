import base64
import json
from pathlib import Path
from xml.etree import ElementTree


REPO_ROOT = Path(__file__).resolve().parent.parent
PROJECT_PATH = REPO_ROOT / "tack.rhproj"
ASSETS_PATH = REPO_ROOT / "assets"


def main():
    project = json.loads(PROJECT_PATH.read_text(encoding="utf-8"))
    serialized_icons = []

    for code in project["codes"]:
        command_path = Path(code["uri"])
        icon_path = ASSETS_PATH / f"{command_path.stem}.svg"
        if not icon_path.is_file():
            raise FileNotFoundError(
                f"Missing SVG for {code['title']}: {icon_path}"
            )

        svg = icon_path.read_bytes()
        ElementTree.fromstring(svg)
        encoded = base64.b64encode(svg).decode("ascii")
        code["image"] = {
            "light": {"type": "svg", "data": encoded},
            "dark": {"type": "svg", "data": encoded},
        }
        serialized_icons.append(icon_path.relative_to(REPO_ROOT))

    PROJECT_PATH.write_text(
        json.dumps(project, indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        "Serialized {} command SVGs into {}.".format(
            len(serialized_icons),
            PROJECT_PATH.relative_to(REPO_ROOT),
        )
    )


if __name__ == "__main__":
    main()
