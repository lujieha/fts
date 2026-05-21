from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, Optional

import yaml


@dataclass(frozen=True)
class InputPaths:
    # Single-file mode. Useful for small tests or already-merged shapefiles.
    road: Optional[Path] = None
    walk: Optional[Path] = None
    road_node: Optional[Path] = None
    road_rule: Optional[Path] = None

    # Region-directory mode. A region consists of multiple mesh-named folders, and
    # each mesh folder contains its own shapefiles.
    region_dir: Optional[Path] = None
    mesh_dir_glob: str = "*"
    road_filename: str = "RoadSegment.shp"
    walk_filename: str = "WALK_LINK.shp"
    road_node_filename: str = "RoadNodeRoadCross.shp"
    road_rule_filename: str = "RoadRule.shp"

    out_dir: Path = Path("out")


@dataclass(frozen=True)
class OutputOptions:
    mode: str = "merged"  # merged | by_mesh | both
    file_name: str = "valhalla_input.osm"
    split_key: str = "MESH"
    osm_version: str = "0.6"
    generator: str = "fts-shp2osm"
    precision: int = 7
    write_statistics: bool = True


@dataclass(frozen=True)
class GeometryOptions:
    target_crs: str = "EPSG:4326"
    snap_tolerance_m: float = 0.15
    preserve_shape_vertices: bool = True
    simplify_tolerance_m: float = 0.0


@dataclass(frozen=True)
class TopologyOptions:
    enabled: bool = False
    node_coordinate_unit: str = "seconds"  # seconds | degrees
    node_coordinate_precision: int = 7
    prefer_topology_nodes: bool = True


@dataclass(frozen=True)
class RoutingDefaults:
    road_default_speed_kph: int = 40
    foot_default_speed_kph: int = 5
    bicycle_default_speed_kph: int = 15
    assume_access_yes_when_unknown: bool = True
    drop_forbidden: bool = True
    include_private_roads: bool = False
    use_average_speed_as_maxspeed_fallback: bool = False
    use_speed_cate_as_maxspeed_fallback: bool = True
    apply_road_rules: bool = True


@dataclass(frozen=True)
class AppConfig:
    inputs: InputPaths = field(default_factory=InputPaths)
    output: OutputOptions = field(default_factory=OutputOptions)
    geometry: GeometryOptions = field(default_factory=GeometryOptions)
    topology: TopologyOptions = field(default_factory=TopologyOptions)
    defaults: RoutingDefaults = field(default_factory=RoutingDefaults)
    field_aliases: Dict[str, Dict[str, Iterable[str]]] = field(default_factory=dict)
    mappings: Dict[str, Any] = field(default_factory=dict)


def _path_or_none(value: Any) -> Optional[Path]:
    if value in (None, ""):
        return None
    return Path(str(value))


def load_config(path: str | Path) -> AppConfig:
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}

    input_raw = raw.get("inputs", {})
    output_raw = raw.get("output", {})
    geometry_raw = raw.get("geometry", {})
    topology_raw = raw.get("topology", {})
    defaults_raw = raw.get("defaults", {})

    return AppConfig(
        inputs=InputPaths(
            road=_path_or_none(input_raw.get("road")),
            walk=_path_or_none(input_raw.get("walk")),
            road_node=_path_or_none(input_raw.get("road_node")),
            road_rule=_path_or_none(input_raw.get("road_rule")),
            region_dir=_path_or_none(input_raw.get("region_dir")),
            mesh_dir_glob=str(input_raw.get("mesh_dir_glob", "*")),
            road_filename=str(input_raw.get("road_filename", "RoadSegment.shp")),
            walk_filename=str(input_raw.get("walk_filename", "WALK_LINK.shp")),
            road_node_filename=str(input_raw.get("road_node_filename", "RoadNodeRoadCross.shp")),
            road_rule_filename=str(input_raw.get("road_rule_filename", "RoadRule.shp")),
            out_dir=Path(str(input_raw.get("out_dir", "out"))),
        ),
        output=OutputOptions(**{**OutputOptions().__dict__, **output_raw}),
        geometry=GeometryOptions(**{**GeometryOptions().__dict__, **geometry_raw}),
        topology=TopologyOptions(**{**TopologyOptions().__dict__, **topology_raw}),
        defaults=RoutingDefaults(**{**RoutingDefaults().__dict__, **defaults_raw}),
        field_aliases=raw.get("field_aliases", {}),
        mappings=raw.get("mappings", {}),
    )


def normalize_columns(columns: Iterable[str]) -> Dict[str, str]:
    """Return a case/space-insensitive mapping from normalized field name to real field name."""
    out: Dict[str, str] = {}
    for col in columns:
        norm = canonical_field_name(col)
        out[norm] = col
    return out


def canonical_field_name(name: str) -> str:
    return str(name).strip().upper().replace(" ", "_").replace("＿", "_")


def resolve_field(row: Any, logical_name: str, aliases: Dict[str, Iterable[str]], default: Any = None) -> Any:
    candidates = [logical_name, *aliases.get(logical_name, [])]
    row_keys = {canonical_field_name(k): k for k in row.keys()}
    for candidate in candidates:
        real = row_keys.get(canonical_field_name(candidate))
        if real is not None:
            value = row.get(real)
            if value is not None and str(value).strip() != "":
                return value
    return default
