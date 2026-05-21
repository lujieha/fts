from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence

import geopandas as gpd
import pandas as pd

from .config import resolve_field


# RoadRule.RULE_TYPE bit positions described by the source data specification.
RULE_BIT_ALL_DAY = 0
RULE_BIT_FOREIGN_PLATE = 1
RULE_BIT_VEHICLE = 2
RULE_BIT_NO_LEFT_U_TURN = 3
RULE_BIT_NO_RIGHT_U_TURN = 4
RULE_BIT_NO_LONG_PARKING = 5
RULE_BIT_NO_PARKING = 6
RULE_BIT_NO_PASSING = 7
RULE_BIT_NO_ENTRY = 8
RULE_BIT_MAXHEIGHT = 9
RULE_BIT_MAXWIDTH = 10
RULE_BIT_MAXWEIGHT = 11
RULE_BIT_MAXAXLELOAD = 12
RULE_BIT_AREA = 13


LIMIT_CODE_TABLE = {
    1: {"height": "1.25", "width": "1.25", "weight": "1", "axleload": "1"},
    2: {"height": "1.75", "width": "1.75", "weight": "3", "axleload": "3"},
    3: {"height": "2.25", "width": "2.25", "weight": "6", "axleload": "6"},
    4: {"height": "2.75", "width": "2.75", "weight": "10", "axleload": "10"},
    5: {"height": "3.25", "width": "3.25", "weight": "15", "axleload": "15"},
    6: {"height": "3.75", "width": "3.75", "weight": "21", "axleload": "21"},
    7: {"height": "4.25", "width": "4.25", "weight": "28", "axleload": "28"},
    8: {"height": "4.75", "width": "4.75", "weight": "36", "axleload": "36"},
    9: {"height": "5.25", "width": "5.25", "weight": "45", "axleload": "45"},
    10: {"height": "5.75", "width": "5.75", "weight": "55", "axleload": "55"},
    11: {"height": "6.25", "width": "6.25", "weight": "75", "axleload": "75"},
    12: {"height": "6.25", "width": "6.25", "weight": "105", "axleload": "105"},
    13: {"height": "1", "width": "1", "weight": "105", "axleload": "105"},
}


@dataclass(frozen=True)
class RoadRule:
    rule: str
    rule_id: Optional[str]
    rule_flag: int
    rule_type: int
    rule_time: Optional[str]
    vehicle: Optional[str]
    direction: int
    code: int

    def has_bit(self, bit: int) -> bool:
        return bool(self.rule_type & (1 << bit))


class RoadRuleIndex:
    def __init__(self, rules: Dict[str, List[RoadRule]]) -> None:
        self.rules = rules

    def get(self, rule: Any) -> List[RoadRule]:
        if rule is None or str(rule).strip() in {"", "0"}:
            return []
        return self.rules.get(str(int(float(str(rule).strip()))), [])


def _int(value: Any, default: int = 0) -> int:
    try:
        if value is None or str(value).strip() == "":
            return default
        text = str(value).strip()
        if text.lower().startswith("0x"):
            return int(text, 16)
        return int(float(text))
    except (TypeError, ValueError):
        return default


def _clean(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    return text if text else None


def build_road_rule_index(paths: Sequence[Path], aliases: Dict[str, Iterable[str]]) -> RoadRuleIndex:
    existing = [path for path in paths if path.exists()]
    if not existing:
        return RoadRuleIndex({})
    frames = [gpd.read_file(path) for path in existing]
    gdf = gpd.GeoDataFrame(pd.concat(frames, ignore_index=True), crs=frames[0].crs if frames else None)

    rules: Dict[str, List[RoadRule]] = {}
    for _, row in gdf.iterrows():
        rule_value = resolve_field(row, "RULE", aliases)
        if rule_value is None or str(rule_value).strip() in {"", "0"}:
            continue
        rule_key = str(int(float(str(rule_value).strip())))
        item = RoadRule(
            rule=rule_key,
            rule_id=_clean(resolve_field(row, "RULE_ID", aliases)),
            rule_flag=_int(resolve_field(row, "RULE_FLAG", aliases), 0),
            rule_type=_int(resolve_field(row, "RULE_TYPE", aliases), 0),
            rule_time=_clean(resolve_field(row, "RULE_TIME", aliases)),
            vehicle=_clean(resolve_field(row, "VEHICLE", aliases)),
            direction=_int(resolve_field(row, "DIR", aliases), 0),
            code=_int(resolve_field(row, "CODE", aliases), 0),
        )
        rules.setdefault(rule_key, []).append(item)
    return RoadRuleIndex(rules)


def apply_road_rules(tags: Dict[str, str], rule_items: Sequence[RoadRule]) -> Dict[str, str]:
    """Apply RoadRule items to a RoadSegment way tag dictionary.

    RoadRule here is a segment-level rule referenced by RoadSegment.RULE. It is not
    the same as node/cross turn restriction tables. This function therefore applies
    road access and physical limit tags to the way, and preserves original rule
    values under `source:*` tags for traceability.
    """
    if not rule_items:
        return tags

    out = dict(tags)
    out["source:road_rule_count"] = str(len(rule_items))
    for idx, rule in enumerate(rule_items):
        prefix = f"source:road_rule:{idx}"
        out[f"{prefix}:rule"] = rule.rule
        if rule.rule_id:
            out[f"{prefix}:rule_id"] = rule.rule_id
        out[f"{prefix}:rule_type"] = str(rule.rule_type)
        out[f"{prefix}:dir"] = str(rule.direction)
        if rule.rule_time:
            out[f"{prefix}:time"] = rule.rule_time

        if rule.has_bit(RULE_BIT_NO_PASSING) or rule.has_bit(RULE_BIT_NO_ENTRY):
            if rule.rule_time and not rule.has_bit(RULE_BIT_ALL_DAY):
                out["access:conditional"] = f"no @ ({rule.rule_time})"
            else:
                out["access"] = "no"

        if rule.has_bit(RULE_BIT_VEHICLE) and rule.vehicle:
            out[f"{prefix}:vehicle"] = rule.vehicle
            out["source:vehicle_rule"] = rule.vehicle

        limit_values = LIMIT_CODE_TABLE.get(rule.code)
        if limit_values:
            if rule.has_bit(RULE_BIT_MAXHEIGHT):
                out["maxheight"] = limit_values["height"]
                out["source:maxheight:code"] = str(rule.code)
            if rule.has_bit(RULE_BIT_MAXWIDTH):
                out["maxwidth"] = limit_values["width"]
                out["source:maxwidth:code"] = str(rule.code)
            if rule.has_bit(RULE_BIT_MAXWEIGHT):
                out["maxweight"] = limit_values["weight"]
                out["source:maxweight:code"] = str(rule.code)
            if rule.has_bit(RULE_BIT_MAXAXLELOAD):
                out["maxaxleload"] = limit_values["axleload"]
                out["source:maxaxleload:code"] = str(rule.code)

        if rule.has_bit(RULE_BIT_FOREIGN_PLATE):
            out["source:foreign_plate_restriction"] = "yes"
        if rule.has_bit(RULE_BIT_AREA):
            out["source:area_restriction"] = "yes"
        if rule.has_bit(RULE_BIT_NO_PARKING) or rule.has_bit(RULE_BIT_NO_LONG_PARKING):
            out["parking:condition"] = "no_parking"

    return out
