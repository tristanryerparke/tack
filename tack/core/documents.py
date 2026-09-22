import scriptcontext as sc

REGISTRY_KEY = "Tack.DocumentsData"


def document_key(doc):
    """Return a document's unique serial number, raising if the document is missing."""
    if doc is None:
        raise ValueError("A Rhino document is required.")
    return int(doc.RuntimeSerialNumber)


def _registry(create):
    """Return the shared document registry, creating it if `create` is True."""
    if create:
        return sc.sticky.setdefault(REGISTRY_KEY, {})
    return sc.sticky.get(REGISTRY_KEY)


def get_value(doc, key, factory):
    """Return the stored value for `key`, creating it with `factory(doc)` if absent."""
    registry = _registry(True)
    values = registry.setdefault(document_key(doc), {})
    if key not in values:
        values[key] = factory(doc)
    return values[key]


def try_get_value(doc, key):
    """Return the stored value for `key`, or None if nothing was ever stored."""
    registry = _registry(False)
    if registry is None:
        return None
    values = registry.get(document_key(doc))
    if values is None:
        return None
    return values.get(key)


def set_value(doc, key, value):
    """Store `value` under `key` for the document, overwriting any existing entry."""
    registry = _registry(True)
    registry.setdefault(document_key(doc), {})[key] = value
    return value


def remove_value(doc, key):
    """Remove and return one stored value, cleaning up empty registry entries."""
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
    """Remove and return everything stored for a document, cleaning up the registry."""
    registry = _registry(False)
    if registry is None:
        return None
    values = registry.pop(document_key(doc), None)
    if not registry:
        sc.sticky.pop(REGISTRY_KEY, None)
    return values


def has_nonempty_value(key):
    """Return True if any open document has a truthy value stored under `key`."""
    registry = _registry(False)
    return bool(registry and any(values.get(key) for values in registry.values()))


def has_matching_value(key, predicate):
    """Return whether an open document has a stored value matching `predicate`."""
    registry = _registry(False)
    return bool(
        registry
        and any(
            key in values and predicate(values[key]) for values in registry.values()
        )
    )
