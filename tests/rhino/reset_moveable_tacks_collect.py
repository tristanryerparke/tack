"""Collect the child position and relationship state after reset or Undo."""

import sys

import scriptcontext as sc

sys.modules.pop("common", None)
from common import point_data, run_flow_step


def _origin(doc, definition):
    from tack.anchors import analytic_plane

    plane = analytic_plane.resolve_definition(doc, definition)
    assert plane is not None
    return plane.Origin


def collect_reset_moveable_tacks():
    from tack.links import repository, runtime, transforms

    doc = sc.doc
    links = repository.all_links(doc)
    parent_ids = {link.parent_id for link in links}
    child_ids = {link.child_id for link in links}
    root_id = next(iter(parent_ids - child_ids))
    parent_link = next(link for link in links if link.parent_id == root_id)
    child_link = next(link for link in links if link.parent_id == parent_link.child_id)
    return {
        "middle": point_data(_origin(doc, parent_link.child_plane_def)),
        "child": point_data(_origin(doc, child_link.child_plane_def)),
        "at_original_relationships": all(
            transforms.transform_data_matches(
                link.current_transform,
                link.original_transform,
            )
            for link in links
        ),
        "resettable_count": len(runtime.resettable_links(doc)),
    }


run_flow_step("reset_moveable_tacks_collect", collect_reset_moveable_tacks)
