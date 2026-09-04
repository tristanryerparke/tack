"""Run all blank-document Rhino checks through one script-server request."""

import sys

sys.modules.pop("common", None)
from anchor_definitions import verify_anchor_definitions
from duplicate_link import verify_duplicate_link_replacement
from metadata_index import verify_metadata_index
from relationship_lifecycle import verify_relationship_lifecycle

from common import _load_repository_tack, run_test


def _run(action):
    _load_repository_tack()
    return action()


def verify_blank_document():
    return {
        "anchor_definitions": _run(verify_anchor_definitions),
        "duplicate_link": _run(verify_duplicate_link_replacement),
        "metadata_index": _run(verify_metadata_index),
        "relationship_lifecycle": _run(verify_relationship_lifecycle),
    }


run_test("blank_document", verify_blank_document)
