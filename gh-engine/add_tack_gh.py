"""Proof-of-concept Tack engine backed by a live Grasshopper document.

Run from Rhino with:

    uv run rhino-watch gh-engine/add_tack_gh.py --debug

This is intentionally rough.  The generated GH_Document owns the geometry
update through Rhino/Grasshopper's native Content Cache component:
parent brep + index -> anchor point, child brep + index -> anchor point,
relationship vector/math, moved child Model Object, then Content Cache Push.
"""

import os
import sys
import traceback

PROJECT_ROOT = os.path.dirname(os.path.dirname(__file__))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import clr
import Rhino
import rhinoscriptsyntax as rs
import scriptcontext as sc
import System
import System.Drawing
from Rhino.Commands import Result

import tack.analysis.vertex as vertex_analysis
from tack import conduit as tack_conduit
from tack.prompting import picking

STICKY_KEY = "TackGH.ActiveLinks"
CONDUIT_KEY = "TackGH.Conduit"
IDLE_SOLVE_HANDLER_KEY = "TackGH.IdleSolveHandler"
GENERATED_DIR = os.path.join(PROJECT_ROOT, "gh-engine", "generated")
GENERATED_PROJECT_PREFIX = "TackGH POC"


class TackGHError(Exception):
    pass


def _short_id(object_id):
    return str(object_id).split("-", 1)[0]


def _load_grasshopper():
    clr.AddReference("Grasshopper")
    import Grasshopper
    from Grasshopper import Instances
    from Grasshopper.Kernel import GH_Document, GH_DocumentIO, IGH_PreviewObject
    from Grasshopper.Kernel.Parameters import Param_Brep, Param_Integer, Param_Vector
    from Grasshopper.Kernel.Special import GH_Group, GH_Panel
    from Grasshopper.Kernel.Types import GH_Brep, GH_Integer, GH_Vector
    from Grasshopper.Rhinoceros.Model import ModelObject
    from Grasshopper.Rhinoceros.Model.Params import Param_ModelObject

    try:
        Instances.AutoShowBanner = False
        Instances.AutoHideBanner = True
    except Exception:
        pass

    return {
        "Grasshopper": Grasshopper,
        "Instances": Instances,
        "GH_Document": GH_Document,
        "GH_DocumentIO": GH_DocumentIO,
        "IGH_PreviewObject": IGH_PreviewObject,
        "Param_Brep": Param_Brep,
        "Param_Integer": Param_Integer,
        "Param_Vector": Param_Vector,
        "GH_Group": GH_Group,
        "GH_Panel": GH_Panel,
        "GH_Brep": GH_Brep,
        "GH_Integer": GH_Integer,
        "GH_Vector": GH_Vector,
        "ModelObject": ModelObject,
        "Param_ModelObject": Param_ModelObject,
    }


class TackGHConduit(Rhino.Display.DisplayConduit):
    def CalculateBoundingBox(self, event):
        for parent_anchor, child_anchor in _active_display_segments(event.RhinoDoc):
            bounding_box = Rhino.Geometry.BoundingBox(parent_anchor, child_anchor)
            if bounding_box.IsValid:
                bounding_box.Inflate(1.0)
                event.IncludeBoundingBox(bounding_box)

    def CalculateBoundingBoxZoomExtents(self, event):
        self.CalculateBoundingBox(event)

    def DrawForeground(self, event):
        for parent_anchor, child_anchor in _active_display_segments(event.RhinoDoc):
            if parent_anchor.DistanceTo(child_anchor) > 0.1:
                event.Display.DrawPatternedLine(
                    parent_anchor,
                    child_anchor,
                    tack_conduit.OFFSET_LINE_COLOR,
                    tack_conduit.OFFSET_LINE_PATTERN,
                    tack_conduit.OFFSET_LINE_THICKNESS,
                )
                tack_conduit._draw_crosshair(
                    event,
                    parent_anchor,
                    tack_conduit.PARENT_COLOR,
                )
                tack_conduit._draw_crosshair(
                    event,
                    child_anchor,
                    tack_conduit.CHILD_COLOR,
                )
            else:
                tack_conduit._draw_crosshair(
                    event,
                    parent_anchor,
                    tack_conduit.CHILD_COLOR,
                )


