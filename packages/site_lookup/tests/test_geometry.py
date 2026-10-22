from site_lookup import geometry as g
from site_lookup.sources import normalize_street

SQUARE = [(0, 0), (10, 0), (10, 10), (0, 10)]


def test_area_centroid_inside():
    assert g.area(SQUARE) == 100
    assert g.centroid(SQUARE) == (5, 5)
    assert g.inside((5, 5), SQUARE) and g.inside((10, 5), SQUARE) and not g.inside((11, 5), SQUARE)


def test_open_ring_drops_the_closing_point_and_duplicates():
    assert g.open_ring([[0, 0], [1, 0], [1, 0], [1, 1], [0, 0]]) == [(0, 0), (1, 0), (1, 1)]


def test_distances_and_angles():
    assert g.seg_distance((5, 3), (0, 0), (10, 0)) == 3
    assert g.polyline_distance((12, 0), [(0, 0), (10, 0)]) == 2
    assert g.angle_between(((0, 0), (1, 0)), ((5, 5), (0, 5))) == 0       # parallel, either direction
    assert round(g.angle_between(((0, 0), (1, 0)), ((0, 0), (0, 1)))) == 90
    assert g.angle_between(((0, 0), (1, 0)), None) == 90


def test_grid_inside_covers_the_polygon():
    pts = g.grid_inside(SQUARE, n=10)
    assert len(pts) == 100 and all(g.inside(p, SQUARE) for p in pts)


def test_street_names_are_written_as_the_city_writes_them():
    assert normalize_street("South Cayuga Street") == "S CAYUGA ST"
    assert normalize_street("Ithaca Road") == "ITHACA RD"
    assert normalize_street("ITHACA RD") == "ITHACA RD"
    assert normalize_street("West Green Street") == "W GREEN ST"
