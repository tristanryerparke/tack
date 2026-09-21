import System


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
