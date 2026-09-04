"""Fixtures for tests that launch a disposable Rhino instance."""

import json
import shutil
from pathlib import Path

import pytest


BLANK_FILE = Path(__file__).with_name("blank_file.3dm")


@pytest.fixture(scope="session")
def _rhino_instance_for_document():
    from run_in_rhino.app_control.instance import launch_rhino
    from run_in_rhino.orchestration import run_rhino_python_til_done

    current = {"source": None, "instance": None}

    def run_script(instance, script):
        reason, data = run_rhino_python_til_done(
            script=script,
            pipe_path=instance.pipe_path,
        )
        assert reason == "done"
        return data

    def open_document(instance, source):
        destination = instance.document_path.parent / source.name
        shutil.copy2(source, destination)
        run_script(
            instance,
            """import rhinoscriptsyntax as rs
from run_in_rhino.rhino_env.client import SocketConnection
from run_in_rhino.rhino_env.parasite import OutputParasite

target = {!r}
connection = SocketConnection()
with OutputParasite(connection, done_msg=True):
    assert rs.Command("_-Save _Enter", echo=False)
    assert rs.Command('_-Open "{{}}" _Enter'.format(target), echo=False)
""".format(str(destination)),
        )
        data = run_script(
            instance,
            """import json
import Rhino
from run_in_rhino.rhino_env.client import SocketConnection
from run_in_rhino.rhino_env.parasite import OutputParasite

connection = SocketConnection()
with OutputParasite(connection, done_msg=True):
    connection.send_data(json.dumps({"document_path": Rhino.RhinoDoc.ActiveDoc.Path}))
""",
        )
        assert len(data) == 1
        assert Path(json.loads(data[0])["document_path"]).resolve() == destination
        instance.document_path = destination

    def instance_for(source):
        source = Path(source).resolve()
        instance = current["instance"]
        if (
            current["source"] == source
            and instance is not None
            and instance.process.poll() is None
        ):
            return instance
        if instance is None or instance.process.poll() is not None:
            instance = launch_rhino(source, disposable=True)
            run_script(
                instance,
                """# r: websocket-client
from run_in_rhino.rhino_env.client import SocketConnection
SocketConnection().send_done()
""",
            )
        else:
            open_document(instance, source)

        current["source"] = source
        current["instance"] = instance
        return instance

    yield instance_for

    if current["instance"] is not None:
        current["instance"].stop()


@pytest.fixture
def rhino_instance(_rhino_instance_for_document):
    return _rhino_instance_for_document(BLANK_FILE)