def _active_display_segments(doc):
    if doc is None:
        return []
    links = sc.sticky.get(STICKY_KEY, {})
    segments = []
    for record in links.values():
        state = record.get("state") if isinstance(record, dict) else None
        if state is None:
            continue
        parent_anchor = resolve_brep_vertex(
            doc,
            state["parent_id"],
            state["parent_index"],
        )
        child_anchor = resolve_brep_vertex(
            doc,
            state["child_id"],
            state["child_index"],
        )
        if parent_anchor is not None and child_anchor is not None:
            segments.append((parent_anchor, child_anchor))
    return segments


def _ensure_tack_gh_conduit(doc):
    active_conduit = sc.sticky.get(CONDUIT_KEY)
    if active_conduit is None:
        active_conduit = TackGHConduit()
        sc.sticky[CONDUIT_KEY] = active_conduit
    active_conduit.Enabled = True
    if doc is not None:
        doc.Views.Redraw()
    return active_conduit


def _set_grasshopper_visible(visible):
    option = "_Show" if visible else "_Hide"
    Rhino.RhinoApp.RunScript(
        "_-Grasshopper _Window {} _Enter".format(option),
        False,
    )


def _hide_grasshopper_previews(api, ghdoc):
    for obj in ghdoc.Objects:
        _hide_preview_object(api, obj)
        params = getattr(obj, "Params", None)
        if params is None:
            continue
        for group_name in ("Input", "Output"):
            group = getattr(params, group_name, None)
            if group is None:
                continue
            for index in range(group.Count):
                _hide_preview_object(api, group[index])
    ghdoc.ForcePreview(False)


def _hide_preview_object(api, obj):
    try:
        if isinstance(obj, api["IGH_PreviewObject"]):
            obj.Hidden = True
            return
    except Exception:
        pass
    try:
        obj.Hidden = True
    except Exception:
        pass


def _set_pivot(gh_object, x, y):
    gh_object.CreateAttributes()
    gh_object.Attributes.Pivot = System.Drawing.PointF(float(x), float(y))


def _add_panel(api, ghdoc, text, x, y):
    panel = api["GH_Panel"]()
    panel.UserText = text
    _set_pivot(panel, x, y)
    ghdoc.AddObject(panel, False)
    return panel


def _add_group(api, ghdoc, title, objects):
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


def _safe_set_persistent_data(param, goo, label):
    """Best-effort persistent data assignment across GH versions."""
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
    print("[TackGH] could not set persistent data on {}".format(label))
    return False


def _add_brep_param(api, ghdoc, object_id, x, y, group_title):
    param = api["Param_Brep"]()
    param.Description = "Referenced Rhino object {}".format(object_id)
    _set_pivot(param, x, y)
    _safe_set_persistent_data(
        param,
        api["GH_Brep"](System.Guid(str(object_id))),
        group_title,
    )
    ghdoc.AddObject(param, False)
    _add_group(api, ghdoc, group_title, [param])
    return param


def _add_int_param(api, ghdoc, value, x, y, group_title):
    param = api["Param_Integer"]()
    _set_pivot(param, x, y)
    _safe_set_persistent_data(param, api["GH_Integer"](int(value)), group_title)
    ghdoc.AddObject(param, False)
    _add_group(api, ghdoc, group_title, [param])
    return param


def _add_vector_param(api, ghdoc, value, x, y, group_title):
    param = api["Param_Vector"]()
    _set_pivot(param, x, y)
    _safe_set_persistent_data(param, api["GH_Vector"](value), group_title)
    ghdoc.AddObject(param, False)
    _add_group(api, ghdoc, group_title, [param])
    return param


