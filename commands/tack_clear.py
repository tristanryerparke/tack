#! python 3

import os
import sys

from Rhino.Commands import Result
from RhinoCodePlatform.Rhino3D.Projects.Plugin import ProjectPlugin

python_root = os.path.join(
    os.path.dirname(__rhino_command__.GetType().Assembly.Location),
    "Python",
)
if python_root not in sys.path:
    sys.path.insert(0, python_root)

from tack import actions


result = actions.run(
    "clear",
    doc=__rhino_doc__,
    default_display_enabled=ProjectPlugin.DefaultDisplayEnabled,
)
if result == Result.Success:
    ProjectPlugin.SaveDisplayPreference("clear")
