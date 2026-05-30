# 外部插件目录

将插件放在本目录下，主程序启动时会自动加载（可在「插件管理」中启用/禁用）。

## 两种布局

### 单文件插件

```
plugins/
  my_plugin.py      # 内含 register() → 插件实例
```

### 插件包（推荐）

```
plugins/
  my_plugin/
    plugin.json     # 元数据（可选但推荐）
    plugin.py       # register()
```

`plugin.json` 示例：

```json
{
  "name": "my_plugin",
  "version": "1.0.0",
  "description": "简短说明",
  "entry": "plugin.py",
  "min_api_version": 1
}
```

## 快速创建

在仓库根目录执行：

```bash
python scripts/scaffold_plugin.py my_plugin
```

## 文档

完整 API 与钩子说明见仓库 **`docs/PLUGIN_GUIDE.md`**。

⚠️ 第三方 `.py` 插件可执行任意代码，请仅安装来源可信的插件。
