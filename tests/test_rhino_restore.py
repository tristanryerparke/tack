from pathlib import Path

from rhino_flow import run_flow


RHINO_DIR = Path(__file__).with_name("rhino")
REDEFINE_SAVED_TACK = RHINO_DIR / "redefine_saved_tack.py"
RESTORE_SAVED_TACK = RHINO_DIR / "restore_saved_tack.py"
SAVED_TACK_FILE = Path(__file__).with_name("tack_restore_fixture.3dm")


def test_tack_restore_rebuilds_runtime_and_configuration_from_saved_document(
    _rhino_instance_for_document,
    tmp_path,
):
    rebuilt_file = tmp_path / "current_tack_restore_fixture.3dm"
    setup = run_flow(
        [("script", REDEFINE_SAVED_TACK)],
        _rhino_instance_for_document(SAVED_TACK_FILE),
        environment={"TACK_RESTORE_FIXTURE_PATH": str(rebuilt_file)},
    )[0]

    assert setup["name"] == "redefine_saved_tack"
    assert Path(setup["fixture_path"]) == rebuilt_file
    assert rebuilt_file.is_file()

    result = run_flow(
        [("script", RESTORE_SAVED_TACK)],
        _rhino_instance_for_document(rebuilt_file),
    )[0]

    assert result["name"] == "restore_saved_tack"
    assert Path(result["document_path"]).name == rebuilt_file.name
    assert result["runtime_count"] == 1
    assert result["link_id"] == setup["link_id"]
    assert result["link_version"] == setup["link_version"]
    assert result["parent_id"] == setup["parent_id"]
    assert result["child_id"] == setup["child_id"]
    assert result["settings"] == setup["settings"]
    assert result["display_enabled"] is False
    assert result["document_strings_unchanged"]
