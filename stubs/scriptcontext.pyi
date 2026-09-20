"""Stubs for modules that Rhino provides only at runtime."""

from typing import Any

import Rhino

doc: Rhino.RhinoDoc
id: int
sticky: dict[Any, Any]
__complete__: list[str]


def escape_test(throw_exception: bool = True, reset: bool = False) -> bool: ...
def errorhandler() -> None: ...
def localize(text: str) -> Rhino.UI.LocalizeStringPair: ...
