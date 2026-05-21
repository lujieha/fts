from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, Optional, Sequence, Tuple

import geopandas as gpd
import pandas as pd

from .config import resolve_field


CoordKey = Tuple[float, float]
WalkNodeKey = Tuple[str, str]


@dataclass
class WalkTopologyIndex:
    node_coords: Dict[WalkNodeKey, CoordKey]

    def coord(self, mesh: Optional[str], enter_id: Any) -> Optional[CoordKey]:
        if mesh is None or enter_id is None or str(enter_id).strip() == "":
            return None
        return self.node_coords.get((str(mesh).strip(), str(enter_id).strip()))

    def logical_key(self, mesh: Optional[str], enter_id: Any) -> Optional[str]:
        if mesh is None or enter_id is None or str(enter_id).strip() == "":
            return None
        return f"walkenter:{str(mesh).strip()}:{str(enter_id).strip()}"


def _float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or str(value).strip() == "":
            return default
        return float(str(value).strip())
    except (TypeError, ValueError):
        return default


def _coord_from_row(row: Any, aliases: Dict[str, Iterable[str]], coordinate_unit: str) -> Optional[CoordKey]:
    x = resolve_field(row, "X_COORD", aliases)
    y = resolve_field(row, "Y_COORD", aliases)
    if x is not None and y is not None:
        lon = _float(x)
        lat = _float(y)
        if coordinate_unit == "seconds":
            return (lon / 3600.0, lat / 3600.0)
        return (lon, lat)
    geom = getattr(row, "geometry", None)
    if geom is not None and not geom.is_empty:
        return (float(geom.x), float(geom.y))
    return None


def build_walk_topology_index(
    paths: Sequence[Path],
    aliases: Dict[str, Iterable[str]],
    *,
    coordinate_unit: str = "seconds",
    precision: int = 7,
) -> WalkTopologyIndex:
    """Build a topology index from WALK_ENTER-like point files.

    The exact field names vary across exports. Configure aliases for ENTER_ID,
    MESH, X_COORD and Y_COORD in `config/default.yaml`.
    """
    existing = [p for p in paths if p.exists()]
    if not existing:
        return WalkTopologyIndex({})
    frames = []
    for path in existing:
        gdf = gpd.read_file(path)
        if not gdf.empty:
            gdf["__source_mesh_dir"] = path.parent.name
            frames.append(gdf)
    if not frames:
        return WalkTopologyIndex({})
    gdf = gpd.GeoDataFrame(pd.concat(frames, ignore_index=True), crs=frames[0].crs)

    node_coords: Dict[WalkNodeKey, CoordKey] = {}
    for _, row in gdf.iterrows():
        mesh = resolve_field(row, "MESH", aliases) or row.get("__source_mesh_dir")
        enter_id = (
            resolve_field(row, "ENTER_ID", aliases)
            or resolve_field(row, "NODE", aliases)
            or resolve_field(row, "LINK_ID", aliases)
        )
        if mesh is None or enter_id is None:
            continue
        coord = _coord_from_row(row, aliases, coordinate_unit)
        if coord is None:
            continue
        node_coords[(str(mesh).strip(), str(enter_id).strip())] = (
            round(coord[0], precision),
            round(coord[1], precision),
        )
    return WalkTopologyIndex(node_coords)
