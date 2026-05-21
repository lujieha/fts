from types import SimpleNamespace

from fts.mapping import map_road_tags, map_walk_tags


def test_map_road_primary_oneway():
    row = {
        "ROAD_ID": 10001,
        "NAME_CHN": "示例主路",
        "ROAD_CLASS": 44000,
        "DIRECTION": 2,
        "MAX_SPEED": 60,
        "S_LANES": 3,
        "TOLL_FLAG": 2,
        "VEHICLE": "1000000000000000",
        "STATUS": 0,
        "FORM_WAY": 15,
        "LINK_TYPE": 0,
    }
    defaults = SimpleNamespace(road_default_speed_kph=40, drop_forbidden=True, include_private_roads=False)
    tags = map_road_tags(row, {}, defaults)
    assert tags["highway"] == "primary"
    assert tags["oneway"] == "yes"
    assert tags["maxspeed"] == "60"
    assert tags["motor_vehicle"] == "yes"


def test_map_walk_cycleway():
    row = {
        "LINK_ID": "20001",
        "WF_TYPE": 24,
        "DIRECTION": 1,
        "NAVITYPE": 1,
        "BICYCLE": 1,
        "BI_DIR": 1,
        "BW_MARK": 2,
        "CONSTATUS": 1,
    }
    defaults = SimpleNamespace(drop_forbidden=True)
    tags = map_walk_tags(row, {}, defaults)
    assert tags["highway"] == "cycleway"
    assert tags["foot"] == "yes"
    assert tags["bicycle"] == "yes"
    assert tags["motor_vehicle"] == "no"
