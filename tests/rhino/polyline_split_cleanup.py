import scriptcontext as sc

from common import TEST_OBJECT_KEY
from common import tack_modules


STATE_KEY = "Tack.IntegrationTest.PolylineSplit"


def _is_marked(obj):
    try:
        return bool(obj.Attributes.UserDictionary[TEST_OBJECT_KEY])
    except Exception:
        return False


def cleanup():
    handlers, metadata, runtime, _ = tack_modules()
    doc = sc.doc
    handlers.unsubscribe()
    runtime.stop_runtime(doc)
    sc.sticky.pop(STATE_KEY, None)

    deleted = 0
    for obj in list(doc.Objects):
        if obj is not None and _is_marked(obj):
            if doc.Objects.Delete(obj.Id, True):
                deleted += 1

    restored = 0
    for saved_link in metadata.all_links(doc):
        if runtime.start_runtime(
            doc,
            saved_link["parent_id"],
            saved_link["child_id"],
            saved_link["link_id"],
        ):
            restored += 1
    handlers.subscribe()
    doc.Views.Redraw()
    print(
        "Polyline split cleanup deleted={} restored={}".format(
            deleted,
            restored,
        )
    )


cleanup()
