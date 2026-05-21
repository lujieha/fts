from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, Optional, Tuple

import geopandas as gpd

from .config import resolve_field


CoordKey = Tuple[float, float]
TopologyNodeKey = Tuple[str, str]


BOUNDARY_INSIDE = 0
BOUNDARY_TOP = 2
BOUNDARY_LEFT = 4
BOUNDARY_RIGHT = 6
BOUNDARY_BOTTOM = 8


OPPOSITE_BOUNDARY = {
    BOUNDARY_TOP: BOUNDARY_BOTTOM,
    BOUNDARY_BOTTOM: BOUNDARY_TOP,
    BOUNDARY_LEFT: BOUNDARY_RIGHT,
    BOUNDARY_RIGHT: BOUNDARY_LEFT,
}


@dataclass(frozen=True)
class BoundaryNode:
    mesh: str
    node: str
    boundary: int
    lon: float
    lat: float


@dataclass
class TopologyIndex:
    """Index used to resolve cross-mesh logical nodes.

    `aliases` maps a node in one mesh to its equivalent node in a neighboring mesh.
    The canonical key is the lexicographically smallest key in an alias group.
    """

    aliases: Dict[TopologyNodeKey, TopologyNodeKey]
    node_coords: Dict[TopologyNodeKey, CoordKey]

    def canonical_node(self, mesh: Optional[str], node_id: Any) -> Optional[TopologyNodeKey]:
        if mesh is None or node_id is None or str(node_id).strip() == "":
            return None
        key = (str(mesh).strip(), str(node_id).strip())
        return self.aliases.get(key, key)

    def canonical_coord(self, mesh: Optional[str], node_id: Any) -> Optional[CoordKey]:
        key = self.canonical_node(mesh, node_id)
        if key is None:
            return None
        return self.node_coords.get(key)


def get_neighbor_mesh(mesh: str, direction: int) -> Optional[str]:
    """Return adjacent mesh id for the requested boundary direction.

    Parameters
    ----------
    mesh:
        Current mesh id, for example the 10-character MESH value in the source data.
    direction:
        One of 2, 4, 6, 8:
        - 2: upper/top neighbor
        - 4: left neighbor
        - 6: right neighbor
        - 8: lower/bottom neighbor

    TODO:
        Implement this method using your internal mesh numbering rule.
        The converter calls this method only for boundary nodes. Returning None means
        "do not attempt cross-mesh matching for this node".

    Example implementation idea:
        1. Decode mesh into row/column or tile coordinate.
        2. Adjust row/column according to direction.
        3. Encode adjusted coordinate back to mesh id.

    Notes
    -----
    This is intentionally left blank because mesh id systems differ between datasets.
    """
    _ = mesh, direction
    return None


def _float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or str(value).strip() == "":
            return default
        return float(str(value).strip())
    except (TypeError, ValueError):
        return default


def _int(value: Any, default: int = 0) -> int:
    try:
        if value is None or str(value).strip() == "":
            return default
        return int(float(str(value).strip()))
    except (TypeError, ValueError):
        return default


def _coord_key(lon: float, lat: float, precision: int) -> CoordKey:
    return (round(lon, precision), round(lat, precision))


def _to_lon_lat(x_coord: Any, y_coord: Any, coordinate_unit: str) -> CoordKey:
    """Convert RoadNodeRoadCross X_COORD/Y_COORD to lon/lat.

    The vehicle spec describes X_COORD/Y_COORD as seconds. Some exported shapefiles
    may already store decimal degrees, so this is configurable.
    """
    x = _float(x_coord)
    y = _float(y_coord)
    if coordinate_unit == "seconds":
        return (x / 3600.0, y / 3600.0)
    if coordinate_unit == "degrees":
        return (x, y)
    raise ValueError(f"Unsupported node coordinate unit: {coordinate_unit}")


def _canonical_pair(a: TopologyNodeKey, b: TopologyNodeKey) -> TopologyNodeKey:
    return min(a, b)


def build_topology_index(
    node_path: Path,
    aliases: Dict[str, Iterable[str]],
    *,
    coordinate_unit: str = "seconds",
    coordinate_precision: int = 7,
) -> TopologyIndex:
    """Build a cross-mesh node index from RoadNodeRoadCross.

    Matching rule:
    1. Read each boundary node from RoadNodeRoadCross.
    2. Use `get_neighbor_mesh(mesh, boundary)` to find the neighbor mesh.
    3. Look for a node in the neighbor mesh whose BOUNDARY is the opposite side and
       whose X_COORD/Y_COORD match after rounding.
    4. Alias both logical nodes to one canonical topology node.

    This supports the case described in the data spec:
    - current mesh `BOUNDARY == 2` is on the upper boundary;
    - upper neighbor mesh should have the corresponding node with `BOUNDARY == 8`;
    - matching coordinates indicate the same cross-mesh node.
    """
    if not node_path.exists():
        raise FileNotFoundError(f"RoadNodeRoadCross shapefile not found: {node_path}")

    gdf = gpd.read_file(node_path)
    boundary_nodes: list[BoundaryNode] = []
    by_mesh_boundary_coord: Dict[Tuple[str, int, CoordKey], BoundaryNode] = {}
    node_coords: Dict[TopologyNodeKey, CoordKey] = {}

    for _, row in gdf.iterrows():
        mesh_value = resolve_field(row, "MESH", aliases)
        node_value = resolve_field(row, "NODE", aliases) or resolve_field(row, "NODE_ID", aliases)
        if mesh_value is None or node_value is None:
            continue
        mesh = str(mesh_value).strip()
        node = str(node_value).strip()
        boundary = _int(resolve_field(row, "BOUNDARY", aliases), BOUNDARY_INSIDE)
        lon, lat = _to_lon_lat(
            resolve_field(row, "X_COORD", aliases),
            resolve_field(row, "Y_COORD", aliases),
            coordinate_unit,
        )
        coord = _coord_key(lon, lat, coordinate_precision)
        key = (mesh, node)
        node_coords[key] = coord

        if boundary in OPPOSITE_BOUNDARY:
            bn = BoundaryNode(mesh=mesh, node=node, boundary=boundary, lon=coord[0], lat=coord[1])
            boundary_nodes.append(bn)
            by_mesh_boundary_coord[(mesh, boundary, coord)] = bn

    aliases_out: Dict[TopologyNodeKey, TopologyNodeKey] = {}

    for bn in boundary_nodes:
        neighbor_mesh = get_neighbor_mesh(bn.mesh, bn.boundary)
        if not neighbor_mesh:
            continue
        opposite_boundary = OPPOSITE_BOUNDARY[bn.boundary]
        coord = (bn.lon, bn.lat)
        other = by_mesh_boundary_coord.get((neighbor_mesh, opposite_boundary, coord))
        if other is None:
            continue

        a = (bn.mesh, bn.node)
        b = (other.mesh, other.node)
        canonical = _canonical_pair(a, b)
        aliases_out[a] = canonical
        aliases_out[b] = canonical
        node_coords[canonical] = coord

    return TopologyIndex(aliases=aliases_out, node_coords=node_coords)
