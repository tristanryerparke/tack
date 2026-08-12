import sys

import Rhino
import scriptcontext as sc

sys.modules.pop("common", None)

from common import run_step
from common import tack_modules


TEST_VALUE_KEY = "Tack.Test.DocumentRuntimeIsolation"


def test_document_runtime_isolation():
    tack_modules(reload_modules=True)
    from tack import document_runtime

    active_doc = sc.doc
    assert active_doc is not None
    second_doc = Rhino.RhinoDoc.CreateHeadless(None)
    assert second_doc is not None
    assert active_doc.RuntimeSerialNumber != second_doc.RuntimeSerialNumber

    try:
        first_value = {"link": "first-document"}
        second_value = {"link": "second-document"}
        document_runtime.set_value(active_doc, TEST_VALUE_KEY, first_value)
        document_runtime.set_value(second_doc, TEST_VALUE_KEY, second_value)

        assert document_runtime.try_get_value(
            active_doc,
            TEST_VALUE_KEY,
        ) is first_value
        assert document_runtime.try_get_value(
            second_doc,
            TEST_VALUE_KEY,
        ) is second_value

        document_runtime.remove_document(second_doc)
        assert document_runtime.try_get_value(
            active_doc,
            TEST_VALUE_KEY,
        ) is first_value
        assert document_runtime.try_get_value(
            second_doc,
            TEST_VALUE_KEY,
        ) is None
    finally:
        document_runtime.remove_value(active_doc, TEST_VALUE_KEY)
        document_runtime.remove_document(second_doc)
        second_doc.Dispose()


run_step("test_document_runtime_isolation", test_document_runtime_isolation)
