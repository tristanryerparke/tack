"""Verify a saved analytic-plane relationship rebuilds after reopening."""

import sys

import scriptcontext as sc

sys.modules.pop("common", None)
from common import run_test


def verify_restore():
    from tack.links import (
        repository,
        runtime,
        state,
    )

    doc = sc.doc
    runtime.remove_runtime(doc)
    restored_count = runtime.restore_document(doc, default_display_enabled=False)
    links = repository.all_links(doc)
    states = state.states(doc, create=False)

    assert len(links) == 1
    assert restored_count == 1
    assert set(states) == {links[0]["link_id"]}
    assert not runtime.display_enabled(doc)
    return {
        "link_id": links[0]["link_id"],
        "restored_count": restored_count,
    }


run_test("verify_restore", verify_restore)
