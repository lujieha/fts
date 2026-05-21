from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

from lxml import etree
from shapely.geometry import LineString, MultiLineString


Coord = Tuple[float, float]


@dataclass
class OsmWay:
    way_id: int
    node_ids: List[int]
    tags: Dict[str, str]
    mesh: Optional[str] = None


@dataclass
class OsmBuildResult:
    nodes: Dict[int, Coord] = field(default_factory=dict)
    ways: List[OsmWay] = field(default_factory=list)
    skipped: List[Dict[str, str]] = field(default_factory=list)


class OsmIdAllocator:
    """Stable negative OSM IDs for generated local data."""

    def __init__(self) -> None:
        self._coord_to_node: Dict[Coord, int] = {}
        self._logical_to_node: Dict[str, int] = {}
        self._next_node = -1
        self._next_way = -1_000_000_000

    def node_id(self, lon: float, lat: float, precision: int) -> int:
        key = (round(float(lon), precision), round(float(lat), precision))
        if key not in self._coord_to_node:
            self._coord_to_node[key] = self._next_node
            self._next_node -= 1
        return self._coord_to_node[key]

    def logical_node_id(self, logical_key: str, lon: float, lat: float, precision: int) -> int:
        """Return a stable node id for a topology node such as mesh+FNODE/TNODE.

        This is used for cross-mesh topology. If two boundary nodes are resolved to
        the same canonical logical key, they will share the same OSM node id even if
        their source links belong to different mesh blocks.
        """
        if logical_key not in self._logical_to_node:
            node_id = self.node_id(lon, lat, precision)
            self._logical_to_node[logical_key] = node_id
        return self._logical_to_node[logical_key]

    def way_id(self, source_key: str) -> int:
        digest = hashlib.sha1(source_key.encode("utf-8")).hexdigest()[:12]
        return -1_000_000 - int(digest, 16) % 900_000_000


def iter_lines(geom) -> Iterable[LineString]:
    if geom is None or geom.is_empty:
        return
    if isinstance(geom, LineString):
        yield geom
    elif isinstance(geom, MultiLineString):
        for part in geom.geoms:
            if not part.is_empty:
                yield part


def add_way_from_geometry(
    result: OsmBuildResult,
    allocator: OsmIdAllocator,
    geom,
    tags: Dict[str, str],
    source_key: str,
    precision: int,
    mesh: Optional[str],
    endpoint_logical_keys: Optional[Tuple[Optional[str], Optional[str]]] = None,
    endpoint_coords: Optional[Tuple[Optional[Coord], Optional[Coord]]] = None,
) -> None:
    part_index = 0
    for line in iter_lines(geom):
        coords = list(line.coords)
        if len(coords) < 2:
            result.skipped.append({"source_key": source_key, "reason": "line has fewer than 2 points"})
            continue
        node_ids = []
        last_idx = len(coords) - 1
        for idx, coord in enumerate(coords):
            lon, lat = coord[0], coord[1]
            logical_key = None
            logical_coord = None
            if endpoint_logical_keys and idx == 0:
                logical_key = endpoint_logical_keys[0]
                logical_coord = endpoint_coords[0] if endpoint_coords else None
            elif endpoint_logical_keys and idx == last_idx:
                logical_key = endpoint_logical_keys[1]
                logical_coord = endpoint_coords[1] if endpoint_coords else None

            if logical_key:
                use_lon, use_lat = logical_coord if logical_coord else (lon, lat)
                nid = allocator.logical_node_id(logical_key, use_lon, use_lat, precision)
                result.nodes[nid] = (round(float(use_lon), precision), round(float(use_lat), precision))
            else:
                nid = allocator.node_id(lon, lat, precision)
                result.nodes[nid] = (round(float(lon), precision), round(float(lat), precision))
            node_ids.append(nid)
        way_tags = {k: v for k, v in tags.items() if v is not None and str(v) != ""}
        way_tags["source:part"] = str(part_index)
        result.ways.append(
            OsmWay(
                way_id=allocator.way_id(f"{source_key}:{part_index}"),
                node_ids=node_ids,
                tags=way_tags,
                mesh=mesh,
            )
        )
        part_index += 1


def write_osm_xml(
    result: OsmBuildResult,
    output_path: Path,
    *,
    osm_version: str = "0.6",
    generator: str = "fts-shp2osm",
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    root = etree.Element("osm", version=osm_version, generator=generator)

    for node_id, (lon, lat) in sorted(result.nodes.items(), key=lambda item: item[0], reverse=True):
        etree.SubElement(root, "node", id=str(node_id), lon=str(lon), lat=str(lat), visible="true")

    for way in result.ways:
        w = etree.SubElement(root, "way", id=str(way.way_id), visible="true")
        for nid in way.node_ids:
            etree.SubElement(w, "nd", ref=str(nid))
        for key, value in sorted(way.tags.items()):
            etree.SubElement(w, "tag", k=str(key), v=str(value))

    tree = etree.ElementTree(root)
    tree.write(str(output_path), encoding="utf-8", xml_declaration=True, pretty_print=True)


def write_statistics(result: OsmBuildResult, output_path: Path) -> None:
    by_highway: Dict[str, int] = {}
    by_mesh: Dict[str, int] = {}
    for way in result.ways:
        by_highway[way.tags.get("highway", "unknown")] = by_highway.get(way.tags.get("highway", "unknown"), 0) + 1
        mesh = way.mesh or way.tags.get("ref:mesh", "unknown")
        by_mesh[mesh] = by_mesh.get(mesh, 0) + 1
    payload = {
        "nodes": len(result.nodes),
        "ways": len(result.ways),
        "skipped": len(result.skipped),
        "by_highway": dict(sorted(by_highway.items())),
        "by_mesh": dict(sorted(by_mesh.items())),
        "skipped_detail": result.skipped[:1000],
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
