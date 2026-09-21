"""Report document-object changes after every Rhino command.

Run with::

    uv run rhino-watch tack/undo_redo/test_undo_redo.py --debug --nostop

The watcher remains available after setup so native commands, including Undo and
Redo, can report through the EndCommand handler.
"""

import importlib
import os
import sys

import Rhino
import scriptcontext as sc

from run_in_rhino.rhino_env.client import SocketConnection
from run_in_rhino.rhino_env.parasite import OutputParasite

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

HANDLER_KEY = "Tack.UndoRedo.EndCommandHandler"
SNAPSHOTS_KEY = "Tack.UndoRedo.ObjectSnapshots"


def _command_name(event):
    return (
        getattr(event, "CommandEnglishName", None)
        or getattr(event, "EnglishName", None)
        or getattr(event, "CommandName", None)
        or "<unknown>"
    )


def _document(event):
    document = getattr(event, "Document", None)
    if document is not None:
        return document
    serial = getattr(event, "DocumentRuntimeSerialNumber", None)
    return (
        None if serial is None else Rhino.RhinoDoc.FromRuntimeSerialNumber(int(serial))
    )


def _label(obj):
    name = str(getattr(obj.Attributes, "Name", "") or "").strip()
    return name or str(obj.Id)


def _snapshot(doc):
    return {
        str(obj.Id): {
            "label": _label(obj),
            "serial": int(obj.RuntimeSerialNumber),
        }
        for obj in doc.Objects
        if obj is not None
    }


def _print_changes(command, before, after):
    added = [after[object_id] for object_id in after.keys() - before.keys()]
    deleted = [before[object_id] for object_id in before.keys() - after.keys()]
    changed = [
        after[object_id]
        for object_id in before.keys() & after.keys()
        if before[object_id]["serial"] != after[object_id]["serial"]
    ]

    print(
        f"{command}: {len(added)} added, {len(deleted)} deleted, {len(changed)} changed"
    )
    for entry in sorted(added, key=lambda item: item["label"].casefold()):
        print(f"  added: {entry['label']}")
    for entry in sorted(deleted, key=lambda item: item["label"].casefold()):
        print(f"  deleted: {entry['label']}")
    for entry in sorted(changed, key=lambda item: item["label"].casefold()):
        print(f"  changed: {entry['label']}")


def _check_tack_invariants(doc):
    """Run every active Tack's maintenance and report any resulting changes."""
    from tack import plane_link

    before = _snapshot(doc)
    active = list(plane_link.states(doc, create=False).values())
    failed = []
    for state in active:
        if not plane_link.maintain(doc, state):
            failed.append(state["link_id"])
    after = _snapshot(doc)
    corrected = [
        after[object_id]
        for object_id in before.keys() & after.keys()
        if before[object_id]["serial"] != after[object_id]["serial"]
    ]

    relationship_word = "relationship" if len(active) == 1 else "relationships"
    if corrected:
        print(
            f"  Tack check: {len(active)} {relationship_word}, "
            f"corrected {len(corrected)} object(s)"
        )
        for entry in sorted(corrected, key=lambda item: item["label"].casefold()):
            print(f"    corrected: {entry['label']}")
    else:
        print(f"  Tack check: {len(active)} {relationship_word}, no object correction")
    for link_id in failed:
        print(f"    failed: Tack {link_id}")
    return after


def on_end_command(sender, event):
    doc = _document(event)
    if doc is None:
        return
    snapshots = sc.sticky.setdefault(SNAPSHOTS_KEY, {})
    document_id = int(doc.RuntimeSerialNumber)
    before = snapshots.get(document_id)
    after = _snapshot(doc)

    # Setup has already sent its done message. Use a fresh connection to send
    # output from every later native command to rhino-watch --nostop.
    connection = SocketConnection()
    with OutputParasite(connection):
        if before is not None:
            _print_changes(_command_name(event), before, after)
        snapshots[document_id] = _check_tack_invariants(doc)


connection = SocketConnection()
with OutputParasite(connection, done_msg=True):
    previous_handler = sc.sticky.get(HANDLER_KEY)
    if previous_handler is not None:
        Rhino.Commands.Command.EndCommand -= previous_handler

    loaded_plane_link = importlib.import_module("tack.plane_link")
    loaded_plane_link.unsubscribe()
    sys.modules.pop("tack.plane_link", None)
    plane_link = importlib.import_module("tack.plane_link")
    plane_link.subscribe()

    sc.sticky[SNAPSHOTS_KEY] = {
        int(document.RuntimeSerialNumber): _snapshot(document)
        for document in Rhino.RhinoDoc.OpenDocuments(False)
    }
    Rhino.Commands.Command.EndCommand += on_end_command
    sc.sticky[HANDLER_KEY] = on_end_command
    print("Subscribed to Rhino.Commands.Command.EndCommand")
