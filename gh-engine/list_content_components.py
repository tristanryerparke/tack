"""List Grasshopper components related to Rhino model content."""

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
        from Grasshopper import Instances

        rows = []
        for proxy in Instances.ComponentServer.ObjectProxies:
            desc = proxy.Desc
            text = "{} {} {} {} {}".format(
                getattr(desc, "Category", ""),
                getattr(desc, "SubCategory", ""),
                getattr(desc, "Name", ""),
                getattr(desc, "NickName", ""),
                getattr(desc, "Description", ""),
            ).lower()
            if any(term in text for term in ("content", "model", "rhino", "attribute", "object")):
                rows.append((
                    getattr(desc, "Category", None),
                    getattr(desc, "SubCategory", None),
                    getattr(desc, "Name", None),
                    getattr(desc, "NickName", None),
                    getattr(desc, "Description", None),
                    proxy.Guid,
                    proxy.Type.FullName if proxy.Type else None,
                ))
        for row in sorted(rows, key=lambda r: (str(r[0]), str(r[1]), str(r[2])))[:500]:
            print("COMP category={} sub={} name={} nick={} guid={} type={} desc={}".format(
                row[0], row[1], row[2], row[3], row[5], row[6], row[4]
            ))
        print("COUNT", len(rows))
        return Result.Success
    except Exception:
        traceback.print_exc()
        return Result.Failure


if __name__ == "__main__":
    from tack.watcher import run_entrypoint

    run_entrypoint(lambda: RunCommand(True), True)
