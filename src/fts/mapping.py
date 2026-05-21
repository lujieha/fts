from __future__ import annotations

from typing import Any, Dict, Optional

from .config import resolve_field


ROAD_CLASS_TO_HIGHWAY = {
    41000: "motorway",
    42000: "trunk",
    51000: "primary",
    52000: "secondary",
    53000: "tertiary",
    54000: "residential",
    43000: "trunk",
    44000: "primary",
    45000: "secondary",
    47000: "residential",
    49000: "service",
}

FORM_WAY_RAMP = {6, 8, 9, 10, 56, 58}
LINK_TYPE_SPECIAL = {
    1: {"route": "ferry"},
    2: {"tunnel": "yes"},
    3: {"bridge": "yes"},
    4: {"tunnel": "yes"},
}

WALK_WF_TYPE_TO_HIGHWAY = {
    1: "crossing",
    3: "footway",
    4: "steps",
    8: "steps",
    9: "elevator",
    12: "footway",
    13: "footway",
    18: "footway",
    19: "service",
    20: "steps",
    21: "path",
    22: "footway",
    23: "footway",
    24: "cycleway",
    25: "footway",
    99: "path",
}


def _int(value: Any, default: int = 0) -> int:
    try:
        if value is None or str(value).strip() == "":
            return default
        return int(float(str(value).strip()))
    except (TypeError, ValueError):
        return default


