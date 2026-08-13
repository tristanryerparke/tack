from pathlib import Path

import pytest

from run_in_rhino.app_control.instance import launch_rhino


BLANK_FILE = Path(__file__).with_name("blank_file.3dm")
SAVED_TACK_FILE = Path(__file__).with_name("tack_restore_fixture.3dm")


def pytest_collection_modifyitems(items):
    restore_items = [
        item
        for item in items
        if Path(str(item.fspath)).name == "test_rhino_restore.py"
    ]
    if restore_items:
        items[:] = [item for item in items if item not in restore_items] + restore_items


@pytest.fixture(scope="session")
def _rhino_instance_for_document():
    current = {"source": None, "instance": None}

    def instance_for(source):
        source = source.resolve()
        if current["source"] == source:
            return current["instance"]

        if current["instance"] is not None:
            current["instance"].stop()
        current["source"] = None
        current["instance"] = None

        instance = launch_rhino(source, disposable=True)
        current["source"] = source
        current["instance"] = instance
        return instance

    yield instance_for

    if current["instance"] is not None:
        current["instance"].stop()


@pytest.fixture
def rhino_instance(_rhino_instance_for_document):
    return _rhino_instance_for_document(BLANK_FILE)


@pytest.fixture
def saved_tack_rhino_instance(_rhino_instance_for_document):
    return _rhino_instance_for_document(SAVED_TACK_FILE)
