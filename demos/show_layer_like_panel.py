"""Run inside Rhino to open the floating layer-panel mock."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from layer_like_panel.runtime import open_panel


if __name__ == "__main__":
    open_panel()
