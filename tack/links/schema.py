"""Validation and identity rules for persisted Tack relationships."""

import math
import uuid

from tack.anchors import analytic_plane
from tack.core.objects import same_id


def valid_transform(data):
    return (
        isinstance(data, list)
        and len(data) == 16
        and all(
            isinstance(value, (int, float))
            and not isinstance(value, bool)
            and math.isfinite(value)
            for value in data
        )
    )


def link_mode(link):
    """Return a Tack mode, defaulting to attached."""
    return link.get("mode", "attached")


def translation_enabled(link):
    """Return whether a Tack inherits its parent's translation."""
    return link.get("translation", True)


def rotation_enabled(link):
    """Return whether a Tack inherits its parent's rotation."""
    return link.get("rotation", True)


def valid_link_id(link_id):
    if not isinstance(link_id, str) or len(link_id) != 8:
        return False
    try:
        return f"{int(link_id, 16):08x}" == link_id
    except ValueError:
        return False


def new_link_id(index):
    while True:
        link_id = uuid.uuid4().hex[:8]
        if link_id not in index:
            return link_id


def validate(link, expected_link_id=None):
    required_fields = {
        "link_id",
        "parent_id",
        "child_id",
        "parent_plane",
        "child_plane",
        "inverted",
    }
    if not isinstance(link, dict):
        return False
    fields = set(link)
    allowed_fields = required_fields | {
        "created_at",
        "mode",
        "original_transform",
        "current_transform",
        "translation",
        "rotation",
    }
    if not required_fields.issubset(fields) or not fields.issubset(allowed_fields):
        return False
    link_id = link.get("link_id")
    created_at = link.get("created_at")
    if (
        not valid_link_id(link_id)
        or (
            created_at is not None
            and (not isinstance(created_at, str) or not created_at.strip())
        )
        or (expected_link_id is not None and not same_id(link_id, expected_link_id))
        or not link.get("parent_id")
        or not link.get("child_id")
        or not isinstance(link.get("inverted"), bool)
    ):
        return False
    mode = link_mode(link)
    if mode not in ("attached", "inherit_only") or not all(
        isinstance(link.get(field, True), bool) for field in ("translation", "rotation")
    ):
        return False
    if mode == "inherit_only" and not (
        valid_transform(link.get("original_transform"))
        and valid_transform(link.get("current_transform"))
    ):
        return False
    return analytic_plane.validate_definition(
        link["parent_plane"]
    ) and analytic_plane.validate_definition(link["child_plane"])


def same_object_pair(left, right):
    return (
        same_id(left["parent_id"], right["parent_id"])
        and same_id(left["child_id"], right["child_id"])
    ) or (
        same_id(left["parent_id"], right["child_id"])
        and same_id(left["child_id"], right["parent_id"])
    )
