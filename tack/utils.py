import System


DEBUG = True
RUNTIME_KEY = "Tack.AnchorLink.Runtime"
CONDUIT_KEY = "Tack.AnchorLink.Conduit"


def same_id(left, right):
    return str(left).lower() == str(right).lower()


def usable_object_id(object_id):
    return not same_id(object_id, System.Guid.Empty)


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
    for object_id in object_ids or event_object_ids(event):
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
