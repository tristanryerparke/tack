import scriptcontext as sc

from glue_constants import STATE_KEY
from glue_metadata import clear_metadata


def new_state():
    return {
        "relationships": {},
        "busy": False,
        "handled_parent_ids": set(),
        "pending_replacement_parent_ids": set(),
    }


def get_state():
    state = sc.sticky.get(STATE_KEY)
    if not isinstance(state, dict) or "relationships" not in state:
        state = new_state()
        sc.sticky[STATE_KEY] = state
    return state


def remove_relationship(state, doc, relation_id):
    relationship = state["relationships"].pop(relation_id, None)
    if relationship is None:
        return

    clear_metadata(doc, relationship["follower_id"])
    clear_metadata(doc, relationship["driver_id"])


def remove_relationships_for_object(state, doc, object_id):
    relationship_ids = [
        relation_id
        for relation_id, relationship in state["relationships"].items()
        if object_id in (relationship["follower_id"], relationship["driver_id"])
    ]

    for relation_id in relationship_ids:
        remove_relationship(state, doc, relation_id)

    # Also removes stale metadata left by a previous script/session.
    clear_metadata(doc, object_id)
