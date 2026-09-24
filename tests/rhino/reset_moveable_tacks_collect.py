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
    link = repository.all_links(doc)[0]
    return {
        "child": point_data(_origin(doc, link.child_plane_def)),
        "at_original_relationship": transforms.transform_data_matches(
            link.current_transform,
            link.original_transform,
        ),
        "resettable_count": len(runtime.resettable_links(doc)),
    }


run_flow_step("reset_moveable_tacks_collect", collect_reset_moveable_tacks)
