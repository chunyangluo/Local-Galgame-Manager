# 插件系统说明（API v1）

插件用于在不修改主程序的前提下扩展扫描、过滤与启动等行为。GUI 扫描、CLI 扫描与启动流程均会调用已启用插件。

## 目录结构

| 位置 | 用途 |
|------|------|
| `app/plugins/builtin/` | 内置插件（随程序发布） |
| `app/plugins/examples/` | 示例插件（首次加载时复制到用户 `data/plugins/`，若不存在） |
| `<数据目录>/plugins/` | 用户外部插件（单文件 `.py` 或插件包文件夹） |

用户数据目录一般为：`%LOCALAPPDATA%\LocalGalgameManager\data\plugins\`

## 插件包（推荐）

```
plugins/
  my_plugin/
    plugin.json
    plugin.py
```

`plugin.json` 示例：

```json
{
  "name": "my_plugin",
  "version": "1.0.0",
  "description": "一句话说明",
  "author": "你的名字",
  "entry": "plugin.py",
  "min_api_version": 1
}
```

`plugin.py` 必须提供：

```python
def register():
    return MyPlugin()  # 实例
```

## 单文件插件（兼容旧版）

```
plugins/my_plugin.py
```

同样提供 `register()`；元数据可写在类属性 `name` / `version` / `description` 上。

## 快速创建骨架

```bash
python scripts/scaffold_plugin.py my_plugin --description "我的插件"
```

然后在主程序 **插件管理** 中启用。

## 推荐基类 `BasePlugin`

继承 `app.plugins.base.BasePlugin`，只重写需要的钩子（其余有安全默认实现）。

| 钩子 | 常量 | 说明 |
|------|------|------|
| `transform_scan_results` | `scan_transform` | 每个扫描根目录完成后，变换结果列表 |
| `should_include_scan_result` | `scan_filter` | 对每条候选返回 `False` 可丢弃 |
| `modify_launch` | `launch_modify` | 启动前调整 exe / LE / 管理员标志，或 `cancel=True` |
| `on_load` / `on_unload` | `on_load` / `on_unload` | 插件加载/重载生命周期 |
| `get_config_schema` | — | 预留：配置项说明（供未来 UI） |

### 上下文 `PluginContext`

- `data_dir` — 应用数据根目录  
- `config_for(plugin_name)` — 读取该插件在数据库中的 JSON 配置（`settings.plugin_configs`）

写入配置（程序内或自行调用数据库 API）：

```python
db.set_plugin_config("prefix_name", {"prefix": "[汉化]"})
```

## 示例：扫描改名

见 `app/plugins/examples/prefix_name/`。

## 示例：过滤 demo 目录

见 `app/plugins/examples/skip_demo_folders/`（`should_include_scan_result`）。

## 示例：启动钩子

```python
from app.plugins.base import BasePlugin, LaunchDecision, PluginContext

class MyLaunchPlugin(BasePlugin):
    name = "my_launch"

    def modify_launch(self, *, game_id, game_name, launch_exe,
                      locale_emulator, as_admin, context: PluginContext):
        # 强制管理员启动
        return LaunchDecision(
            launch_exe=launch_exe,
            locale_emulator=locale_emulator,
            as_admin=True,
        )
```

取消启动：

```python
return LaunchDecision(
    launch_exe=launch_exe,
    cancel=True,
    cancel_reason="维护中，暂不允许启动",
)
```

## 内置插件

| 名称 | 说明 |
|------|------|
| `normalize_scan_result` | 去重、修剪字段、规范化 `game_dir` 路径 |

## 启用 / 禁用 / 重载

- 主界面 **「更多」→ 插件管理**（或工具栏入口）
- 勾选启用；配置写入 `plugin_disabled_names`
- **重新加载** — 从磁盘重新扫描插件目录（无需重启程序）
- **打开插件目录** — 直接编辑外部插件

## API 版本

- 当前程序：`PLUGIN_API_VERSION = 1`
- 插件可声明 `api_version`；`plugin.json` 可写 `min_api_version`
- 版本不兼容时插件加载失败并在列表中显示错误

## 安全提示

⚠️ 外部 `.py` 插件与主进程**同一 Python 解释器、同一权限**，可访问本机文件与网络。请仅安装可信来源的插件。

## 与 Locale Emulator 的区别

**LE 转区** 是独立 Windows 工具，在「更多 → Locale Emulator (LE)…」中配置 `LEProc.exe`，**不是** `plugins/` 下的 Python 插件。启动类插件钩子发生在调用 LE/普通启动之前，可与 LE 组合使用。

## 生效范围

| 流程 | 扫描变换 | 扫描过滤 | 启动修改 |
|------|----------|----------|----------|
| GUI 全量/增量扫描 | ✓ | ✓ | — |
| CLI `python -m app.cli` | ✓ | ✓ | — |
| 游戏启动 | — | — | ✓ |
