from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Optional

from .config import AppConfig


@dataclass(frozen=True)
class MeshInputSet:
    """Input shapefiles belonging to one mesh folder."""

    mesh: str
    mesh_dir: Path
    road: Optional[Path] = None
    walk: Optional[Path] = None
    road_node: Optional[Path] = None


@dataclass(frozen=True)
class DiscoveredInputs:
    """All input shapefiles discovered from config."""

    road_files: List[Path]
    walk_files: List[Path]
    road_node_files: List[Path]
    mesh_sets: List[MeshInputSet]


def _existing(path: Optional[Path]) -> List[Path]:
    if path is not None and path.exists():
        return [path]
    return []


def discover_mesh_inputs(config: AppConfig) -> List[MeshInputSet]:
    """Discover shapefiles from a region directory containing mesh-named folders.

    Directory layout expected by default:

        <region_dir>/<mesh>/RoadSegment.shp
        <region_dir>/<mesh>/WALK_LINK.shp
        <region_dir>/<mesh>/RoadNodeRoadCross.shp

    The mesh folder name is treated as the mesh id. The actual DBF `MESH` field is
    still used as the authoritative mesh value when present. This fallback is useful
    for incomplete or truncated DBF field exports.
    """
    if not config.inputs.region_dir:
        return []
    region_dir = config.inputs.region_dir
    if not region_dir.exists():
        raise FileNotFoundError(f"Region directory not found: {region_dir}")

    mesh_sets: List[MeshInputSet] = []
    for mesh_dir in sorted(p for p in region_dir.glob(config.inputs.mesh_dir_glob) if p.is_dir()):
        road = mesh_dir / config.inputs.road_filename
        walk = mesh_dir / config.inputs.walk_filename
        road_node = mesh_dir / config.inputs.road_node_filename
        if not road.exists() and not walk.exists() and not road_node.exists():
            continue
        mesh_sets.append(
            MeshInputSet(
                mesh=mesh_dir.name,
                mesh_dir=mesh_dir,
                road=road if road.exists() else None,
                walk=walk if walk.exists() else None,
                road_node=road_node if road_node.exists() else None,
            )
        )
    return mesh_sets


def discover_inputs(config: AppConfig) -> DiscoveredInputs:
    """Discover inputs from both single-file mode and region-directory mode."""
    mesh_sets = discover_mesh_inputs(config)
    road_files = _existing(config.inputs.road)
    walk_files = _existing(config.inputs.walk)
    road_node_files = _existing(config.inputs.road_node)

    road_files.extend(m.road for m in mesh_sets if m.road is not None)
    walk_files.extend(m.walk for m in mesh_sets if m.walk is not None)
    road_node_files.extend(m.road_node for m in mesh_sets if m.road_node is not None)

    return DiscoveredInputs(
        road_files=list(_dedupe_paths(road_files)),
        walk_files=list(_dedupe_paths(walk_files)),
        road_node_files=list(_dedupe_paths(road_node_files)),
        mesh_sets=mesh_sets,
    )


def _dedupe_paths(paths: Iterable[Path]) -> Iterable[Path]:
    seen = set()
    for path in paths:
        key = str(path.resolve()) if path.exists() else str(path)
        if key in seen:
            continue
        seen.add(key)
        yield path
