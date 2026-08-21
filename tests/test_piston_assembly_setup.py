"""Rebuild the piston assembly in a fresh Rhino from the recorded setup JSON.

Opens a disposable copy of assets/piston_dissassembled.3dm, applies the
anchor/revolute/slider records with no user input, asserts the assembly
matches the recording, and leaves Rhino open for interactive inspection.

Close the leftover Rhino instance manually before running again;
launch_rhino refuses to start while another Rhino is running.
"""

import json
from pathlib import Path

import pytest

from rhino_flow import run_flow

from run_in_rhino.app_control.instance import launch_rhino


TESTS_DIR = Path(__file__).parent
ASSETS_DIR = TESTS_DIR.parent / "assets"
PISTON_FILE = ASSETS_DIR / "piston_dissassembled.3dm"
SETUP_JSON = ASSETS_DIR / "ondsel_assembly_setup.json"
EXPECTED_PLANES_JSON = ASSETS_DIR / "ondsel_assembly_expected_planes.json"
RHINO_TESTS = TESTS_DIR / "rhino"

# Keep the instance alive after the session so its disposable temp
# directory is not collected mid-run.
_KEEP_ALIVE = {}


@pytest.fixture(scope="module")
def piston_rhino():
    instance = launch_rhino(PISTON_FILE, disposable=True)
    _KEEP_ALIVE["instance"] = instance
    yield instance
    # Intentionally not stopped: Rhino stays open for inspection.


def _assert_plane_baseline(actual, expected):
    actual_parts = {part["object_id"]: part for part in actual["parts"]}
    expected_parts = {part["object_id"]: part for part in expected["parts"]}
    assert set(actual_parts) == set(expected_parts)

    for object_id, expected_part in expected_parts.items():
        actual_part = actual_parts[object_id]
        assert actual_part["roles"] == expected_part["roles"], object_id
        actual_planes = {
            plane["edge_index"]: plane for plane in actual_part["planes"]
        }
        expected_planes = {
            plane["edge_index"]: plane for plane in expected_part["planes"]
        }
        assert set(actual_planes) == set(expected_planes), object_id
        for edge_index, expected_plane in expected_planes.items():
            actual_plane = actual_planes[edge_index]
            assert abs(actual_plane["radius"] - expected_plane["radius"]) <= 1e-3
            assert all(
                abs(actual - expected) <= 1e-3
                for actual, expected in zip(
                    actual_plane["origin"], expected_plane["origin"]
                )
            ), (object_id, edge_index, actual_plane, expected_plane)
            normal_dot = sum(
                actual * expected
                for actual, expected in zip(
                    actual_plane["normal"], expected_plane["normal"]
                )
            )
            assert abs(normal_dot) >= 1.0 - 1e-4, (
                object_id,
                edge_index,
                actual_plane,
                expected_plane,
            )


def test_piston_assembly_from_json(piston_rhino):
    results = run_flow(
        [("script", RHINO_TESTS / "piston_setup_from_json.py")],
        piston_rhino,
        environment={"PISTON_SETUP_JSON": str(SETUP_JSON)},
    )

    assert results, "Setup script returned no payload"
    payload = results[0]
    assert payload["part_count"] == 4, payload
    assert payload["constraint_count"] == 5, payload
    assert payload["constraint_types"] == [
        "revolute",
        "revolute",
        "revolute",
        "slider_axis",
        "world_anchor",
    ], payload
    assert len(payload["part_ids"]) == 4, payload

    with EXPECTED_PLANES_JSON.open() as handle:
        expected_planes = json.load(handle)
    _assert_plane_baseline(payload["plane_records"], expected_planes)
