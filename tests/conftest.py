"""Fixtures for tests that launch a disposable Rhino instance."""

from pathlib import Path

import pytest


BLANK_FILE = Path(__file__).with_name("blank_file.3dm")


@pytest.fixture(scope="session")
def _rhino_instance_for_document():
    from run_in_rhino.app_control.instance import launch_rhino

    current = {"source": None, "instance": None}

    def instance_for(source):
        source = Path(source).resolve()
        instance = current["instance"]
        if (
            current["source"] == source
            and instance is not None
            and instance.process.poll() is None
        ):
            return instance
        if instance is not None:
            instance.stop()

        current["source"] = source
        current["instance"] = launch_rhino(source, disposable=True)
        return current["instance"]

    yield instance_for

    if current["instance"] is not None:
        current["instance"].stop()


@pytest.fixture
def rhino_instance(_rhino_instance_for_document):
    return _rhino_instance_for_document(BLANK_FILE)