def _add_model_object_param(api, ghdoc, object_id, x, y, group_title):
    param = api["Param_ModelObject"]()
    param.Description = "Referenced Rhino model object {}".format(object_id)
    _set_pivot(param, x, y)
    _safe_set_persistent_data(
        param,
        api["ModelObject"](System.Guid(str(object_id))),
        group_title,
    )
    ghdoc.AddObject(param, False)
    _add_group(api, ghdoc, group_title, [param])
    return param


def _emit_guid(api, ghdoc, component_guid, x, y, group_title=None):
    proxy = api["Instances"].ComponentServer.EmitObjectProxy(
        System.Guid(str(component_guid))
    )
    if proxy is None:
        _add_panel(
            api,
            ghdoc,
            "Missing native GH component:\n{}".format(component_guid),
            x,
            y,
        )
        print("[TackGH] missing native GH component: {}".format(component_guid))
        return None

    obj = proxy.CreateInstance()
    _set_pivot(obj, x, y)
    ghdoc.AddObject(obj, False)
    if group_title:
        _add_group(api, ghdoc, group_title, [obj])
    return obj


def _make_content_cache_action(action_name="Push"):
    clr.AddReference("IOComponents")
    from IOComponents.Rhinoceros.Cache import ModelAction

    action_type = System.Enum.Parse(ModelAction.Type, action_name)
    flags = (
        System.Reflection.BindingFlags.Instance
        | System.Reflection.BindingFlags.Public
        | System.Reflection.BindingFlags.NonPublic
    )
    action = ModelAction()
    attrs_field = action.GetType().GetField("_Attributes", flags)
    attrs = attrs_field.GetValue(action)
    attrs.GetType().GetField("Type", flags).SetValue(attrs, action_type)
    attrs_field.SetValue(action, attrs)
    return action


def _add_content_cache_push_input(content_cache):
    if content_cache is None:
        return None
    from Grasshopper.Kernel import GH_ParameterSide

    for index in range(content_cache.Params.Input.Count):
        if content_cache.Params.Input[index].Name == "Action":
            action_param = content_cache.Params.Input[index]
            break
    else:
        action_param = content_cache.CreateParameter(GH_ParameterSide.Input, 1)
        content_cache.Params.RegisterInputParam(action_param, 1)
        content_cache.VariableParameterMaintenance()
        content_cache.Params.OnParametersChanged()

    _safe_set_persistent_data(action_param, _make_content_cache_action("Push"), "Content Cache Push action")
    return action_param


def _emit_named(api, ghdoc, name, x, y, group_title=None):
    proxy = api["Instances"].ComponentServer.FindObjectByName(
        name,
        True,
        True,
    )
    if proxy is None:
        _add_panel(
            api,
            ghdoc,
            "Missing native GH component:\n{}".format(name),
            x,
            y,
        )
        print("[TackGH] missing native GH component: {}".format(name))
        return None

    obj = proxy.CreateInstance()
    _set_pivot(obj, x, y)
    ghdoc.AddObject(obj, False)
    if group_title:
        _add_group(api, ghdoc, group_title, [obj])
    return obj


def _output_param(source, index=0):
    params = getattr(source, "Params", None)
    if params is not None and params.Output.Count > index:
        return params.Output[index]
    return source


def _input_param(target, index=0):
    params = getattr(target, "Params", None)
    if params is not None and params.Input.Count > index:
        return params.Input[index]
    return None


def _wire(source, source_index, target, target_index):
    if source is None or target is None:
        return False
    source_param = _output_param(source, source_index)
    target_param = _input_param(target, target_index)
    if source_param is None or target_param is None:
        return False
    try:
        target_param.AddSource(source_param)
        return True
    except Exception as error:
        print("[TackGH] wire failed: {}".format(error))
        return False


