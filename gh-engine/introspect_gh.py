import clr
import traceback


def _try_add(name):
    try:
        clr.AddReference(name)
        print("ADDREF OK", name)
    except Exception as error:
        print("ADDREF FAIL", name, repr(error))


def RunCommand(is_interactive):
    for name in ("Grasshopper", "GhPython", "GH_IO"):
        _try_add(name)

    try:
        import Grasshopper
        from Grasshopper import Instances

        print("Grasshopper Instances OK")
        server = Instances.ComponentServer
        print("ComponentServer", server)
        names = []
        for proxy in server.ObjectProxies:
            desc = proxy.Desc
            name = getattr(desc, "Name", None)
            category = getattr(desc, "Category", None)
            subcategory = getattr(desc, "SubCategory", None)
            if name and any(term.lower() in name.lower() for term in ("content", "cache", "python", "script", "brep", "move", "deconstruct")):
                names.append((category, subcategory, name, proxy.Guid))
        for item in sorted(names, key=lambda row: (str(row[0]), str(row[1]), str(row[2])))[:200]:
            print("PROXY", item[0], "/", item[1], "/", item[2], "/", item[3])
        print("PROXY COUNT", len(names))
    except Exception:
        traceback.print_exc()

    try:
        import GhPython
        print("GhPython module", GhPython)
        import GhPython.Component as C
        print("GhPython.Component members", [name for name in dir(C) if "Python" in name or "Component" in name or "Script" in name][:100])
    except Exception:
        traceback.print_exc()


if __name__ == "__main__":
    RunCommand(True)
