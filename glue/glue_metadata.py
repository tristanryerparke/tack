META_RELATION = "GlueObjects.RelationshipId"
META_ROLE = "GlueObjects.Role"
META_PEER = "GlueObjects.PeerId"
META_TRANSLATION = "GlueObjects.Translation"
META_ROTATION = "GlueObjects.Rotation"
META_SCALE = "GlueObjects.Scale"
META_REFERENCE = "GlueObjects.Reference"
META_VERTEX_INDEX = "GlueObjects.VertexIndex"
META_VERTEX_TYPE = "GlueObjects.VertexType"
META_OFFSET_X = "GlueObjects.ReferenceOffsetX"
META_OFFSET_Y = "GlueObjects.ReferenceOffsetY"
META_OFFSET_Z = "GlueObjects.ReferenceOffsetZ"
META_FRAME_INDEX_1 = "GlueObjects.FrameIndex1"
META_FRAME_INDEX_2 = "GlueObjects.FrameIndex2"
META_FRAME_ORIGIN_X = "GlueObjects.FrameOriginX"
META_FRAME_ORIGIN_Y = "GlueObjects.FrameOriginY"
META_FRAME_ORIGIN_Z = "GlueObjects.FrameOriginZ"
META_FRAME_X_X = "GlueObjects.FrameXAxisX"
META_FRAME_X_Y = "GlueObjects.FrameXAxisY"
META_FRAME_X_Z = "GlueObjects.FrameXAxisZ"
META_FRAME_Y_X = "GlueObjects.FrameYAxisX"
META_FRAME_Y_Y = "GlueObjects.FrameYAxisY"
META_FRAME_Y_Z = "GlueObjects.FrameYAxisZ"
from glue_debug import log


META_KEYS = (
    META_RELATION,
    META_ROLE,
    META_PEER,
    META_TRANSLATION,
    META_ROTATION,
    META_SCALE,
    META_REFERENCE,
    META_VERTEX_INDEX,
    META_VERTEX_TYPE,
    META_OFFSET_X,
    META_OFFSET_Y,
    META_OFFSET_Z,
    META_FRAME_INDEX_1,
    META_FRAME_INDEX_2,
    META_FRAME_ORIGIN_X,
    META_FRAME_ORIGIN_Y,
    META_FRAME_ORIGIN_Z,
    META_FRAME_X_X,
    META_FRAME_X_Y,
    META_FRAME_X_Z,
    META_FRAME_Y_X,
    META_FRAME_Y_Y,
    META_FRAME_Y_Z,
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


def write_metadata(
    doc,
    object_id,
    relation_id,
    role,
    peer_id,
    translation,
    rotation,
    scale,
    reference,
    vertex_index,
    vertex_type,
    offset,
    frame_indices,
    frame,
):
    obj = doc.Objects.Find(object_id)
    if obj is None:
        return

    attrs = obj.Attributes.Duplicate()
    attrs.UserDictionary.Set(META_RELATION, relation_id)
    attrs.UserDictionary.Set(META_ROLE, role)
    attrs.UserDictionary.Set(META_PEER, str(peer_id))
    attrs.UserDictionary.Set(META_TRANSLATION, translation)
    attrs.UserDictionary.Set(META_ROTATION, rotation)
    attrs.UserDictionary.Set(META_SCALE, scale)
    attrs.UserDictionary.Set(META_REFERENCE, reference)
    attrs.UserDictionary.Set(META_VERTEX_INDEX, vertex_index)
    attrs.UserDictionary.Set(META_VERTEX_TYPE, vertex_type)
    for key, value in (
        (META_OFFSET_X, getattr(offset, "X", None)),
        (META_OFFSET_Y, getattr(offset, "Y", None)),
        (META_OFFSET_Z, getattr(offset, "Z", None)),
    ):
        if value is None:
            if attrs.UserDictionary.ContainsKey(key):
                attrs.UserDictionary.Remove(key)
        else:
            attrs.UserDictionary.Set(key, value)
    frame_values = {
        META_FRAME_INDEX_1: frame_indices[0] if frame_indices else None,
        META_FRAME_INDEX_2: frame_indices[1] if frame_indices else None,
        META_FRAME_ORIGIN_X: getattr(getattr(frame, "Origin", None), "X", None),
        META_FRAME_ORIGIN_Y: getattr(getattr(frame, "Origin", None), "Y", None),
        META_FRAME_ORIGIN_Z: getattr(getattr(frame, "Origin", None), "Z", None),
        META_FRAME_X_X: getattr(getattr(frame, "XAxis", None), "X", None),
        META_FRAME_X_Y: getattr(getattr(frame, "XAxis", None), "Y", None),
        META_FRAME_X_Z: getattr(getattr(frame, "XAxis", None), "Z", None),
        META_FRAME_Y_X: getattr(getattr(frame, "YAxis", None), "X", None),
        META_FRAME_Y_Y: getattr(getattr(frame, "YAxis", None), "Y", None),
        META_FRAME_Y_Z: getattr(getattr(frame, "YAxis", None), "Z", None),
    }
    for key, value in frame_values.items():
        if value is None:
            if attrs.UserDictionary.ContainsKey(key):
                attrs.UserDictionary.Remove(key)
        else:
            attrs.UserDictionary.Set(key, value)

    doc.Objects.ModifyAttributes(object_id, attrs, True)
    log(
        "metadata written: object={}, relation={}, role={}, peer={}, reference={}, vertex_type={}, vertex_index={}, offset={}, frame_indices={}".format(
            object_id,
            relation_id,
            role,
            peer_id,
            reference,
            vertex_type,
            vertex_index,
            offset,
            frame_indices,
        )
    )