def _brep_from_object(obj):
    if obj is None:
        return None
    geometry = obj.Geometry
    if isinstance(geometry, Rhino.Geometry.Brep):
        return geometry
    if isinstance(geometry, Rhino.Geometry.Extrusion):
        return geometry.ToBrep()
    if getattr(geometry, "HasBrepForm", False):
        try:
            return Rhino.Geometry.Brep.TryConvertBrep(geometry)
        except Exception:
            return None
    return None


def resolve_brep_vertex(doc, object_id, index):
    obj = doc.Objects.Find(System.Guid(str(object_id)))
    brep = _brep_from_object(obj)
    if brep is None:
        return None
    index = int(index)
    if index < 0 or index >= brep.Vertices.Count:
        return None
    return Rhino.Geometry.Point3d(brep.Vertices[index].Location)


def _duplicate_child_geometry_for_replace(child_obj):
    geometry = child_obj.Geometry
    if isinstance(geometry, Rhino.Geometry.Extrusion):
        return geometry.ToBrep()
    duplicate = geometry.Duplicate()
    if duplicate is None:
        return None
    return duplicate


def _object_runtime_serial(doc, object_id):
    obj = doc.Objects.Find(System.Guid(str(object_id)))
    if obj is None:
        return None
    return int(obj.RuntimeSerialNumber)


def _refresh_runtime_serials(doc, state):
    state["parent_runtime_serial"] = _object_runtime_serial(
        doc,
        state["parent_id"],
    )
    state["child_runtime_serial"] = _object_runtime_serial(
        doc,
        state["child_id"],
    )


def _active_link_changed(doc, state):
    for role in ("parent", "child"):
        key = role + "_runtime_serial"
        current = _object_runtime_serial(doc, state[role + "_id"])
        if current != state.get(key):
            return True
    return False


def _solve_changed_active_links(doc):
    links = sc.sticky.get(STICKY_KEY, {})
    solved = 0
    for record in list(links.values()):
        state = record.get("state") if isinstance(record, dict) else None
        ghdoc = record.get("ghdoc") if isinstance(record, dict) else None
        if state is None or ghdoc is None or state.get("busy"):
            continue
        if not _active_link_changed(doc, state):
            continue
        ghdoc.ExpireSolution()
        ghdoc.NewSolution(True)
        _refresh_runtime_serials(doc, state)
        solved += 1
    if solved:
        doc.Views.Redraw()
        print("[TackGH] EndCommand expired {} hidden GH link(s)".format(solved))


def _schedule_changed_active_links_solve(doc):
    if doc is None or sc.sticky.get(IDLE_SOLVE_HANDLER_KEY) is not None:
        return

    def on_idle(sender, event):
        try:
            Rhino.RhinoApp.Idle -= on_idle
        except Exception:
            pass
        sc.sticky.pop(IDLE_SOLVE_HANDLER_KEY, None)
        active_doc = Rhino.RhinoDoc.ActiveDoc or doc
        if active_doc is not None:
            _solve_changed_active_links(active_doc)

    sc.sticky[IDLE_SOLVE_HANDLER_KEY] = on_idle
    Rhino.RhinoApp.Idle += on_idle


def _end_command_handler(sender, event):
    _schedule_changed_active_links_solve(Rhino.RhinoDoc.ActiveDoc)


def _close_document_handler(sender, event):
    doc = getattr(event, "Document", None)
    if doc is not None:
        conduit = sc.sticky.pop(CONDUIT_KEY, None)
        if conduit is not None:
            conduit.Enabled = False


def _subscribe_hidden_gh_updates():
    handlers_key = STICKY_KEY + ".Handlers"
    if sc.sticky.get(handlers_key):
        return
    Rhino.Commands.Command.EndCommand += _end_command_handler
    Rhino.RhinoDoc.CloseDocument += _close_document_handler
    sc.sticky[handlers_key] = (_end_command_handler, _close_document_handler)


