"""Prompt helpers for mate commands.

These functions are intentionally thin wrappers around Rhino input. They return
serializable references for mate records instead of Grasshopper objects.
"""

import Rhino
import System

from assembly.mate_records import line_axis_reference, object_reference, point_reference


class PromptCancelled(Exception):
    pass


def pick_object(prompt, *, role, geometry_filter=None):
    getter = Rhino.Input.Custom.GetObject()
    getter.SetCommandPrompt(prompt)
    if geometry_filter is not None:
        getter.GeometryFilter = geometry_filter
    result = getter.Get()
    if result != Rhino.Input.GetResult.Object:
        raise PromptCancelled(prompt)
    obj_ref = getter.Object(0)
    return object_reference(
        obj_ref.ObjectId,
        role=role,
        geometry_type=str(getattr(obj_ref.Geometry(), "ObjectType", "")),
    )


def pick_object_id(prompt, *, geometry_filter=None):
    getter = Rhino.Input.Custom.GetObject()
    getter.SetCommandPrompt(prompt)
    if geometry_filter is not None:
        getter.GeometryFilter = geometry_filter
    result = getter.Get()
    if result != Rhino.Input.GetResult.Object:
        raise PromptCancelled(prompt)
    return getter.Object(0).ObjectId


def pick_point(prompt, *, role, source=None):
    getter = Rhino.Input.Custom.GetPoint()
    getter.SetCommandPrompt(prompt)
    result = getter.Get()
    if result != Rhino.Input.GetResult.Point:
        raise PromptCancelled(prompt)
    return point_reference(getter.Point(), role=role, source=source)


def pick_axis_by_two_points(prompt_start, prompt_end, *, role, source=None):
    start_getter = Rhino.Input.Custom.GetPoint()
    start_getter.SetCommandPrompt(prompt_start)
    if start_getter.Get() != Rhino.Input.GetResult.Point:
        raise PromptCancelled(prompt_start)
    start = start_getter.Point()

    end_getter = Rhino.Input.Custom.GetPoint()
    end_getter.SetCommandPrompt(prompt_end)
    end_getter.SetBasePoint(start, True)
    end_getter.DrawLineFromPoint(start, True)
    if end_getter.Get() != Rhino.Input.GetResult.Point:
        raise PromptCancelled(prompt_end)
    end = end_getter.Point()

    if start.DistanceTo(end) <= Rhino.RhinoDoc.ActiveDoc.ModelAbsoluteTolerance:
        raise PromptCancelled("Axis points are too close together.")
    return line_axis_reference(start, end_getter.Point(), role=role, source=source)


def get_number(prompt, default_value):
    getter = Rhino.Input.Custom.GetNumber()
    getter.SetCommandPrompt(prompt)
    getter.SetDefaultNumber(float(default_value))
    result = getter.Get()
    if result != Rhino.Input.GetResult.Number:
        raise PromptCancelled(prompt)
    return float(getter.Number())


def ask_yes_no(prompt, default=False):
    default_text = "Yes" if default else "No"
    result = Rhino.UI.Dialogs.ShowMessageBox(
        prompt,
        "AssemblyGH",
        System.Windows.Forms.MessageBoxButtons.YesNo,
        System.Windows.Forms.MessageBoxIcon.Question,
        System.Windows.Forms.MessageBoxDefaultButton.Button1 if default else System.Windows.Forms.MessageBoxDefaultButton.Button2,
    )
    return str(result) == "Yes"
