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
        self._next_node = -1
        self._next_way = -1_000_000_000

    def node_id(self, lon: float, lat: float, precision: int) -> int:
        key = (round(float(lon), precision), round(float(lat), precision))
        if key not in self._coord_to_node:
            self._coord_to_node[key] = self._next_node
            self._next_node -= 1
        return self._coord_to_node[key]

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
) -> None:
    part_index = 0
    for line in iter_lines(geom):
        coords = list(line.coords)
        if len(coords) < 2:
            result.skipped.append({"source_key": source_key, "reason": "line has fewer than 2 points"})
            continue
        node_ids = []
        for coord in coords:
            lon, lat = coord[0], coord[1]
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
