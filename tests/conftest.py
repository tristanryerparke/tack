from pathlib import Path

import pytest

from run_in_rhino.app_control.instance import launch_rhino


BLANK_FILE = Path(__file__).with_name("blank_file.3dm")


@pytest.fixture(scope="session")
def rhino_instance():
    with launch_rhino(BLANK_FILE, disposable=True) as instance:
        yield instance
