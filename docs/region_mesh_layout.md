# Region mesh layout

A region can contain many mesh folders. Each mesh folder contains shapefiles for that mesh.

Example:

```text
data/region/mesh_a/RoadSegment.shp
data/region/mesh_a/WALK_LINK.shp
data/region/mesh_a/RoadNodeRoadCross.shp
data/region/mesh_b/RoadSegment.shp
data/region/mesh_b/WALK_LINK.shp
data/region/mesh_b/RoadNodeRoadCross.shp
```

Configuration:

```yaml
inputs:
  region_dir: data/region
  mesh_dir_glob: "*"
  road_filename: RoadSegment.shp
  walk_filename: WALK_LINK.shp
  road_node_filename: RoadNodeRoadCross.shp
```

Run:

```bash
fts-shp2osm --config config/default.yaml --region-dir data/region --mode both
```

Rules:

1. The converter scans all mesh folders under `region_dir`.
2. Folder name is used as fallback mesh id.
3. DBF field `MESH` is preferred when it exists.
4. All RoadSegment files are read as one regional road dataset.
5. All WALK_LINK files are read as one regional walk and bicycle dataset.
6. All RoadNodeRoadCross files are read together for cross-mesh topology.
