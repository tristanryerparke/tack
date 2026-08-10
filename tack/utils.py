import os

import System


SETTINGS_KEY = "Tack.LiveSettings"


def _live_settings():
    try:
        import scriptcontext as sc
    except ImportError:
        return {}
    return sc.sticky.get(SETTINGS_KEY, {})


def _as_bool(value):
    if isinstance(value, str):
        return value.strip().lower() in ("1", "true", "yes", "on")
    return bool(value)


def _debug_enabled_from_environment():
    return any(
        os.getenv(name, "").strip().lower() in ("1", "true", "yes", "on")
        for name in ("debug", "TACK_DEBUG")
    )


# run-in-rhino installs its environment before the watched target script runs.
# Normal Rhino sessions provide neither value, so Tack remains silent.
live_settings = _live_settings()
DEBUG = _as_bool(
    live_settings.get("debug", _debug_enabled_from_environment())
)

# Reconcile replacement objects created by operations such as BooleanDifference
# and Split by matching their anchor geometry. Basic reconciliation remains
# available when this is disabled.
ADVANCED_RECONCILIATION = _as_bool(
    live_settings.get("advanced_reconciliation", False)
)
ALLOW_CHILD_MOVEMENT = _as_bool(
    live_settings.get("allow_child_movement", False)
)


def set_setting(name, value):
    if name not in (
        "debug",
        "advanced_reconciliation",
        "allow_child_movement",
    ):
        raise ValueError("Unknown Tack setting: {}".format(name))
    value = bool(value)
    if name == "debug":
        global DEBUG
        DEBUG = value
    elif name == "advanced_reconciliation":
        global ADVANCED_RECONCILIATION
        ADVANCED_RECONCILIATION = value
    else:
        global ALLOW_CHILD_MOVEMENT
        ALLOW_CHILD_MOVEMENT = value
    try:
        import scriptcontext as sc
    except ImportError:
        return value
    settings = sc.sticky.setdefault(SETTINGS_KEY, {})
    settings[name] = value
    return value


def debug(message):
    if DEBUG:
        print(message)


RUNTIME_KEY = "Tack.AnchorLink.Runtime"
DISPLAY_ENABLED_KEY = "Tack.AnchorLink.DisplayEnabled"
CONDUIT_KEY = "Tack.AnchorLink.Conduit"
SCHEDULE_KEY = "Tack.AnchorLink.Schedule"


def same_id(left, right):
    return str(left).lower() == str(right).lower()


def find_object(doc, object_id):
    if doc is None or object_id is None:
        return None
    try:
        object_id = System.Guid.Parse(str(object_id))
    except Exception:
        return None
    return doc.Objects.Find(object_id)


def undo_or_redo(doc):
    return doc is not None and (
        bool(getattr(doc, "UndoActive", False))
        or bool(getattr(doc, "RedoActive", False))
    )


def event_object_ids(event):
    ids = []

    def add(value):
        if value is None:
            return
        try:
            value = value.Id
        except Exception:
            pass
        try:
            value = System.Guid.Parse(str(value))
        except Exception:
            return
        if value not in ids:
            ids.append(value)

    for name in ("ObjectId", "NewObjectId", "TheObject", "Object", "NewObject"):
        try:
            add(getattr(event, name))
        except Exception:
            pass
    for name in ("ObjectIds", "NewObjectIds"):
        try:
            for value in getattr(event, name):
                add(value)
        except Exception:
            pass
    return ids


def event_object(doc, event, object_ids=None):
    if event is None:
        return None
    for name in ("TheObject", "Object", "NewObject"):
        candidate = getattr(event, name, None)
        if candidate is not None and hasattr(candidate, "Geometry"):
            return candidate
    event_ids = event_object_ids(event) if object_ids is None else object_ids
    for object_id in event_ids:
        candidate = doc.Objects.Find(object_id)
        if candidate is not None:
            return candidate
    return None


def debug_point(point):
    if point is None:
        return "None"
    return "({:.6f}, {:.6f}, {:.6f})".format(point.X, point.Y, point.Z)


def debug_event(label, event, state):
    if DEBUG:
        print(
            "[Tack anchor] {} event={} ids={} parent={} child={} busy={}".format(
                label,
                type(event).__name__,
                [str(value) for value in event_object_ids(event)],
                state.get("parent_id"),
                state.get("child_id"),
                state.get("busy"),
            )
        )
