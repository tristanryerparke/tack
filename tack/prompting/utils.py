"""Shared helpers for interactive pickers."""

import rhinoscriptsyntax as rs


def lock_other_objects(doc, target_id):
    locked_ids = []
    for candidate in doc.Objects:
        if candidate is None or str(candidate.Id).lower() == str(target_id).lower():
            continue
        try:
            if not rs.IsObjectLocked(candidate.Id) and rs.LockObject(candidate.Id):
                locked_ids.append(candidate.Id)
        except Exception:
            pass
    return locked_ids


def unlock_objects(object_ids):
    for object_id in object_ids:
        try:
            rs.UnlockObject(object_id)
        except Exception:
            pass
