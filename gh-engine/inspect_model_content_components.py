"""Inspect model-content component params and key properties by exact GUID."""

import os
import sys
import traceback

PROJECT_ROOT = os.path.dirname(os.path.dirname(__file__))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import clr
import System
from Rhino.Commands import Result

COMPONENTS = [
    ("Rhino > Objects > Model Object", "d7071c97-bc7f-4966-beba-b7110064eebf"),
    ("Rhino > Content > Content Identity", "ed9fbfde-1a0d-4469-a03f-feb54ac3e5cf"),
    ("Rhino > Content > Duplicate Content", "494d3ec5-c6b4-420e-9417-37278cf94ee2"),
    ("Rhino > Content > Content Information", "f03f9435-810e-4afa-8a9b-ed4132554730"),
    ("Params > Input > Object Details", "c7b5c66a-6360-4f5f-aa17-a918d0b1c314"),
    ("Params > Util > Get Object", "522cee36-b61e-4e5a-a581-371795cb5d21"),
    ("Rhino > Content > Content Cache", "1fae4c7a-d84a-4f04-8400-179e13193381"),
]


def _dump_component(server, label, guid_text):
    proxy = server.EmitObjectProxy(System.Guid(guid_text))
    print("\n=== {} ===".format(label))
    print("PROXY", proxy, "guid", getattr(proxy, "Guid", None), "type", proxy.Type.FullName if proxy and proxy.Type else None)
    if proxy is None:
        return
    obj = proxy.CreateInstance()
    print("TYPE", obj.GetType().FullName)
    print("NICK", getattr(obj, "NickName", None), "DESC", getattr(obj, "Description", None))
    print("PROPS")
    for prop in sorted(obj.GetType().GetProperties(), key=lambda p: p.Name):
        if prop.GetIndexParameters().Length:
            continue
        if prop.Name in ("Attributes", "Icon_24x24", "Icon_24x24_Locked", "Params"):
            continue
        try:
            value = prop.GetValue(obj, None) if prop.CanRead else "<no read>"
        except Exception as error:
            value = "<err {}>".format(error)
        if prop.CanWrite or prop.Name in ("DefaultAction", "InstanceDescription", "Message", "PrincipalParameterIndex"):
            print("  {} type={} write={} value={}".format(prop.Name, prop.PropertyType.FullName, prop.CanWrite, value))
    params = getattr(obj, "Params", None)
    if params is None:
        print("NO Params SERVER")
        return
    print("INPUTS", params.Input.Count)
    for i in range(params.Input.Count):
        p = params.Input[i]
        print("  IN[{}] type={} name={} nick={} desc={} access={} optional={}".format(
            i, p.GetType().FullName, p.Name, p.NickName, p.Description, p.Access, p.Optional
        ))
    print("OUTPUTS", params.Output.Count)
    for i in range(params.Output.Count):
        p = params.Output[i]
        print("  OUT[{}] type={} name={} nick={} desc={} access={} optional={}".format(
            i, p.GetType().FullName, p.Name, p.NickName, p.Description, p.Access, p.Optional
        ))


def RunCommand(is_interactive):
    try:
        clr.AddReference("Grasshopper")
        from Grasshopper import Instances

        for label, guid_text in COMPONENTS:
            _dump_component(Instances.ComponentServer, label, guid_text)
        return Result.Success
    except Exception:
        traceback.print_exc()
        return Result.Failure


if __name__ == "__main__":
    from tack.watcher import run_entrypoint

    run_entrypoint(lambda: RunCommand(True), True)
