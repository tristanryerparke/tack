"""Helpers for looking up Rhino document objects by id."""

from __future__ import annotations

import Rhino
import System


def object_key(object_id: System.Guid | str) -> str:
    """Return a case-insensitive key for a Rhino object ID."""
    return str(object_id).lower()


def same_id(left: System.Guid | str, right: System.Guid | str) -> bool:
    """Compare two object ids case-insensitively."""
    return object_key(left) == object_key(right)


def find_object(
    doc: Rhino.RhinoDoc | None, object_id: System.Guid | str | None
) -> Rhino.DocObjects.RhinoObject | None:
    """Look up a document object by id, returning None when not found."""
    if doc is None or object_id is None:
        return None
    try:
        object_id = System.Guid.Parse(str(object_id))
    except Exception:  # noqa: BLE001
        return None
    return doc.Objects.Find(object_id)
