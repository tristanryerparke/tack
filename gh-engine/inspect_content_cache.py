"""Inspect Rhino's Content Cache Grasshopper component runtime API."""

import os
import sys
import traceback

PROJECT_ROOT = os.path.dirname(os.path.dirname(__file__))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import clr
import Rhino
from Rhino.Commands import Result


def _public_names(obj):
    names = []
    for name in dir(obj):
        if name.startswith("_"):
            continue
        names.append(name)
    return names


def _dump_param(param, prefix):
    print("{} type={} name={} nickname={} description={} access={} optional={} source_count={}".format(
        prefix,
        param.GetType().FullName,
        getattr(param, "Name", None),
        getattr(param, "NickName", None),
        getattr(param, "Description", None),
        getattr(param, "Access", None),
        getattr(param, "Optional", None),
        getattr(getattr(param, "Sources", None), "Count", None),
    ))


def _dump_dotnet_members(obj):
    typ = obj.GetType()
    print("TYPE", typ.FullName)
    print("ASSEMBLY", typ.Assembly.FullName)
    print("BASE", typ.BaseType.FullName if typ.BaseType else None)

    print("PROPERTIES")
    for prop in sorted(typ.GetProperties(), key=lambda p: p.Name):
        try:
            can_read = prop.CanRead
            can_write = prop.CanWrite
            value = None
            if can_read and prop.GetIndexParameters().Length == 0:
                try:
                    value = prop.GetValue(obj, None)
                except Exception as error:
                    value = "<read error {}>".format(error)
            print("  {} type={} read={} write={} value={}".format(
                prop.Name,
                prop.PropertyType.FullName,
                can_read,
                can_write,
                value,
            ))
        except Exception as error:
            print("  PROP ERR", prop.Name, error)

    print("FIELDS")
    for field in sorted(typ.GetFields(), key=lambda f: f.Name):
        try:
            print("  {} type={} value={}".format(
                field.Name,
                field.FieldType.FullName,
                field.GetValue(obj),
            ))
        except Exception as error:
            print("  FIELD ERR", field.Name, error)

    print("METHODS")
    method_rows = []
    for method in typ.GetMethods():
        if method.IsSpecialName:
            continue
        if method.DeclaringType is not None and method.DeclaringType.FullName.startswith("System."):
            continue
        params = ", ".join([p.ParameterType.Name + " " + p.Name for p in method.GetParameters()])
        method_rows.append("  {}({}) -> {}".format(method.Name, params, method.ReturnType.Name))
    for row in sorted(set(method_rows)):
        print(row)


def RunCommand(is_interactive):
    try:
        clr.AddReference("Grasshopper")
        import Grasshopper
        from Grasshopper import Instances
        from Grasshopper.Kernel import GH_Document
        from GH_IO.Serialization import GH_LooseChunk

        proxy = Instances.ComponentServer.FindObjectByName("Content Cache", True, True)
        print("PROXY", proxy, "guid", getattr(proxy, "Guid", None), "desc", getattr(proxy, "Desc", None))
        if proxy is None:
            return Result.Failure

        obj = proxy.CreateInstance()
        _dump_dotnet_members(obj)

        params = getattr(obj, "Params", None)
        if params is not None:
            print("INPUTS", params.Input.Count)
            for i in range(params.Input.Count):
                _dump_param(params.Input[i], "  IN[{}]".format(i))
            print("OUTPUTS", params.Output.Count)
            for i in range(params.Output.Count):
                _dump_param(params.Output[i], "  OUT[{}]".format(i))

        ghdoc = GH_Document()
        ghdoc.AddObject(obj, False)
        writer = GH_LooseChunk("archive")
        ok = ghdoc.Write(writer)
        print("WRITE OK", ok)
        print("WRITER TYPE", writer.GetType().FullName)
        print("WRITER MEMBERS", [name for name in _public_names(writer) if "Chunk" in name or "Item" in name or "String" in name][:80])
        print("DOC OBJECT COUNT", ghdoc.ObjectCount)
        ghdoc.Dispose()
        return Result.Success
    except Exception:
        traceback.print_exc()
        return Result.Failure


if __name__ == "__main__":
    from tack.watcher import run_entrypoint

    run_entrypoint(lambda: RunCommand(True), True)
