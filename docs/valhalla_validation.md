# Valhalla 可用性验证

## 1. 生成 OSM

```bash
pip install -e .
fts-shp2osm --config config/default.yaml --road data/RoadSegment.shp --walk data/WALK_LINK.shp --mode both
```

输出：

- `out/valhalla_input.osm`：合并后的 OSM XML。
- `out/mesh/<MESH>.osm`：按 `MESH` 分块的 OSM XML。
- `*.stats.json`：节点、way、highway 类型、mesh 数量统计。

## 2. XML 基础校验

```bash
xmllint --noout out/valhalla_input.osm
```

## 3. 使用 osmium 可选校验

```bash
osmium fileinfo out/valhalla_input.osm
osmium check-refs out/valhalla_input.osm
```

## 4. 构建 Valhalla tiles

Valhalla 通常接受 `.osm.pbf`，建议先从 XML 转换为 PBF：

```bash
osmium cat out/valhalla_input.osm -o out/valhalla_input.osm.pbf -f pbf,add_metadata=false --overwrite
```

生成配置：

```bash
mkdir -p valhalla_tiles
valhalla_build_config \
  --mjolnir-tile-dir valhalla_tiles \
  --mjolnir-tile-extract valhalla_tiles.tar \
  --mjolnir-timezone /usr/share/zoneinfo \
  --mjolnir-admin /tmp/admin.sqlite > valhalla.json
```

构建 tiles：

```bash
valhalla_build_tiles -c valhalla.json out/valhalla_input.osm.pbf
find valhalla_tiles -type f | head
```

## 5. 启动服务并验证路径规划

```bash
valhalla_service valhalla.json 1
```

车行：

```bash
curl 'http://localhost:8002/route' \
  -H 'Content-Type: application/json' \
  -d '{"locations":[{"lat":39.9070,"lon":116.3910},{"lat":39.9080,"lon":116.3930}],"costing":"auto","directions_options":{"units":"kilometers"}}'
```

步行：

```bash
curl 'http://localhost:8002/route' \
  -H 'Content-Type: application/json' \
  -d '{"locations":[{"lat":39.9068,"lon":116.3915},{"lat":39.9072,"lon":116.3925}],"costing":"pedestrian"}'
```

骑行：

```bash
curl 'http://localhost:8002/route' \
  -H 'Content-Type: application/json' \
  -d '{"locations":[{"lat":39.9072,"lon":116.3925},{"lat":39.9080,"lon":116.3930}],"costing":"bicycle"}'
```

## 6. mesh 分块策略

### 合并模式 `merged`

适用于 Valhalla 一次性构建全区域 tiles。所有 mesh 的 way 会写入一个 OSM 文件。推荐生产构建使用此模式，避免跨 mesh 边界断连。

### 分块模式 `by_mesh`

按 `MESH` 字段输出多个 `.osm` 文件，适用于局部质检、增量检查和问题定位。不建议直接逐 mesh 独立构建 Valhalla tiles，因为边界处可能缺少邻接 mesh 的连接道路。

### 双输出 `both`

推荐默认模式。用于同时满足全量构建和分块质检。

## 7. 质量检查重点

1. 坐标必须是 WGS84 经纬度，即 EPSG:4326。
2. 每条 way 至少包含两个 node。
3. 禁行、施工中、私有道路的处理策略必须和业务策略一致。
4. 跨 mesh 道路建议进入合并文件构建，避免边界断路。
5. 如果原始 Shapefile 已有拓扑节点表，可后续扩展为按 FNODE/TNODE 或 ENTER_ID 对齐节点，以提高跨线连通性。
