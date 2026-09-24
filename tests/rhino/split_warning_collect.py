"""Verify Split removed the endpoint and requested Tack's invalid warning."""

import sys

import scriptcontext as sc

sys.modules.pop("common", None)
from common import run_flow_step

STICKY_KEY = "Tack.SplitWarning"


def collect_split_warning():
    from tack.core.objects import find_object
    from tack.links import repository, state

    doc = sc.doc
    info = sc.sticky[STICKY_KEY]
    warning_count = info["warning"]["count"]
    endpoint_present = find_object(doc, info["endpoint_id"]) is not None
    link_present = (
        repository.read_link(
            doc,
            info["link_id"],
            include_invalid=True,
        )
        is not None
    )
    runtime_count = len(state.states(doc, create=False))

    assert warning_count == 1, "Expected one invalid-Tack warning request"
    assert not endpoint_present, "Split did not replace the {}".format(info["role"])
    assert not link_present, "Split left the Tack active"
    assert runtime_count == 0, "Split left runtime Tack state active"
    result = {
        "role": info["role"],
        "warning_count": warning_count,
        "endpoint_present": endpoint_present,
        "link_present": link_present,
        "runtime_count": runtime_count,
    }
    if info["role"] == "child":
        sc.sticky.pop(STICKY_KEY, None)
    return result


run_flow_step("split_warning_collect", collect_split_warning)