def _iter_grasshopper_documents(document_server):
    try:
        return list(document_server)
    except Exception:
        pass

    for count_name in ("DocumentCount", "Count"):
        try:
            count = int(getattr(document_server, count_name))
        except Exception:
            continue
        documents = []
        for index in range(count):
            try:
                documents.append(document_server[index])
                continue
            except Exception:
                pass
            try:
                documents.append(document_server.Document(index))
            except Exception:
                pass
        return documents

    return []


def _is_tack_gh_document(ghdoc):
    names = []
    for target in (ghdoc, getattr(ghdoc, "Properties", None)):
        if target is None:
            continue
        for property_name in ("DisplayName", "FileNameProxy", "FilePath", "ProjectFileName"):
            try:
                value = getattr(target, property_name)
            except Exception:
                continue
            if value:
                names.append(str(value))
    if any(GENERATED_PROJECT_PREFIX in name or "_TackGH_" in name for name in names):
        return True

    try:
        for obj in ghdoc.Objects:
            if obj.GetType().FullName == "Grasshopper.Kernel.Special.GH_Group":
                title = getattr(obj, "NickName", "") or ""
                if title.startswith(
                    (
                        "Parent Brep",
                        "Child Brep",
                        "Child Model Object for Content Cache",
                        "Content Cache Push",
                    )
                ):
                    return True
    except Exception:
        pass
    return False


def _mark_grasshopper_document_unmodified(ghdoc):
    """Prevent Grasshopper from asking to save generated throwaway docs."""
    for target in (ghdoc, getattr(ghdoc, "Properties", None)):
        if target is None:
            continue
        for property_name in ("Modified", "IsModified"):
            try:
                setattr(target, property_name, False)
            except Exception:
                pass


def _remove_grasshopper_document(document_server, ghdoc):
    if ghdoc is None:
        return False
    _mark_grasshopper_document_unmodified(ghdoc)
    try:
        document_server.RemoveDocument(ghdoc)
    except Exception:
        pass
    try:
        ghdoc.Dispose()
    except Exception:
        pass
    return True


def reset_tack_gh(doc=None, hide_grasshopper=True):
    api = _load_grasshopper()
    document_server = api["Instances"].DocumentServer
    links = sc.sticky.pop(STICKY_KEY, {})
    removed_docs = 0
    removed_ids = set()
    for record in list(links.values()):
        ghdoc = record.get("ghdoc") if isinstance(record, dict) else None
        handler = record.get("solution_end_handler") if isinstance(record, dict) else None
        if ghdoc is None:
            continue
        if handler is not None:
            try:
                ghdoc.SolutionEnd -= handler
            except Exception:
                pass
        try:
            removed_ids.add(str(ghdoc.DocumentID))
        except Exception:
            pass
        if _remove_grasshopper_document(document_server, ghdoc):
            removed_docs += 1

    for ghdoc in _iter_grasshopper_documents(document_server):
        try:
            document_id = str(ghdoc.DocumentID)
        except Exception:
            document_id = ""
        if document_id in removed_ids or not _is_tack_gh_document(ghdoc):
            continue
        if _remove_grasshopper_document(document_server, ghdoc):
            removed_docs += 1

    handlers_key = STICKY_KEY + ".Handlers"
    idle_handler = sc.sticky.pop(IDLE_SOLVE_HANDLER_KEY, None)
    if idle_handler is not None:
        try:
            Rhino.RhinoApp.Idle -= idle_handler
        except Exception:
            pass

    stored_handlers = sc.sticky.pop(handlers_key, ())
    if len(stored_handlers) >= 1:
        try:
            Rhino.Commands.Command.EndCommand -= stored_handlers[0]
        except Exception:
            pass
    if len(stored_handlers) >= 2:
        try:
            Rhino.RhinoDoc.CloseDocument -= stored_handlers[1]
        except Exception:
            pass

    active_conduit = sc.sticky.pop(CONDUIT_KEY, None)
    if active_conduit is not None:
        active_conduit.Enabled = False

    if hide_grasshopper:
        try:
            _set_grasshopper_visible(False)
        except Exception:
            pass
    if doc is not None:
        doc.Views.Redraw()
    print("[TackGH reset] removed {} generated GH document(s)".format(removed_docs))
    return removed_docs


