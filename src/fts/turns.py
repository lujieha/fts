from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import geopandas as gpd
import pandas as pd

from .config import resolve_field
from .osm_writer import OsmRelationMember
from .topology import TopologyIndex


RULE_SIGN_TO_RESTRICTION = {
    1: "no_left_turn",
    2: "no_right_turn",
    3: "no_straight_on",
    4: "no_u_turn",
    5: "no_u_turn",
}


@dataclass(frozen=True)
class TurnRule:
    rule: str
    rule_id: Optional[str]
    rule_flag: int
    rule_type: int
    rule_sign: int
    rule_time: Optional[str]
    vehicle: Optional[str]


@dataclass(frozen=True)
class TurnMaat:
    source: str  # node | cross
    mesh: str
    node: str
    from_road: str
    to_road: str
    rule: Optional[str]
    rule_cnt: int


@dataclass(frozen=True)
class TurnRestriction:
    source_key: str
    from_way_id: int
    via_node_id: int
    to_way_id: int
    tags: Dict[str, str]

    @property
    def members(self) -> List[OsmRelationMember]:
        return [
            OsmRelationMember(type="way", ref=self.from_way_id, role="from"),
            OsmRelationMember(type="node", ref=self.via_node_id, role="via"),
            OsmRelationMember(type="way", ref=self.to_way_id, role="to"),
        ]


class TurnRuleIndex:
    def __init__(self, rules: Dict[str, List[TurnRule]]) -> None:
        self.rules = rules

    def get(self, rule: Any) -> List[TurnRule]:
        if rule is None or str(rule).strip() in {"", "0"}:
            return []
        return self.rules.get(_id_text(rule), [])


def _id_text(value: Any) -> str:
    return str(int(float(str(value).strip())))


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


def _read_many(paths: Sequence[Path]) -> gpd.GeoDataFrame:
    existing = [p for p in paths if p.exists()]
    if not existing:
        return gpd.GeoDataFrame()
    frames = []
    for path in existing:
        gdf = gpd.read_file(path)
        if not gdf.empty:
            gdf["__source_file"] = str(path)
            gdf["__source_mesh_dir"] = path.parent.name
            frames.append(gdf)
    if not frames:
        return gpd.GeoDataFrame()
    return gpd.GeoDataFrame(pd.concat(frames, ignore_index=True), crs=frames[0].crs)


def build_turn_rule_index(paths: Sequence[Path], aliases: Dict[str, Iterable[str]]) -> TurnRuleIndex:
    gdf = _read_many(paths)
    rules: Dict[str, List[TurnRule]] = {}
    for _, row in gdf.iterrows():
        rule_value = resolve_field(row, "RULE", aliases)
        if rule_value is None or str(rule_value).strip() in {"", "0"}:
            continue
        rule_key = _id_text(rule_value)
        item = TurnRule(
            rule=rule_key,
            rule_id=_clean(resolve_field(row, "RULE_ID", aliases)),
            rule_flag=_int(resolve_field(row, "RULE_FLAG", aliases), 0),
            rule_type=_int(resolve_field(row, "RULE_TYPE", aliases), 0),
            rule_sign=_int(resolve_field(row, "RULE_SIGN", aliases), 0),
            rule_time=_clean(resolve_field(row, "RULE_TIME", aliases)),
            vehicle=_clean(resolve_field(row, "VEHICLE", aliases)),
        )
        rules.setdefault(rule_key, []).append(item)
    return TurnRuleIndex(rules)


def read_maat_files(
    paths: Sequence[Path],
    aliases: Dict[str, Iterable[str]],
    *,
    source: str,
) -> List[TurnMaat]:
    gdf = _read_many(paths)
    out: List[TurnMaat] = []
    for _, row in gdf.iterrows():
        mesh = _clean(resolve_field(row, "MESH", aliases)) or _clean(row.get("__source_mesh_dir"))
        node = _clean(resolve_field(row, "NODE", aliases))
        from_road = _clean(resolve_field(row, "FROM_ROAD", aliases))
        to_road = _clean(resolve_field(row, "TO_ROAD", aliases))
        if not mesh or not node or not from_road or not to_road:
            continue
        out.append(
            TurnMaat(
                source=source,
                mesh=mesh,
                node=_id_text(node),
                from_road=_id_text(from_road),
                to_road=_id_text(to_road),
                rule=_clean(resolve_field(row, "RULE", aliases)),
                rule_cnt=_int(resolve_field(row, "RULE_CNT", aliases), 0),
            )
        )
    return out


def build_turn_restrictions(
    maats: Sequence[TurnMaat],
    rule_index: TurnRuleIndex,
    road_way_index: Dict[Tuple[str, str], int],
    topology: Optional[TopologyIndex],
    logical_node_to_osm_id: Dict[str, int],
) -> Tuple[List[TurnRestriction], List[Dict[str, str]]]:
    """Build OSM turn restriction relations from Maat and Node/CrossRule records.

    Maat rows define link-to-link topology. Only rows with an explicit rule whose
    RULE_SIGN maps to an OSM restriction produce a relation. Rows without such rules
    are treated as ordinary allowed turns and do not need an OSM relation.
    """
    restrictions: List[TurnRestriction] = []
    skipped: List[Dict[str, str]] = []

    for maat in maats:
        from_way = road_way_index.get((maat.mesh, maat.from_road))
        to_way = road_way_index.get((maat.mesh, maat.to_road))
        if from_way is None or to_way is None:
            skipped.append({
                "reason": "missing from/to way",
                "mesh": maat.mesh,
                "node": maat.node,
                "from_road": maat.from_road,
                "to_road": maat.to_road,
            })
            continue

        canonical = topology.canonical_node(maat.mesh, maat.node) if topology else (maat.mesh, maat.node)
        if canonical is None:
            skipped.append({"reason": "missing canonical via node", "mesh": maat.mesh, "node": maat.node})
            continue
        logical_key = f"roadnode:{canonical[0]}:{canonical[1]}"
        via_node = logical_node_to_osm_id.get(logical_key)
        if via_node is None:
            skipped.append({"reason": "via node has no OSM node id", "logical_key": logical_key})
            continue

        for rule in rule_index.get(maat.rule):
            restriction = RULE_SIGN_TO_RESTRICTION.get(rule.rule_sign)
            if not restriction:
                continue
            tags = {
                "type": "restriction",
                "restriction": restriction,
                "source:feature": f"{maat.source}_maat_rule",
                "source:mesh": maat.mesh,
                "source:node": maat.node,
                "source:from_road": maat.from_road,
                "source:to_road": maat.to_road,
                "source:rule": rule.rule,
                "source:rule_sign": str(rule.rule_sign),
            }
            if rule.rule_id:
                tags["source:rule_id"] = rule.rule_id
            if rule.rule_time:
                tags["restriction:conditional"] = f"{restriction} @ ({rule.rule_time})"
                tags["source:rule_time"] = rule.rule_time
            if rule.vehicle:
                tags["source:vehicle_rule"] = rule.vehicle
            source_key = f"turn:{maat.source}:{maat.mesh}:{maat.node}:{maat.from_road}:{maat.to_road}:{rule.rule}"
            restrictions.append(
                TurnRestriction(
                    source_key=source_key,
                    from_way_id=from_way,
                    via_node_id=via_node,
                    to_way_id=to_way,
                    tags=tags,
                )
            )
    return restrictions, skipped
