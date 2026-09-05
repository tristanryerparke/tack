#! python 3

import os
import sys

from Rhino.Commands import Result


python_root = os.path.join(
    os.path.dirname(__rhino_command__.GetType().Assembly.Location),
    "Python",
)
if python_root not in sys.path:
    sys.path.insert(0, python_root)

from tack import settings


result = settings.show(__rhino_doc__)
