"""Inspect Grasshopper Rhino model object parameter/data types."""

import os
import sys
import traceback

PROJECT_ROOT = os.path.dirname(os.path.dirname(__file__))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import clr
from Rhino.Commands import Result


def RunCommand(is_interactive):
    try:
        clr.AddReference("Grasshopper")
        import System
        from Grasshopper import Instances

        asm_names = set()
        for proxy in Instances.ComponentServer.ObjectProxies:
            if proxy.Type and (
                proxy.Type.FullName.startswith("Grasshopper.Rhinoceros")
                or proxy.Type.FullName.startswith("IOComponents")
            ):
                asm_names.add(proxy.Type.Assembly.FullName)
        for asm_name in sorted(asm_names):
            asm = System.Reflection.Assembly.Load(asm_name)
            print("\nASSEMBLY", asm.FullName)
            for typ in sorted(asm.GetTypes(), key=lambda t: t.FullName):
                name = typ.FullName
                if any(term in name.lower() for term in ("modelobject", "modelcontent", "content")):
                    print("TYPE", name)
                    ctors = typ.GetConstructors()
                    for ctor in ctors:
                        params = ", ".join([p.ParameterType.FullName + " " + p.Name for p in ctor.GetParameters()])
                        print("  CTOR({})".format(params))
                    props = [p for p in typ.GetProperties() if p.CanWrite or p.Name in ("Id", "ReferenceId", "Content", "Value")]
                    for prop in props[:30]:
                        print("  PROP {} type={} write={}".format(prop.Name, prop.PropertyType.FullName, prop.CanWrite))
        return Result.Success
    except Exception:
        traceback.print_exc()
        return Result.Failure


if __name__ == "__main__":
    from tack.watcher import run_entrypoint

    run_entrypoint(lambda: RunCommand(True), True)
