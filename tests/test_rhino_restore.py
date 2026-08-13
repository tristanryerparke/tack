from pathlib import Path

from rhino_flow import run_flow


RHINO_DIR = Path(__file__).with_name("rhino")
RESTORE_SAVED_TACK = RHINO_DIR / "restore_saved_tack.py"
SAVED_TACK_FILE = Path(__file__).with_name("tack_restore_fixture.3dm")


def test_tack_restore_rebuilds_runtime_from_saved_document(
    saved_tack_rhino_instance,
):
    result = run_flow(
        [("script", RESTORE_SAVED_TACK)],
        saved_tack_rhino_instance,
    )[0]

    assert result["name"] == "restore_saved_tack"
    assert Path(result["document_path"]).name == SAVED_TACK_FILE.name
    assert result["runtime_count"] == 1
    assert result["link_id"]
    assert result["parent_id"]
    assert result["child_id"]
