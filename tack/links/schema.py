"""The persistent Tack relationship model and its JSON validation."""

from __future__ import annotations

import math
import uuid
from collections.abc import Iterator, Mapping
from dataclasses import dataclass

from tack.anchors import analytic_plane
from tack.core.objects import same_id
from tack.links.transforms import identity_transform_data


@dataclass(frozen=True)
class Link(Mapping[str, object]):
    """One persisted Tack, stored in its parent object's user dictionary.

    Mapping support keeps the serialized field names available to existing Rhino
    scripts while product code uses the named attributes.
    """

    link_id: str
    created_at: str | None
    parent_id: str
    child_id: str
    parent_plane_def: dict
    child_plane_def: dict
    translation: bool
    rotation: bool
    allow_child_movement: bool
    original_transform: list
    current_transform: list
    valid: bool = True

    def to_data(self):
        return {
            "link_id": self.link_id,
            "created_at": self.created_at,
            "parent_id": self.parent_id,
            "child_id": self.child_id,
            "parent_plane_def": self.parent_plane_def,
            "child_plane_def": self.child_plane_def,
            "translation": self.translation,
            "rotation": self.rotation,
            "allow_child_movement": self.allow_child_movement,
            "original_transform": self.original_transform,
            "current_transform": self.current_transform,
            "valid": self.valid,
        }

    def __getitem__(self, name):
        return self.to_data()[name]

    def __iter__(self) -> Iterator[str]:
        return iter(self.to_data())

    def __len__(self):
        return len(self.to_data())


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


def valid_link_id(link_id):
    if not isinstance(link_id, str) or len(link_id) != 8:
        return False
    try:
        return f"{int(link_id, 16):08x}" == link_id
    except ValueError:
        return False


def new_link_id(links):
    """Return an ID absent from a mapping or iterable of Links."""
    ids = set(links) if isinstance(links, Mapping) else {link.link_id for link in links}
    while True:
        link_id = uuid.uuid4().hex[:8]
        if link_id not in ids:
            return link_id


def _legacy_link(data):
    """Translate the previous attached/inherit-only model while reading it."""
    required = {
        "link_id",
        "created_at",
        "parent_id",
        "child_id",
        "parent_plane_def",
        "child_plane_def",
        "inverted",
        "mode",
        "translation",
        "rotation",
    }
    allowed = required | {"valid", "original_transform", "current_transform"}
    if not required.issubset(data) or not set(data).issubset(allowed):
        return None

    mode = data["mode"]
    if mode not in ("attached", "inherit_only") or not isinstance(
        data["inverted"], bool
    ):
        return None
    child_plane_def = data["child_plane_def"]
    if data["inverted"]:
        child_plane_def = analytic_plane.flipped_definition(child_plane_def)
    identity = identity_transform_data()
    return Link(
        link_id=data["link_id"],
        created_at=data["created_at"],
        parent_id=data["parent_id"],
        child_id=data["child_id"],
        parent_plane_def=data["parent_plane_def"],
        child_plane_def=child_plane_def,
        translation=data["translation"],
        rotation=data["rotation"],
        allow_child_movement=mode == "inherit_only",
        original_transform=(
            data["original_transform"] if mode == "inherit_only" else identity
        ),
        current_transform=(
            data["current_transform"] if mode == "inherit_only" else list(identity)
        ),
        valid=data.get("valid", True),
    )


def from_data(data, expected_link_id=None):
    """Parse object metadata into a Link, including the prior Link format."""
    if isinstance(data, Link):
        link = data
    elif isinstance(data, dict):
        required = {
            "link_id",
            "created_at",
            "parent_id",
            "child_id",
            "parent_plane_def",
            "child_plane_def",
            "translation",
            "rotation",
            "allow_child_movement",
            "original_transform",
            "current_transform",
        }
        allowed = required | {"valid"}
        if required.issubset(data) and set(data).issubset(allowed):
            link = Link(
                link_id=data["link_id"],
                created_at=data["created_at"],
                parent_id=data["parent_id"],
                child_id=data["child_id"],
                parent_plane_def=data["parent_plane_def"],
                child_plane_def=data["child_plane_def"],
                translation=data["translation"],
                rotation=data["rotation"],
                allow_child_movement=data["allow_child_movement"],
                original_transform=data["original_transform"],
                current_transform=data["current_transform"],
                valid=data.get("valid", True),
            )
        else:
            link = _legacy_link(data)
            if link is None:
                return None
    else:
        return None

    if (
        not valid_link_id(link.link_id)
        or (
            link.created_at is not None
            and (not isinstance(link.created_at, str) or not link.created_at.strip())
        )
        or (
            expected_link_id is not None
            and not same_id(link.link_id, expected_link_id)
        )
        or not link.parent_id
        or not link.child_id
        or not isinstance(link.valid, bool)
        or not isinstance(link.translation, bool)
        or not isinstance(link.rotation, bool)
        or not isinstance(link.allow_child_movement, bool)
        or not (
            valid_transform(link.original_transform)
            and valid_transform(link.current_transform)
        )
    ):
        return None
    if not (
        analytic_plane.validate_definition(link.parent_plane_def)
        and analytic_plane.validate_definition(link.child_plane_def)
    ):
        return None
    return link


def validate(link, expected_link_id=None):
    return from_data(link, expected_link_id) is not None


def same_object_pair(left, right):
    return (
        same_id(left["parent_id"], right["parent_id"])
        and same_id(left["child_id"], right["child_id"])
    ) or (
        same_id(left["parent_id"], right["child_id"])
        and same_id(left["child_id"], right["parent_id"])
    )
