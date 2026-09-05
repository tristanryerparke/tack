"""Pure graph checks for directed Tack relationships."""


def object_key(object_id):
    return str(object_id).lower()


def would_create_cycle(links, parent_id, child_id):
    """Return whether adding parent_id -> child_id closes a directed cycle."""
    parent_key = object_key(parent_id)
    child_key = object_key(child_id)
    if parent_key == child_key:
        return True

    children = {}
    for link in links:
        source = link.get("parent_id")
        target = link.get("child_id")
        if source is None or target is None:
            continue
        children.setdefault(object_key(source), set()).add(object_key(target))

    pending = [child_key]
    visited = set()
    while pending:
        current = pending.pop()
        if current == parent_key:
            return True
        if current in visited:
            continue
        visited.add(current)
        pending.extend(children.get(current, ()))
    return False
