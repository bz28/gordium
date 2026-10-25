"""Only the offending part is coloured (Ben, 2026-10-21): what the viewport draws for a coloured block, and the
legend that explains it. The blocks themselves (per building, a roof's ridge) are pinned in test_present.py."""

from design_checker import rhino_logic as logic


def test_a_block_draws_the_buildings_own_part_inside_it():
    assert logic.offending_pieces(["the cantilever"], "the block") == ["the cantilever"]
    assert logic.offending_pieces(["a", None, "b"], "the block") == ["a", "b"]


def test_a_failed_intersection_still_colours_the_block_never_nothing():
    # Rhino's boolean gives None when it fails, an empty list when it finds nothing (a block instance or a mesh
    # is never intersected): the failing part stays coloured either way
    for pieces in (None, [], [None]):
        assert logic.offending_pieces(pieces, "the block") == ["the block"]


def test_the_legend_says_red_is_every_reading_amber_some_and_nothing_where_it_complies():
    text = logic.legend_text()
    assert "only the offending part" in text
    assert "RED: it fails there under every reading" in text
    assert "AMBER: it fails there under some readings only" in text and "2'-0\"" in text
    assert "Nothing where it complies" in text
    assert "a roof's ridge, not its eaves" in text and "a cantilever, not the ground under it" in text