def apply_link_state(rhino_doc, state):
    if state.get("busy"):
        return False

    parent_id = state["parent_id"]
    child_id = state["child_id"]
    parent_point = resolve_brep_vertex(
        rhino_doc,
        parent_id,
        state["parent_index"],
    )
    child_point = resolve_brep_vertex(
        rhino_doc,
        child_id,
        state["child_index"],
    )
    child_obj = rhino_doc.Objects.Find(System.Guid(str(child_id)))

    if parent_point is None or child_point is None or child_obj is None:
        print("[TackGH] skipped solve; parent/child/index could not resolve")
        return False

    relation = Rhino.Geometry.Vector3d(*state["relation"])
    target_child_point = parent_point + relation
    correction_vector = target_child_point - child_point
    if correction_vector.IsTiny(rhino_doc.ModelAbsoluteTolerance):
        return True

    replacement = _duplicate_child_geometry_for_replace(child_obj)
    if replacement is None:
        print("[TackGH] skipped solve; child geometry could not duplicate")
        return False

    replacement.Transform(Rhino.Geometry.Transform.Translation(correction_vector))
    state["busy"] = True
    try:
        if not rhino_doc.Objects.Replace(System.Guid(str(child_id)), replacement):
            print("[TackGH] child replace failed")
            return False
        state["solve_count"] = state.get("solve_count", 0) + 1
        _refresh_runtime_serials(rhino_doc, state)
        print(
            "[TackGH] content cache pushed child={} correction=({:.3f}, {:.3f}, {:.3f})".format(
                _short_id(child_id),
                correction_vector.X,
                correction_vector.Y,
                correction_vector.Z,
            )
        )
        rhino_doc.Views.Redraw()
        return True
    finally:
        state["busy"] = False


def _add_graph(api, ghdoc, parent_id, child_id, parent_index, child_index, relation):
    """Create a readable GH canvas for the POC.

    Components keep their default names.  Per-component information is stored
    on one-component groups so the canvas stays inspectable without mutating
    native component labels.
    """
    parent_brep = _add_brep_param(
        api,
        ghdoc,
        parent_id,
        20,
        20,
        "Parent Brep: {}".format(_short_id(parent_id)),
    )
    parent_idx = _add_int_param(
        api,
        ghdoc,
        parent_index,
        20,
        125,
        "Parent vertex index: {}".format(parent_index),
    )
    child_brep = _add_brep_param(
        api,
        ghdoc,
        child_id,
        20,
        285,
        "Child Brep: {}".format(_short_id(child_id)),
    )
    child_model_object = _add_model_object_param(
        api,
        ghdoc,
        child_id,
        20,
        650,
        "Child Model Object for Content Cache: {}".format(_short_id(child_id)),
    )
    child_idx = _add_int_param(
        api,
        ghdoc,
        child_index,
        20,
        390,
        "Child vertex index: {}".format(child_index),
    )
    stored_vector = _add_vector_param(
        api,
        ghdoc,
        relation,
        20,
        525,
        "Stored initial vector: ({:.3f}, {:.3f}, {:.3f})".format(
            relation.X,
            relation.Y,
            relation.Z,
        ),
    )

    p_debrep = _emit_named(api, ghdoc, "Deconstruct Brep", 260, 20, "Parent: deconstruct Brep")
    p_item = _emit_named(api, ghdoc, "List Item", 500, 20, "Parent: list item from vertices")
    c_debrep = _emit_named(api, ghdoc, "Deconstruct Brep", 260, 285, "Child: deconstruct Brep")
    c_item = _emit_named(api, ghdoc, "List Item", 500, 285, "Child: list item from vertices")
    target_point = _emit_named(api, ghdoc, "Move", 740, 120, "Target child anchor = parent anchor + stored vector")
    correction = _emit_named(api, ghdoc, "Vector 2Pt", 980, 185, "Correction vector = child anchor -> target anchor")
    moved_child = _emit_named(api, ghdoc, "Move", 1220, 285, "Move child geometry by correction")
    model_object = _emit_guid(
        api,
        ghdoc,
        "d7071c97-bc7f-4966-beba-b7110064eebf",
        1480,
        285,
        "Model Object combines child identity with moved geometry",
    )
    content_cache = _emit_guid(
        api,
        ghdoc,
        "1fae4c7a-d84a-4f04-8400-179e13193381",
        1740,
        285,
        "Content Cache Push writes child geometry",
    )
    _add_content_cache_push_input(content_cache)

    _wire(parent_brep, 0, p_debrep, 0)
    _wire(p_debrep, 2, p_item, 0)
    _wire(parent_idx, 0, p_item, 1)
    _wire(child_brep, 0, c_debrep, 0)
    _wire(c_debrep, 2, c_item, 0)
    _wire(child_idx, 0, c_item, 1)
    _wire(p_item, 0, target_point, 0)
    _wire(stored_vector, 0, target_point, 1)
    _wire(c_item, 0, correction, 0)
    _wire(target_point, 0, correction, 1)
    _wire(child_brep, 0, moved_child, 0)
    _wire(correction, 0, moved_child, 1)
    _wire(child_model_object, 0, model_object, 0)
    _wire(moved_child, 0, model_object, 1)
    _wire(model_object, 0, content_cache, 0)

    note = _add_panel(
        api,
        ghdoc,
        "Native Content Cache owns child write-back.\nPython only creates/expires the hidden GH document.",
        1740,
        60,
    )
    _add_group(api, ghdoc, "Implementation note", [note])


