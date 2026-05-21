from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .config import load_config
from .converter import convert


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="fts-shp2osm",
        description="Convert local road/walk/cycle shapefiles to OSM XML for Valhalla.",
    )
    parser.add_argument("--config", required=True, help="Path to YAML configuration file.")
    parser.add_argument("--region-dir", help="Region directory containing mesh-named subfolders.")
    parser.add_argument("--mesh-dir-glob", help="Glob pattern used to select mesh subfolders.")
    parser.add_argument("--road", help="Override single road shapefile path.")
    parser.add_argument("--walk", help="Override single walk/cycle shapefile path.")
    parser.add_argument("--road-node", help="Override single RoadNodeRoadCross shapefile path.")
    parser.add_argument("--out-dir", help="Override output directory.")
    parser.add_argument("--mode", choices=["merged", "by_mesh", "both"], help="Override output mode.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    config = load_config(args.config)

    # Dataclasses are frozen; use object.__setattr__ for CLI overrides only.
    if args.region_dir:
        object.__setattr__(config.inputs, "region_dir", Path(args.region_dir))
    if args.mesh_dir_glob:
        object.__setattr__(config.inputs, "mesh_dir_glob", args.mesh_dir_glob)
    if args.road:
        object.__setattr__(config.inputs, "road", Path(args.road))
    if args.walk:
        object.__setattr__(config.inputs, "walk", Path(args.walk))
    if args.road_node:
        object.__setattr__(config.inputs, "road_node", Path(args.road_node))
    if args.out_dir:
        object.__setattr__(config.inputs, "out_dir", Path(args.out_dir))
    if args.mode:
        object.__setattr__(config.output, "mode", args.mode)

    outputs = convert(config)
    for label, path in outputs.items():
        print(f"{label}: {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
