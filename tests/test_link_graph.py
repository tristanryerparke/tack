from tack.link_graph import would_create_cycle


def test_three_object_tack_loop_is_rejected():
    links = [
        {"parent_id": "object-a", "child_id": "object-b"},
        {"parent_id": "object-b", "child_id": "object-c"},
    ]

    assert would_create_cycle(links, "object-c", "object-a")
    assert not would_create_cycle(links, "object-a", "object-c")