def _safe_filename_part(value):
    invalid = set(System.IO.Path.GetInvalidFileNameChars())
    text = str(value or "").strip()
    cleaned = "".join("_" if character in invalid else character for character in text)
    return cleaned or "untitled"


def _generated_definition_path(rhino_doc, ghdoc):
    rhino_path = getattr(rhino_doc, "Path", None) if rhino_doc is not None else None
    if rhino_path:
        directory = os.path.dirname(str(rhino_path))
        base_name = os.path.splitext(os.path.basename(str(rhino_path)))[0]
    else:
        directory = GENERATED_DIR
        base_name = "unsaved_rhino_document"

    if not os.path.isdir(directory):
        os.makedirs(directory)

    try:
        document_id = _short_id(ghdoc.DocumentID)
    except Exception:
        document_id = "generated"
    filename = "{}_TackGH_{}.ghx".format(
        _safe_filename_part(base_name),
        _safe_filename_part(document_id),
    )
    return os.path.join(directory, filename)


def _bind_grasshopper_document_path(ghdoc, path):
    try:
        ghdoc.FilePath = path
    except Exception:
        pass
    try:
        ghdoc.Properties.ProjectFileName = os.path.basename(path)
    except Exception:
        pass


def _save_generated(api, ghdoc, rhino_doc=None):
    path = _generated_definition_path(rhino_doc, ghdoc)
    io = api["GH_DocumentIO"](ghdoc)
    if io.SaveQuiet(path):
        _bind_grasshopper_document_path(ghdoc, path)
        _mark_grasshopper_document_unmodified(ghdoc)
        print("[TackGH] saved generated definition: {}".format(path))
    else:
        print("[TackGH] could not save generated definition: {}".format(path))
    return path


