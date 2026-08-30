import os
import sys
import traceback

import Rhino

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from tack import plane_link
from tack import plane_link_metadata


def restore_open_documents():
    open_documents = list(Rhino.RhinoDoc.OpenDocuments(False))
    Rhino.RhinoApp.WriteLine(
        "Tack restore: checking {} open document(s).".format(
            len(open_documents)
        )
    )
    relationship_count = 0
    document_count = 0
    for doc in open_documents:
        links = plane_link_metadata.all_links(doc)
        Rhino.RhinoApp.WriteLine(
            "Tack restore: {!r} contains {} saved relationship(s).".format(
                doc.Path,
                len(links),
            )
        )
        if not links:
            continue
        restored = plane_link.restore_document(doc)
        Rhino.RhinoApp.WriteLine(
            "Tack restore: restored {} relationship(s) in {!r}.".format(
                restored,
                doc.Path,
            )
        )
        if restored:
            document_count += 1
            relationship_count += restored

    if relationship_count:
        Rhino.RhinoApp.WriteLine(
            "Restored {} analytic-plane Tack relationship(s) in {} document(s).".format(
                relationship_count,
                document_count,
            )
        )


try:
    restore_open_documents()
except Exception:
    Rhino.RhinoApp.WriteLine(
        "Analytic-plane Tack restore failed:\n{}".format(
            traceback.format_exc()
        )
    )
    raise
