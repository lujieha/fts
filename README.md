# fts

`fts` 是一套面向 Valhalla 的本地 Shapefile 到 OSM XML 转换工具，用于把车行道路、步行设施、骑行设施转换为 Valhalla 可构建 routing tiles 的 OSM 标签体系。

## 数据来源

当前默认支持两类输入：

- 车行：`RoadSegment.shp`，核心字段包括 `ROAD_ID`、`NAME_CHN`、`ROAD_CLASS`、`DIRECTION`、`MAX_SPEED`、`VEHICLE`、`STATUS`、`FORM_WAY`、`LINK_TYPE` 等。
- 步骑：`WALK_LINK.shp`，核心字段包括 `MESH`、`LINK_ID`、`WF_TYPE`、`DIRECTION`、`NAVITYPE`、`BICYCLE`、`BI_DIR`、`BW_MARK` 等。

两类数据均可通过 `MESH` 字段做分块输出。

## 安装

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .
```

依赖：`geopandas`、`shapely`、`pyproj`、`pyyaml`、`lxml`。

## 快速运行

```bash
fts-shp2osm \
  --config config/default.yaml \
  --road data/RoadSegment.shp \
  --walk data/WALK_LINK.shp \
  --out-dir out \
  --mode both
```

输出：

- `out/valhalla_input.osm`：合并后的 OSM XML，推荐用于 Valhalla 全量构建。
- `out/mesh/<MESH>.osm`：按 mesh 分块的 OSM XML，适用于质检和增量排查。
- `*.stats.json`：统计信息。

## 输出 OSM 标签示例

车行：

```xml
<way id="-1000001" visible="true">
  <nd ref="-1"/>
  <nd ref="-2"/>
  <tag k="highway" v="primary"/>
  <tag k="name" v="示例主路"/>
  <tag k="oneway" v="yes"/>
  <tag k="maxspeed" v="60"/>
  <tag k="lanes" v="3"/>
  <tag k="motor_vehicle" v="yes"/>
</way>
```

步行：

```xml
<way id="-1000002" visible="true">
  <nd ref="-4"/>
  <nd ref="-5"/>
  <tag k="highway" v="footway"/>
  <tag k="foot" v="yes"/>
  <tag k="motor_vehicle" v="no"/>
</way>
```

骑行：

```xml
<way id="-1000003" visible="true">
  <nd ref="-5"/>
  <nd ref="-3"/>
  <tag k="highway" v="cycleway"/>
  <tag k="bicycle" v="yes"/>
  <tag k="oneway:bicycle" v="no"/>
</way>
```

完整示例见 `examples/sample.osm`。

## Valhalla 验证

详见 `docs/valhalla_validation.md`。核心流程：

```bash
xmllint --noout out/valhalla_input.osm
osmium cat out/valhalla_input.osm -o out/valhalla_input.osm.pbf -f pbf,add_metadata=false --overwrite
valhalla_build_config --mjolnir-tile-dir valhalla_tiles --mjolnir-tile-extract valhalla_tiles.tar > valhalla.json
valhalla_build_tiles -c valhalla.json out/valhalla_input.osm.pbf
valhalla_service valhalla.json 1
```

## 可配置参数

主要配置位于 `config/default.yaml`：

- `inputs.road`：车行 Shapefile 路径。
- `inputs.walk`：步骑 Shapefile 路径。
- `output.mode`：`merged`、`by_mesh`、`both`。
- `output.split_key`：默认 `MESH`。
- `geometry.target_crs`：默认 `EPSG:4326`。
- `defaults.drop_forbidden`：是否丢弃禁行、施工中、不可通行记录。
- `defaults.include_private_roads`：是否保留私有/内部道路。
- `field_aliases`：字段别名映射，用于适配 DBF 字段名截断、空格、下划线差异。

## 设计说明

1. 生成 OSM 使用负数 ID，避免和真实 OSM 数据 ID 冲突。
2. 坐标默认输出 WGS84 经纬度。
3. 同一坐标点会复用同一个 OSM node，以提高连通性。
4. 推荐使用 `both` 模式：合并文件用于 Valhalla 构建，mesh 文件用于质检。
5. 后续可扩展 RoadNode、WALK_ENTER、RoadRule、RoadNodeMaat 等表，进一步支持节点拓扑、转向限制、时间限制、限高限宽限重等高级 routing 约束。