def _clean(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    return text if text else None


def _yes_no_from_1_2(value: Any, yes_code: int = 1, no_code: int = 2) -> Optional[str]:
    code = _int(value, -1)
    if code == yes_code:
        return "yes"
    if code == no_code:
        return "no"
    return None


def map_road_tags(row: Any, aliases: Dict[str, Any], defaults: Any) -> Dict[str, str]:
    road_class = _int(resolve_field(row, "ROAD_CLASS", aliases), 47000)
    form_way = _int(resolve_field(row, "FORM_WAY", aliases), 15)
    direction = _int(resolve_field(row, "DIRECTION", aliases), 1)
    status = _int(resolve_field(row, "STATUS", aliases), 0)
    link_type = _int(resolve_field(row, "LINK_TYPE", aliases), 0)
    vehicle = _clean(resolve_field(row, "VEHICLE", aliases))

    highway = ROAD_CLASS_TO_HIGHWAY.get(road_class, "residential")
    if form_way in FORM_WAY_RAMP and highway in {"motorway", "trunk", "primary", "secondary"}:
        highway = f"{highway}_link"
    elif form_way in FORM_WAY_RAMP:
        highway = "service"

    tags: Dict[str, str] = {
        "highway": highway,
        "source:feature": "RoadSegment",
    }

    road_id = _clean(resolve_field(row, "ROAD_ID", aliases)) or _clean(resolve_field(row, "ROAD", aliases))
    if road_id:
        tags["ref:road_id"] = road_id

    mesh = _clean(resolve_field(row, "MESH", aliases))
    if mesh:
        tags["ref:mesh"] = mesh

    name = _clean(resolve_field(row, "NAME_CHN", aliases)) or _clean(resolve_field(row, "NAME", aliases))
    if name:
        tags["name"] = name
    name_en = _clean(resolve_field(row, "NAME_ENG", aliases))
    if name_en:
        tags["name:en"] = name_en

    max_speed = _int(resolve_field(row, "MAX_SPEED", aliases), 0)
    if max_speed > 0:
        tags["maxspeed"] = str(max_speed)
    elif defaults.road_default_speed_kph > 0:
        tags["maxspeed"] = str(defaults.road_default_speed_kph)

    lanes = _int(resolve_field(row, "S_LANES", aliases), 0)
    if lanes > 0:
        tags["lanes"] = str(lanes)

    width = _clean(resolve_field(row, "WIDTH", aliases))
    if width and width not in {"0", "0.0"}:
        tags["width"] = width

    if direction == 2:
        tags["oneway"] = "yes"
    elif direction == 3:
        tags["oneway"] = "-1"
    elif direction == 4:
        tags["access"] = "no"
    else:
        tags["oneway"] = "no"

    if status in {1, 2, 3}:
        tags["access"] = "no" if defaults.drop_forbidden else "destination"
        tags["construction"] = highway
        tags["highway"] = "construction"

    toll = _yes_no_from_1_2(resolve_field(row, "TOLL_FLAG", aliases))
    if toll:
        tags["toll"] = toll

    ownership = _int(resolve_field(row, "OWNERSHIP", aliases), 0)
    if ownership in {1, 3, 4, 5}:
        tags["access"] = "private" if defaults.include_private_roads else "no"

    if vehicle == "0000000000000000":
        tags["motor_vehicle"] = "no"
    elif vehicle:
        tags["motor_vehicle"] = "yes"

    if link_type in LINK_TYPE_SPECIAL:
        tags.update(LINK_TYPE_SPECIAL[link_type])
    if _int(resolve_field(row, "OVER_HEAD", aliases), 0) == 1:
        tags["bridge"] = tags.get("bridge", "yes")
        tags["layer"] = tags.get("layer", "1")
    if _int(resolve_field(row, "PAVER", aliases), 0) == 1:
        tags["surface"] = "unpaved"
    elif _int(resolve_field(row, "PAVER", aliases), 0) == 2:
        tags["surface"] = "paved"

    return tags


def map_walk_tags(row: Any, aliases: Dict[str, Any], defaults: Any) -> Dict[str, str]:
    wf_type = _int(resolve_field(row, "WF_TYPE", aliases), 13)
    direction = _int(resolve_field(row, "DIRECTION", aliases), 1)
    navitype = _int(resolve_field(row, "NAVITYPE", aliases), 1)
    bicycle = _int(resolve_field(row, "BICYCLE", aliases), 0)
    bi_dir = _int(resolve_field(row, "BI_DIR", aliases), 0)
    bw_mark = _int(resolve_field(row, "BW_MARK", aliases), 0)
    con_status = _int(resolve_field(row, "CONSTATUS", aliases), 1)

    highway = WALK_WF_TYPE_TO_HIGHWAY.get(wf_type, "path")
    tags: Dict[str, str] = {
        "highway": highway,
        "source:feature": "WALK_LINK",
        "foot": "yes",
    }

    link_id = _clean(resolve_field(row, "LINK_ID", aliases))
    if link_id:
        tags["ref:walk_link_id"] = link_id
    mesh = _clean(resolve_field(row, "MESH", aliases))
    if mesh:
        tags["ref:mesh"] = mesh
    name = _clean(resolve_field(row, "NAME", aliases))
    if name:
        tags["name"] = name

    if wf_type in {20, 4, 8}:
        tags["highway"] = "steps"
    if wf_type == 9:
        tags["highway"] = "elevator"
        tags["indoor"] = "yes"
    if wf_type == 22:
        tags["bridge"] = "yes"
    if wf_type == 23:
        tags["tunnel"] = "yes"

    if navitype == 2:
        tags["foot"] = "no"
        tags["motor_vehicle"] = "yes"
    elif navitype == 3:
        tags["access"] = "no"
    else:
        tags["motor_vehicle"] = "no"

    if bicycle in {1, 2, 3} or bw_mark in {2, 3, 4, 5} or wf_type == 24:
        tags["bicycle"] = "yes"
        if wf_type == 24:
            tags["highway"] = "cycleway"
    elif bicycle in {5, 6} or bw_mark in {9, 10}:
        tags["bicycle"] = "no"
    elif bw_mark in {6, 8}:
        tags["bicycle"] = "discouraged"

    if bw_mark in {1, 7}:
        tags["foot"] = "yes"
        tags["bicycle"] = tags.get("bicycle", "no")

    if direction == 2:
        tags["oneway:foot"] = "yes"
    elif direction == 3:
        tags["oneway:foot"] = "-1"
    elif direction == 4:
        tags["foot"] = "no"

    if bi_dir == 2:
        tags["oneway:bicycle"] = "yes"
    elif bi_dir == 3:
        tags["oneway:bicycle"] = "-1"

    toll = _yes_no_from_1_2(resolve_field(row, "ISTOLL", aliases))
    if toll:
        tags["toll"] = toll

    if con_status in {2, 3, 4}:
        tags["access"] = "no" if defaults.drop_forbidden else "destination"
        tags["construction"] = tags.get("highway", "path")
        tags["highway"] = "construction"

    slope = _int(resolve_field(row, "SLOPE", aliases), 0)
    if slope == 2:
        tags["incline"] = "up"
    elif slope == 3:
        tags["incline"] = "down"

    return tags
