import json

from glue_debug import log


META_RELATION = "GlueObjects.RelationshipId"
META_ROLE = "GlueObjects.Role"
META_PEER = "GlueObjects.PeerId"
META_DATA = "GlueObjects.RelationshipData"
META_KEYS = (
    META_RELATION,
    META_ROLE,
    META_PEER,
    META_DATA,
    "GlueObjects.Translation",
    "GlueObjects.Rotation",
    "GlueObjects.Scale",
    "GlueObjects.Reference",
    "GlueObjects.VertexIndex",
    "GlueObjects.VertexType",
    "GlueObjects.ReferenceOffsetX",
    "GlueObjects.ReferenceOffsetY",
    "GlueObjects.ReferenceOffsetZ",
    "GlueObjects.FrameIndex1",
    "GlueObjects.FrameIndex2",
    "GlueObjects.FrameOriginX",
    "GlueObjects.FrameOriginY",
    "GlueObjects.FrameOriginZ",
    "GlueObjects.FrameXAxisX",
    "GlueObjects.FrameXAxisY",
    "GlueObjects.FrameXAxisZ",
    "GlueObjects.FrameYAxisX",
    "GlueObjects.FrameYAxisY",
    "GlueObjects.FrameYAxisZ",
)


def user_value(obj, key):
    try:
        return obj.Attributes.UserDictionary[key]
    except Exception:
        return None


def clear_metadata(doc, object_id):
    obj = doc.Objects.Find(object_id)
    if obj is None:
        return

    attrs = obj.Attributes.Duplicate()
    changed = False
    for key in META_KEYS:
        try:
            if attrs.UserDictionary.ContainsKey(key):
                attrs.UserDictionary.Remove(key)
                changed = True
        except Exception:
            pass
    if changed:
        doc.Objects.ModifyAttributes(object_id, attrs, True)


def write_metadata(doc, object_id, relation_id, role, peer_id, data):
    obj = doc.Objects.Find(object_id)
    if obj is None:
        return

    attrs = obj.Attributes.Duplicate()
    attrs.UserDictionary.Set(META_RELATION, relation_id)
    attrs.UserDictionary.Set(META_ROLE, role)
    attrs.UserDictionary.Set(META_PEER, str(peer_id))
    attrs.UserDictionary.Set(META_DATA, json.dumps(data))
    doc.Objects.ModifyAttributes(object_id, attrs, True)
    log(
        "metadata written: object={}, relation={}, role={}, peer={}".format(
            object_id,
            relation_id,
            role,
            peer_id,
        )
    )


def relationship_data(obj):
    value = user_value(obj, META_DATA)
    if value is None:
        return None
    try:
        return json.loads(str(value))
    except Exception:
        return None