def create_tack_gh_link(
    rhino_doc,
    parent_id,
    child_id,
    parent_index,
    child_index,
    *,
    show_grasshopper=False,
    save_definition=True,
):
    api = _load_grasshopper()
    parent_point = resolve_brep_vertex(rhino_doc, parent_id, parent_index)
    child_point = resolve_brep_vertex(rhino_doc, child_id, child_index)
    if parent_point is None or child_point is None:
        raise TackGHError("Parent or child vertex index could not resolve.")

    relation = child_point - parent_point
    ghdoc = api["GH_Document"]()
    ghdoc.Enabled = True
    ghdoc.ActiveDoc = True
    ghdoc.Properties.ProjectFileName = "{} {} -> {}".format(
        GENERATED_PROJECT_PREFIX,
        _short_id(parent_id),
        _short_id(child_id),
    )
    _add_graph(api, ghdoc, parent_id, child_id, parent_index, child_index, relation)
    _hide_grasshopper_previews(api, ghdoc)

    state = {
        "parent_id": str(parent_id),
        "child_id": str(child_id),
        "parent_index": int(parent_index),
        "child_index": int(child_index),
        "relation": (relation.X, relation.Y, relation.Z),
        "busy": False,
        "solve_count": 0,
    }
    _refresh_runtime_serials(rhino_doc, state)

    api["Instances"].DocumentServer.AddDocument(ghdoc)
    api["Instances"].DocumentServer.PromoteDocument(ghdoc)

    sticky = sc.sticky.setdefault(STICKY_KEY, {})
    link_key = "{}:{}:{}:{}".format(parent_id, parent_index, child_id, child_index)
    sticky[link_key] = {
        "ghdoc": ghdoc,
        "state": state,
        "solution_end_handler": None,
    }

    _ensure_tack_gh_conduit(rhino_doc)
    _subscribe_hidden_gh_updates()

    path = _save_generated(api, ghdoc, rhino_doc) if save_definition else None
    if show_grasshopper:
        _set_grasshopper_visible(True)

    ghdoc.NewSolution(True)
    print(
        "[TackGH] active GH link parent={} child={} parent_index={} child_index={}".format(
            _short_id(parent_id),
            _short_id(child_id),
            parent_index,
            child_index,
        )
    )
    return ghdoc, state, path


def _pick_brep_vertex_anchor(doc, object_id, role):
    obj = doc.Objects.Find(object_id)
    if obj is None:
        return None
    if not vertex_analysis.supports_vertex_anchors(obj.Geometry):
        print("Select a Brep/Extrusion object for the {}.".format(role))
        return None
    locked_ids = picking.lock_other_objects(doc, obj.Id)
    try:
        anchors = vertex_analysis.anchors(obj)
        return picking.pick_anchor(
            obj,
            vertex_analysis.ANCHOR_TYPE,
            anchors,
            [],
            "Pick a Brep vertex anchor on the {}".format(role),
        )
    finally:
        picking.unlock_objects(locked_ids)
        doc.Views.Redraw()


def pick_link(doc):
    parent_id = picking.pick_object(doc, "Select parent Brep/box for TackGH")
    if not parent_id:
        return None
    parent_anchor = _pick_brep_vertex_anchor(doc, parent_id, "parent")
    if parent_anchor is None:
        return None

    parent_was_locked = rs.IsObjectLocked(parent_id)
    if not parent_was_locked:
        rs.LockObject(parent_id)
    try:
        child_id = picking.pick_object(doc, "Select child Brep/box for TackGH")
    finally:
        if not parent_was_locked:
            rs.UnlockObject(parent_id)

    if not child_id or str(child_id).lower() == str(parent_id).lower():
        print("Select a different child object.")
        return None
    child_anchor = _pick_brep_vertex_anchor(doc, child_id, "child")
    if child_anchor is None:
        return None

    _, parent_index, _ = parent_anchor
    _, child_index, _ = child_anchor
    return parent_id, child_id, int(parent_index), int(child_index)


def RunCommand(is_interactive):
    doc = Rhino.RhinoDoc.ActiveDoc
    if doc is None:
        return Result.Cancel

    picked = pick_link(doc)
    if picked is None:
        return Result.Cancel

    try:
        create_tack_gh_link(doc, *picked)
        return Result.Success
    except Exception:
        traceback.print_exc()
        return Result.Failure


if __name__ == "__main__":
    from tack.watcher import run_entrypoint

    run_entrypoint(lambda: RunCommand(True), True)
