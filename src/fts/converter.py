from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Iterable, Optional, Sequence, Tuple

import geopandas as gpd
import pandas as pd

from .config import AppConfig, resolve_field
from .inputs import discover_inputs
from .mapping import map_road_tags, map_walk_tags
from .osm_writer import OsmBuildResult, OsmIdAllocator, add_way_from_geometry, write_osm_xml, write_statistics
from .topology import TopologyIndex, build_topology_index


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


def _read_many_shapefiles(paths: Sequence[Path], target_crs: str) -> gpd.GeoDataFrame:
    frames = []
    for path in paths:
        gdf = _read_shapefile(path, target_crs)
        if not gdf.empty:
            gdf["__source_file"] = str(path)
            gdf["__source_mesh_dir"] = path.parent.name
            frames.append(gdf)
    if not frames:
        return gpd.GeoDataFrame(geometry=[])
    return gpd.GeoDataFrame(pd.concat(frames, ignore_index=True), crs=frames[0].crs)


def _row_id(row: Any, candidates: Iterable[str], aliases: Dict[str, Any], fallback: str) -> str:
    for name in candidates:
        value = resolve_field(row, name, aliases)
        if value is not None and str(value).strip() != "":
            return str(value).strip()
    return fallback


def _row_mesh(row: Any, aliases: Dict[str, Any], split_key: str = "MESH") -> Optional[str]:
    value = resolve_field(row, split_key, aliases)
    if value is not None and str(value).strip() != "":
        return str(value).strip()
    # Fallback for region-directory mode: use mesh folder name when DBF MESH is absent.
    source_mesh_dir = row.get("__source_mesh_dir") if hasattr(row, "get") else None
    if source_mesh_dir is not None and str(source_mesh_dir).strip() != "":
        return str(source_mesh_dir).strip()
    return None


def _road_endpoint_topology(
    row: Any,
    aliases: Dict[str, Any],
    mesh: Optional[str],
    topology: Optional[TopologyIndex],
) -> Tuple[Tuple[Optional[str], Optional[str]], Tuple[Optional[Tuple[float, float]], Optional[Tuple[float, float]]]]:
    if topology is None or mesh is None:
        return (None, None), (None, None)

    fnode = resolve_field(row, "FNODE", aliases)
    tnode = resolve_field(row, "TNODE", aliases)
    fkey = topology.canonical_node(mesh, fnode)
    tkey = topology.canonical_node(mesh, tnode)

    fkey_text = f"roadnode:{fkey[0]}:{fkey[1]}" if fkey else None
    tkey_text = f"roadnode:{tkey[0]}:{tkey[1]}" if tkey else None
    fcoord = topology.canonical_coord(mesh, fnode)
    tcoord = topology.canonical_coord(mesh, tnode)
    return (fkey_text, tkey_text), (fcoord, tcoord)


def convert(config: AppConfig) -> Dict[str, Path]:
    out_dir = config.inputs.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    discovered = discover_inputs(config)
    allocator = OsmIdAllocator()
    merged = OsmBuildResult()
    per_mesh: Dict[str, OsmBuildResult] = {}
    topology: Optional[TopologyIndex] = None

    if config.topology.enabled:
        if not discovered.road_node_files:
            raise ValueError(
                "topology.enabled=true requires inputs.road_node or region_dir mesh node files"
            )
        topology = build_topology_index(
            discovered.road_node_files,
            config.field_aliases.get("road_node", {}),
            coordinate_unit=config.topology.node_coordinate_unit,
            coordinate_precision=config.topology.node_coordinate_precision,
        )

    def add_to_results(
        row: Any,
        geom: Any,
        tags: Dict[str, str],
        source_key: str,
        mesh: Optional[str],
        endpoint_logical_keys: Optional[Tuple[Optional[str], Optional[str]]] = None,
        endpoint_coords: Optional[Tuple[Optional[Tuple[float, float]], Optional[Tuple[float, float]]]] = None,
    ) -> None:
        add_way_from_geometry(
            merged,
            allocator,
            geom,
            tags,
            source_key,
            config.output.precision,
            mesh,
            endpoint_logical_keys=endpoint_logical_keys,
            endpoint_coords=endpoint_coords,
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
                endpoint_logical_keys=endpoint_logical_keys,
                endpoint_coords=endpoint_coords,
            )

    if discovered.road_files:
        road_gdf = _read_many_shapefiles(discovered.road_files, config.geometry.target_crs)
        road_aliases = config.field_aliases.get("road", {})
        for index, row in road_gdf.iterrows():
            tags = map_road_tags(row, road_aliases, config.defaults)
            if config.defaults.drop_forbidden and tags.get("access") == "no":
                continue
            mesh = _row_mesh(row, road_aliases, config.output.split_key)
            key = "road:" + _row_id(row, ["ROAD_ID", "ROAD"], road_aliases, str(index))
            endpoint_keys, endpoint_coords = (None, None), (None, None)
            if config.topology.prefer_topology_nodes:
                endpoint_keys, endpoint_coords = _road_endpoint_topology(row, road_aliases, mesh, topology)
            add_to_results(row, row.geometry, tags, key, mesh, endpoint_keys, endpoint_coords)

    if discovered.walk_files:
        walk_gdf = _read_many_shapefiles(discovered.walk_files, config.geometry.target_crs)
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
