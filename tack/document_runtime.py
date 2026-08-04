import scriptcontext as sc


REGISTRY_KEY = "Tack.DocumentRuntimeData"


def document_key(doc):
    if doc is None:
        raise ValueError("A Rhino document is required.")
    return int(doc.RuntimeSerialNumber)


def _registry(create):
    if create:
        return sc.sticky.setdefault(REGISTRY_KEY, {})
    return sc.sticky.get(REGISTRY_KEY)


def get_value(doc, key, factory):
    registry = _registry(True)
    values = registry.setdefault(document_key(doc), {})
    if key not in values:
        values[key] = factory(doc)
    return values[key]


def try_get_value(doc, key):
    registry = _registry(False)
    if registry is None:
        return None
    values = registry.get(document_key(doc))
    if values is None:
        return None
    return values.get(key)


def set_value(doc, key, value):
    registry = _registry(True)
    registry.setdefault(document_key(doc), {})[key] = value
    return value


def remove_value(doc, key):
    registry = _registry(False)
    if registry is None:
        return None
    document_id = document_key(doc)
    values = registry.get(document_id)
    if values is None:
        return None
    value = values.pop(key, None)
    if not values:
        registry.pop(document_id, None)
    if not registry:
        sc.sticky.pop(REGISTRY_KEY, None)
    return value


def remove_document(doc):
    registry = _registry(False)
    if registry is None:
        return None
    values = registry.pop(document_key(doc), None)
    if not registry:
        sc.sticky.pop(REGISTRY_KEY, None)
    return values


def has_nonempty_value(key):
    registry = _registry(False)
    return bool(
        registry
        and any(values.get(key) for values in registry.values())
    )
