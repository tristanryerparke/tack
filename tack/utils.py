import json
import os

import System


SETTINGS_KEY = "Tack.LiveSettings"
DOCUMENT_SETTINGS_SECTION = "Tack"
DOCUMENT_SETTINGS_ENTRY = "Settings.v1"
DOCUMENT_DISPLAY_ENTRY = "Display.v1"
_SETTING_NAMES = (
    "debug",
    "advanced_reconciliation",
    "allow_child_movement",
)
_SETTING_DEFAULTS = {
    "debug": False,
    "advanced_reconciliation": False,
    "allow_child_movement": False,
}


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


def _read_document_settings(doc):
    if doc is None:
        return None
    try:
        raw = doc.Strings.GetValue(
            DOCUMENT_SETTINGS_SECTION,
            DOCUMENT_SETTINGS_ENTRY,
        )
        data = json.loads(str(raw))
    except Exception:
        return None
    if not isinstance(data, dict) or data.get("version") != 1:
        return None
    return {
        name: data[name]
        for name in _SETTING_NAMES
        if isinstance(data.get(name), bool)
    }


def _complete_settings(settings=None):
    complete = dict(_SETTING_DEFAULTS)
    if settings:
        complete.update(settings)
    return complete


def _apply_settings(settings):
    global DEBUG
    global ADVANCED_RECONCILIATION
    global ALLOW_CHILD_MOVEMENT

    DEBUG = bool(settings["debug"]) or _debug_enabled_from_environment()
    ADVANCED_RECONCILIATION = bool(settings["advanced_reconciliation"])
    ALLOW_CHILD_MOVEMENT = bool(settings["allow_child_movement"])
    try:
        import scriptcontext as sc
    except ImportError:
        return settings
    sc.sticky[SETTINGS_KEY] = dict(settings)
    return settings


def _write_document_settings(doc, settings):
    data = dict(settings)
    data["version"] = 1
    doc.Strings.SetString(
        DOCUMENT_SETTINGS_SECTION,
        DOCUMENT_SETTINGS_ENTRY,
        json.dumps(data, sort_keys=True),
    )


def document_settings(doc):
    saved = _read_document_settings(doc)
    return _complete_settings(saved)


def saved_document_display_enabled(doc):
    if doc is None:
        return None
    try:
        value = doc.Strings.GetValue(
            DOCUMENT_SETTINGS_SECTION,
            DOCUMENT_DISPLAY_ENTRY,
        )
    except Exception:
        return None
    if value == "shown":
        return True
    if value == "hidden":
        return False
    return None


def set_document_display_enabled(doc, enabled):
    enabled = bool(enabled)
    doc.Strings.SetString(
        DOCUMENT_SETTINGS_SECTION,
        DOCUMENT_DISPLAY_ENTRY,
        "shown" if enabled else "hidden",
    )
    return enabled


def ensure_document_display_enabled(doc):
    enabled = saved_document_display_enabled(doc)
    if enabled is None:
        return set_document_display_enabled(doc, True)
    return enabled


def ensure_document_settings(doc):
    saved = _read_document_settings(doc)
    settings = _complete_settings(saved)
    if saved != settings:
        _write_document_settings(doc, settings)
    return _apply_settings(settings)


def load_document_settings(doc):
    saved = _read_document_settings(doc)
    if saved is None:
        return None
    return _apply_settings(_complete_settings(saved))


def set_document_settings(doc, settings):
    unknown = set(settings) - set(_SETTING_NAMES)
    if unknown:
        raise ValueError(
            "Unknown Tack setting(s): {}".format(", ".join(sorted(unknown)))
        )
    complete = _complete_settings(
        {name: bool(value) for name, value in settings.items()}
    )
    _write_document_settings(doc, complete)
    return _apply_settings(complete)


def get_setting(name, doc=None):
    if name not in _SETTING_NAMES:
        raise ValueError("Unknown Tack setting: {}".format(name))
    if doc is not None:
        saved = _read_document_settings(doc)
        if saved is not None:
            return _complete_settings(saved)[name]
    if name == "debug":
        return DEBUG
    if name == "advanced_reconciliation":
        return ADVANCED_RECONCILIATION
    return ALLOW_CHILD_MOVEMENT


def set_setting(name, value, doc=None):
    if name not in _SETTING_NAMES:
        raise ValueError("Unknown Tack setting: {}".format(name))
    value = bool(value)
    if doc is not None:
        settings = document_settings(doc)
        settings[name] = value
        set_document_settings(doc, settings)
        return value

    settings = {
        "debug": DEBUG,
        "advanced_reconciliation": ADVANCED_RECONCILIATION,
        "allow_child_movement": ALLOW_CHILD_MOVEMENT,
    }
    settings[name] = value
    _apply_settings(settings)
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


def debug_point(point):
    if point is None:
        return "None"
    return "({:.6f}, {:.6f}, {:.6f})".format(point.X, point.Y, point.Z)
