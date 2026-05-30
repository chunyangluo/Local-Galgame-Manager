# integrations — 待整合 Python 子项目

本目录用于**存放、归档**计划并入 Local Galgame Manager 的独立 Python 项目（脚本、爬虫、小工具、服务等）。

与主程序的关系：

| 目录 | 用途 |
|------|------|
| **`integrations/`**（本目录） | 新建 / 迁入、尚未或正在对接主程序的子项目 |
| **`tools/`** | 已对接的独立工具（例如 `2dfan-save-crawler`） |
| **`app/plugins/`** | 主进程内插件（钩子扩展，轻量逻辑） |

主程序代码在 **`app/`**；不要把大型子项目直接塞进 `app/`，应保留为可单独运行、可单独测试的子仓库式目录。

## 目录约定

每个子项目占一个子文件夹，建议命名：`小写-连字符` 或 `snake_case`。

```
integrations/
  README.md                 # 本说明
  _template/                # 新建子项目时可复制的骨架
  my-awesome-tool/          # 你的项目（示例）
    README.md
    pyproject.toml          # 或 requirements.txt
    src/ 或 包名/
    tests/
```

### 子项目 README 建议包含

1. 项目用途（一句话）
2. 如何单独运行（`python -m ...` / CLI）
3. 与主程序如何对接（配置项、数据文件路径、是否调用 `app.services.paths`）
4. 依赖安装方式
5. 集成状态：`草稿` / `可独立运行` / `已接入主界面`

## 新建子项目

复制模板目录：

```bash
# 在仓库根目录
cp -r integrations/_template integrations/my-project
# Windows PowerShell:
Copy-Item -Recurse integrations\_template integrations\my-project
```

然后编辑 `integrations/my-project/README.md` 与代码；对接完成后可：

- 将说明链接写入 `docs/USER_GUIDE.md` / 主 `README.md`，或
- 视情况迁到 `tools/` 并在主程序中增加菜单/服务入口（参考 `tools/2dfan-save-crawler`）。

## 依赖与数据

- 各子项目优先使用**自己的** `requirements.txt` 或 `pyproject.toml`，避免污染主程序 `requirements.txt`，除非已正式合并依赖。
- 运行时数据、缓存、SQLite 等放在子项目下的 `data/`（已被仓库根 `.gitignore` 忽略），不要提交密钥或 Cookie。

## 集成方式（选型参考）

| 方式 | 适用场景 |
|------|----------|
| **独立 CLI + 主程序读其产出** | 爬虫、批处理、生成 SQLite/JSON（类似 2DFan 线索库） |
| **`app/plugins/` 插件** | 扫描/启动链路上的轻量逻辑 |
| **主程序 `app/services/` 调用子项目包** | 需深度耦合、但代码仍希望分目录维护时 |

## 与 `tools/` 的区别

- **`integrations/`**：工作台 / 归档区，项目可以尚不可用、文档先行。
- **`tools/`**：已约定路径、文档与主程序联动的成熟子工具。

现有 **`tools/2dfan-save-crawler`** 保持不变；新迁入项目请先放在本目录，完成对接后再考虑是否移至 `tools/`。

### 已集成

| 目录 | 主程序入口 |
|------|------------|
| `hbe-decryptor/` | 更多 → **HBE 解密工具…** |
| `自动化解压工具/` | 更多 → **自动化解压工具…**（扩展工具子菜单） |
