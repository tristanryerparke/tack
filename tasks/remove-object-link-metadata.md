# Store Tack links only in document metadata

Persist each relationship only in the document string-table index (`Tack` / `PlaneLinkIndex.v1`). Remove the duplicate `Tack.PlaneLinks.v1` payload from parent and child object `UserDictionary`s.

## Implementation

1. In `tack/plane_link_metadata.py`, make `save()` validate the link and write it only to the document index; remove `_set_links`, `_raw_links`, `read_links`, and `read_link` if no callers remain.
2. Make `clear()` replace the document index with an empty `links` map, without modifying object attributes.
3. In `tack/plane_link.py`, have `maintain()` use `state["link"]`. Runtime synchronization already refreshes that value from `all_links(doc)` after undo/redo.
4. Update `tests/rhino/metadata_index.py` to assert the index contents and that unrelated object user data remains untouched; remove expectations for Tack object user data.

Links remain saved with the `.3dm` and restore from the document index. Object-level link provenance and any future recovery from a damaged index are intentionally removed.
