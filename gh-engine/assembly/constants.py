"""Shared constants for generated assembly/constraint Grasshopper sessions."""

STICKY_KEY = "AssemblyGH.ActiveSession"
GENERATED_PROJECT_PREFIX = "AssemblyGH POC"
GENERATED_DIR_NAME = "generated"

MATE_TYPES = (
    "coincident",
    "concentric",
    "parallel",
    "perpendicular",
    "tangent",
    "distance",
    "angle",
    "lock",
    "hinge",
    "slider",
    "eccentric_joint",
)

MOVING_MATE_TYPES = (
    "hinge",
    "slider",
    "eccentric_joint",
)
