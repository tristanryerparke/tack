"""Verify a saved analytic-plane relationship rebuilds after reopening."""

import sys

import scriptcontext as sc

sys.modules.pop("common", None)
from common import run_test



def verify_restore():
    from tack import plane_link
    from tack import plane_link_metadata

    doc = sc.doc
    plane_link._remove_runtime(doc)
    restored_count = plane_link.restore_document(doc, default_display_enabled=False)
    links = plane_link_metadata.all_links(doc)
    states = plane_link.states(doc, create=False)

    assert len(links) == 1
    assert restored_count == 1
    assert set(states) == {links[0]["link_id"]}
    assert not plane_link.display_enabled(doc)
    return {
        "link_id": links[0]["link_id"],
        "restored_count": restored_count,
    }


run_test("verify_restore", verify_restore)
