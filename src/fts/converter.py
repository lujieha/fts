from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Iterable, Optional

import geopandas as gpd

from .config import AppConfig, resolve_field
from .mapping import map_road_tags, map_walk_tags
from .osm_writer import OsmBuildResult, OsmIdAllocator, add_way_from_geometry, write_osm_xml, write_statistics


def _read_shapefile(path: Path, target_crs: str) -> gpd.GeoDataFrame:
    if not path.exists():
        raise FileNotFoundError(f"Shapefile not found: {path}")
    gdf = gpd.read_file(path)
    if gdf.empty:
        return gdf
    if gdf.crs is None:
        # Most domestic navigation shapefiles in this workflow are already longitude/latitude.
        gdf = gdf.set_crs(target_crs, allow_override=True)
    elif str(gdf.crs).upper() != target_crs.upper():
        gdf = gdf.to_crs(target_crs)
    return gdf


def _row_id(row: Any, candidates: Iterable[str], aliases: Dict[str, Any], fallback: str) -> str:
    for name in candidates:
        value = resolve_field(row, name, aliases)
        if value is not None and str(value).strip() != "":
            return str(value).strip()
    return fallback


def _row_mesh(row: Any, aliases: Dict[str, Any], split_key: str = "MESH") -> Optional[str]:
    value = resolve_field(row, split_key, aliases)
    if value is None or str(value).strip() == "":
        return None
    return str(value).strip()


def convert(config: AppConfig) -> Dict[str, Path]:
    out_dir = config.inputs.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    allocator = OsmIdAllocator()
    merged = OsmBuildResult()
    per_mesh: Dict[str, OsmBuildResult] = {}

    def add_to_results(row: Any, geom: Any, tags: Dict[str, str], source_key: str, mesh: Optional[str]) -> None:
        add_way_from_geometry(
            merged,
            allocator,
            geom,
            tags,
            source_key,
            config.output.precision,
            mesh,
        )
        if config.output.mode in {"by_mesh", "both"}:
            mesh_key = mesh or "unknown"
            if mesh_key not in per_mesh:
                per_mesh[mesh_key] = OsmBuildResult()
            # Per-mesh outputs intentionally use the same allocator to keep IDs stable across files.
            add_way_from_geometry(
                per_mesh[mesh_key],
                allocator,
                geom,
                tags,
                source_key,
                config.output.precision,
                mesh,
            )

    if config.inputs.road:
        road_gdf = _read_shapefile(config.inputs.road, config.geometry.target_crs)
        road_aliases = config.field_aliases.get("road", {})
        for index, row in road_gdf.iterrows():
            tags = map_road_tags(row, road_aliases, config.defaults)
            if config.defaults.drop_forbidden and tags.get("access") == "no":
                continue
            mesh = _row_mesh(row, road_aliases, config.output.split_key)
            key = "road:" + _row_id(row, ["ROAD_ID", "ROAD"], road_aliases, str(index))
            add_to_results(row, row.geometry, tags, key, mesh)

    if config.inputs.walk:
        walk_gdf = _read_shapefile(config.inputs.walk, config.geometry.target_crs)
        walk_aliases = config.field_aliases.get("walk", {})
        for index, row in walk_gdf.iterrows():
            tags = map_walk_tags(row, walk_aliases, config.defaults)
            if config.defaults.drop_forbidden and tags.get("access") == "no":
                continue
            mesh = _row_mesh(row, walk_aliases, config.output.split_key)
            key = "walk:" + _row_id(row, ["LINK_ID"], walk_aliases, str(index))
            add_to_results(row, row.geometry, tags, key, mesh)

    outputs: Dict[str, Path] = {}
    if config.output.mode in {"merged", "both"}:
        osm_path = out_dir / config.output.file_name
        write_osm_xml(
            merged,
            osm_path,
            osm_version=config.output.osm_version,
            generator=config.output.generator,
        )
        outputs["merged_osm"] = osm_path
        if config.output.write_statistics:
            stat_path = osm_path.with_suffix(".stats.json")
            write_statistics(merged, stat_path)
            outputs["merged_stats"] = stat_path

    if config.output.mode in {"by_mesh", "both"}:
        mesh_dir = out_dir / "mesh"
        mesh_dir.mkdir(parents=True, exist_ok=True)
        for mesh, result in sorted(per_mesh.items()):
            osm_path = mesh_dir / f"{mesh}.osm"
            write_osm_xml(
                result,
                osm_path,
                osm_version=config.output.osm_version,
                generator=config.output.generator,
            )
            outputs[f"mesh:{mesh}"] = osm_path
            if config.output.write_statistics:
                write_statistics(result, osm_path.with_suffix(".stats.json"))

    return outputs
