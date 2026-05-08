# 插件系统说明

项目已支持扫描结果插件化扩展。

## 插件目录

- 外部插件目录：`data/plugins/`
- 文件命名：任意 `*.py`（以下划线开头的文件会被忽略）

## 插件接口

每个插件文件需要提供 `register()` 函数，返回一个插件实例。

插件实例必须包含：

- `name: str`
- `transform_scan_results(root, results, context) -> list`

其中 `results` 是扫描结果列表（每项包含 `game_name/game_dir/launch_exe`）。

## 示例

```python
from __future__ import annotations

from dataclasses import replace


class PrefixNamePlugin:
    name = "prefix_name"

    def transform_scan_results(self, *, root, results, context):
        output = []
        for item in results:
            output.append(replace(item, game_name=f"[本地] {item.game_name}"))
        return output


def register():
    return PrefixNamePlugin()
```

## 生效范围

- GUI 扫描：生效
- CLI 扫描：生效

## 启用/禁用插件

- 在主界面顶部点击 `插件管理`
- 勾选表示启用，取消勾选表示禁用
- 配置会持久化保存到本地数据库，重启后仍生效

