# 跨 mesh 拓扑连接

本项目已加入基于 `RoadNodeRoadCross` 的跨 mesh node 匹配框架。

## 输入字段

`RoadNodeRoadCross.shp` 需要包含：

- `MESH`
- `NODE` 或 `NODE_ID`
- `X_COORD`
- `Y_COORD`
- `BOUNDARY`

`BOUNDARY` 方向编码：

- `0`：图幅内
- `2`：上侧
- `4`：左侧
- `6`：右侧
- `8`：下侧

## 匹配逻辑

1. 读取当前 mesh 的边界 node。
2. 调用 `src/fts/topology.py` 中的 `get_neighbor_mesh(mesh, direction)` 计算邻接 mesh。
3. 在邻接 mesh 中查找相反边界：
   - `2` 对 `8`
   - `8` 对 `2`
   - `4` 对 `6`
   - `6` 对 `4`
4. 对比 `X_COORD/Y_COORD`，坐标一致则认为是同一个跨 mesh node。
5. 输出 `RoadSegment` 时，`FNODE/TNODE` 会优先使用归并后的 canonical node。

## 需要你补充的代码

`get_neighbor_mesh(mesh, direction)` 已保留为空方法：

```python
def get_neighbor_mesh(mesh: str, direction: int) -> Optional[str]:
    # TODO: 按你们内部 mesh 编码规则实现上下左右邻接 mesh 计算。
    return None
```

你只需要在该方法中实现 mesh 编码解析、行列偏移、重新编码即可。

## 配置

开启方式：

```yaml
topology:
  enabled: true
  node_coordinate_unit: "seconds"
  node_coordinate_precision: 7
  prefer_topology_nodes: true
```

并配置：

```yaml
inputs:
  road_node: "data/RoadNodeRoadCross.shp"
```

如果 `X_COORD/Y_COORD` 已经是十进制度，把 `node_coordinate_unit` 改成 `degrees`。
