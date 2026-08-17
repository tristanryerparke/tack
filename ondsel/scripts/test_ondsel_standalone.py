"""Standalone sanity check for the ondselsolver module.

Run with Rhino's own CPython (not the system python):

    ~/.rhinocode/py39-rh8/python3.99 ondsel/scripts/test_ondsel_standalone.py

Expected: the bolt part moves from (100, 40, 30) to the base's hole marker
at (10, 5, 0), with its orientation free about the joint's Z axis.
"""
import os
import sys

sys.path.insert(
    0,
    os.path.join(os.path.dirname(__file__), "..", "rhino_modules"),
)

import ondselsolver  # noqa: E402

assembly = ondselsolver.Assembly("Assembly1")

assembly.add_part("base", (0.0, 0.0, 0.0), (1.0, 0.0, 0.0, 0.0))
assembly.add_part("bolt", (100.0, 40.0, 30.0), (1.0, 0.0, 0.0, 0.0))

assembly.set_fixed("base", True)

assembly.add_marker("base", "hole", (10.0, 5.0, 0.0), (1.0, 0.0, 0.0, 0.0))
assembly.add_marker("bolt", "axis", (0.0, 0.0, 0.0), (1.0, 0.0, 0.0, 0.0))

assembly.add_revolute_joint("J1", "base", "hole", "bolt", "axis")

print("before solve:")
print("  base:", assembly.get_pose("base"))
print("  bolt:", assembly.get_pose("bolt"))

assembly.solve()

base_pose = assembly.get_pose("base")
bolt_pose = assembly.get_pose("bolt")

print("after solve:")
print("  base:", base_pose)
print("  bolt:", bolt_pose)

expected = (10.0, 5.0, 0.0)
actual = bolt_pose[0]
error = sum((a - e) ** 2 for a, e in zip(actual, expected)) ** 0.5
print(f"bolt position error vs (10, 5, 0): {error:.2e}")

if error < 1e-6:
    print("PASS")
    sys.exit(0)
print("FAIL")
sys.exit(1)
