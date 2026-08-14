"""Small helpers for programmatically building Grasshopper definitions."""

import System
import System.Drawing


class ComponentIOError(Exception):
    pass


def set_pivot(gh_object, x, y):
    gh_object.CreateAttributes()
    gh_object.Attributes.Pivot = System.Drawing.PointF(float(x), float(y))


def safe_set_persistent_data(param, goo, label=None):
    try:
        param.PersistentData.Clear()
    except Exception:
        pass

    attempts = (
        lambda: param.PersistentData.Append(goo),
        lambda: param.AddPersistentData(goo),
        lambda: param.SetPersistentData(goo),
    )
    for attempt in attempts:
        try:
            attempt()
            param.ExpireSolution(False)
            return True
        except Exception:
            continue
    if label:
        print("[AssemblyGH] could not set persistent data on {}".format(label))
    return False


def emit_named(api, ghdoc, name, x, y, group_title=None):
    proxy = api["Instances"].ComponentServer.FindObjectByName(name, True, True)
    if proxy is None:
        raise ComponentIOError("Missing native GH component: {}".format(name))
    obj = proxy.CreateInstance()
    set_pivot(obj, x, y)
    ghdoc.AddObject(obj, False)
    if group_title:
        add_group(api, ghdoc, group_title, [obj])
    return obj


def emit_guid(api, ghdoc, component_guid, x, y, group_title=None):
    proxy = api["Instances"].ComponentServer.EmitObjectProxy(System.Guid(str(component_guid)))
    if proxy is None:
        raise ComponentIOError("Missing native GH component: {}".format(component_guid))
    obj = proxy.CreateInstance()
    set_pivot(obj, x, y)
    ghdoc.AddObject(obj, False)
    if group_title:
        add_group(api, ghdoc, group_title, [obj])
    return obj


def output_param(source, index=0):
    params = getattr(source, "Params", None)
    if params is not None and params.Output.Count > index:
        return params.Output[index]
    return source


def input_param(target, index=0):
    params = getattr(target, "Params", None)
    if params is not None and params.Input.Count > index:
        return params.Input[index]
    return target


def wire(source, source_index, target, target_index):
    if source is None or target is None:
        return False
    source_param = output_param(source, source_index)
    target_param = input_param(target, target_index)
    if source_param is None or target_param is None:
        return False
    target_param.AddSource(source_param)
    return True


def add_panel(api, ghdoc, text, x, y):
    panel = api["GH_Panel"]()
    panel.UserText = text
    set_pivot(panel, x, y)
    ghdoc.AddObject(panel, False)
    return panel


def add_group(api, ghdoc, title, objects):
    group = api["GH_Group"]()
    group.NickName = title
    for obj in objects:
        if obj is None:
            continue
        try:
            group.AddObject(obj.InstanceGuid)
        except Exception:
            pass
    try:
        group.Colour = System.Drawing.Color.FromArgb(60, 90, 160, 220)
    except Exception:
        pass
    group.CreateAttributes()
    ghdoc.AddObject(group, False)
    return group


def clear_ghdoc(ghdoc):
    objects = list(ghdoc.Objects)
    for obj in objects:
        try:
            ghdoc.RemoveObject(obj, False)
        except Exception:
            pass
