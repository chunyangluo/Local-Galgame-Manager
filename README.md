# Local Galgame Manager

面向 **Windows 10/11** 的本地 Galgame 启动器与元数据管理工具：**以 VNDB 为主、Bangumi 为辅** 补全信息，支持大库扫描、封面缓存与多用户数据隔离。

---

## 项目简介

- 配置**扫描根目录**，自动识别游戏文件夹与启动 `exe`
- 扫描后可选 **VNDB 批量导入**（多线程），失败或缺图时自动尝试 **Bangumi** 元数据/封面
- **封面**：在线缓存（含重试与回退）、本地智能匹配、手动指定；策略可在「仅本地 / 本地优先 / 网图优先」间切换
- **用户覆盖优先**：手动修改的**显示名、启动路径、封面**持久保存，不会被扫描/VNDB 覆盖（见下文「数据与优先级」）
- **游戏库**：网格/列表视图、搜索、仅收藏、收藏与分类、游玩记录、备份/恢复
- **系统**：托盘、开机自启、为单个游戏创建桌面快捷方式
- **无 UI CLI**：扫描、入库、VNDB 导入与 JSON 摘要
- **自检**：`app.feature_selftest` 一键冒烟（可选联网/UI）

更细的操作说明见 **`docs/USER_GUIDE.md`**；插件开发见 **`docs/PLUGIN_GUIDE.md`**。

---

## 数据与优先级（重要）

### 运行时数据目录

GUI 与 CLI 使用**同一套**数据目录解析逻辑（`app/services/app_data_dir.py`）：

| 环境 | 路径 |
|------|------|
| 一般情况 | `%LOCALAPPDATA%\LocalGalgameManager\data\` |
| 无 `LOCALAPPDATA` 时 | `%USERPROFILE%\AppData\Local\LocalGalgameManager\data\` |

其中包含：

- **`manager.sqlite3`**：游戏库、扫描根、用户、设置、收藏与分类、游玩记录、VNDB 等字段
- **`covers/`**：封面缓存（含 VNDB CDN、在线 Bangumi 等子目录）
- **`plugins/`**：外部扫描插件（可选）
- **`system_config.json`** 等系统侧配置

首次启动会**尽力迁移**旧版放在「当前工作目录」或 exe 旁 `data/` 下的文件（**只补缺、不覆盖**已有新数据）。

### 手动修改的优先级

- **名称 / 启动 exe**：存于 `custom_name`、`custom_launch_exe`，列表与启动时优先于扫描结果。
- **手动封面**：存于 `custom_cover_path`，优先于自动/`cover_path` 缓存路径。

---

## 功能概览（与当前实现对齐）

### 扫描与元数据

- 多扫描根、管理对话框（添加/删除/清空）；清空全部根目录时会按设计清理库数据（见代码与 USER_GUIDE）
- 扫描结束后可触发 **VNDB 导入**；**未匹配 VNDB 的条目仍会入库**，避免「扫到 40 条只剩 20 条」类丢失
- **VNDB**：公开 Kana API（无 token），内置限速与重试；**Bangumi**：在 VNDB 失败或**无封面图 URL** 等情况下作为补充
- **封面链路**：主图源下载失败时会重试并按名称走 Bangumi；仍失败则尝试**本地目录**智能选图；UI 侧另有后台修补与「重新获取封面」菜单项

### 界面

- **两行工具栏**：第一行「找游戏」「库」；第二行「账户」「显示」「系统」+ **「更多」**（备份、恢复、插件、Locale Emulator 等）
- 列表**分批渲染**，大库时保持可交互；状态栏与进度条显示扫描/VNDB 进度

### 插件

- 扫描结果可经**内置 + 外部插件**变换后再入库
- **运行时**外部插件目录：`%LOCALAPPDATA%\LocalGalgameManager\data\plugins\`（与上表数据根一致）
- 说明与示例：**`docs/PLUGIN_GUIDE.md`**

### Locale Emulator（LE）转区启动

本功能**不是** `data/plugins/` 下的 Python 扫描插件，而是可选的 **Windows 转区启动**：通过已安装的 [Locale Emulator](https://github.com/xupefei/Locale-Emulator/releases) 调用其 **`LEProc.exe`** 以日文区域等环境运行游戏（上游仓库已归档，**Releases** 仍可下载安装包）。

**配置步骤**

1. 在本机安装 Locale Emulator（解压或安装到任意目录，确保该目录下有 **`LEProc.exe`** 及 LE 自带 DLL）。
2. 打开本程序，点击顶部 **「更多」→「Locale Emulator (LE)…」**。
3. 在对话框中填写或 **「浏览…」** 选择 LE 安装目录下的 **`LEProc.exe`**，确定保存。  
   - 留空并确定可清除配置，之后仅保留普通启动。
4. 保存路径写入数据库字段 **`locale_emulator_leproc_path`**（与游戏库同库，见上文「数据与优先级」中的 `manager.sqlite3`）。

**使用方式**（配置成功且路径有效后）

| 入口 | 说明 |
|------|------|
| 游戏列表 **右键菜单** | **「LE 转区启动」**（未配置时该项为灰色不可用） |
| **游戏详情** 窗口 | **「LE 转区启动」** 按钮；调试区会显示当前配置的 `locale_emulator_leproc_path` |
| **游玩历史** 窗口 | 每条记录旁的 **「LE」** 按钮 |

启动时本程序执行 **`LEProc.exe` + 游戏 exe 的绝对路径**（与 LE 官方命令行约定一致），由 LE 按自身规则选择 per-game `.le.config`、全局配置或默认日文环境。游戏退出后仍会写入**游玩记录**（与普通启动相同）。

更细的说明（与扫描插件的区别）见 **`docs/PLUGIN_GUIDE.md`** 末尾「Locale Emulator」一节。

---

## 技术栈

- Python 3.12+（开发与当前 CI/打包环境）
- PySide6（Qt6）
- SQLite（`sqlite3`）
- PyInstaller（Windows 可执行文件）
- requests / Pillow 等（见 `requirements.txt`）

---

## 环境要求与从源码运行

```bash
pip install -r requirements.txt
python -m app.main
```

在项目根目录执行；数据会写入上述 **LocalAppData** 下的 `data`，与是否从 IDE、终端或打包 exe 启动无关。

---

## 命令行（无 UI）

输出 JSON 到终端：

```bash
python -m app.cli --root "D:\Games\Galgame" --json
```

写入文件（UTF-8）：

```bash
python -m app.cli --root "D:\Games\Galgame" --json --output "scan_result.json"
```

扫描并写入数据库：

```bash
python -m app.cli --root "D:\Games\Galgame" --import-db
```

VNDB 批量导入（多线程）并入库，附带摘要 JSON：

```bash
python -m app.cli --root "D:\Games\Galgame" --vndb-import --threads 6 --import-db --json
```

参数说明以 **`python -m app.cli --help`** 为准。

---

## 功能自检

```bash
python -m app.feature_selftest
```

可选联网与 UI 冒烟，并输出 JSON 报告：

```bash
python -m app.feature_selftest --with-network --with-ui --json
```

---

## Windows 打包

在项目根目录执行：

```powershell
./build.ps1
```

脚本会：

1. 尝试结束已运行的 `LocalGalgameManager` 进程，避免文件占用导致打包失败  
2. 使用**带时间戳**的输出目录，避免覆盖正在使用的旧构建  
3. 安装依赖后调用 PyInstaller  
4. 仅在**构建成功**后更新桌面快捷方式 **`Local Galgame Manager.lnk`**，指向本次生成的 `LocalGalgameManager.exe`

**本次构建产物路径**形如：

```text
dist\builds\<yyyyMMdd-HHmmss>\LocalGalgameManager\LocalGalgameManager.exe
```

控制台会打印 `Build output: ...` 完整路径。旧路径 `dist\LocalGalgameManager\` 若仍存在，可为历史构建；以脚本打印的目录为准。

---

## 仓库与文档索引

| 路径 | 内容 |
|------|------|
| `docs/USER_GUIDE.md` | 用户操作、扫描、VNDB、备份等 |
| `docs/PLUGIN_GUIDE.md` | 插件接口与放置位置 |
| `docs/DB_DESIGN.md` | 数据库设计说明 |
| `docs/RELEASE_CHECKLIST.md` | 发布检查清单 |
| `CHANGELOG.md` | 版本变更记录 |

---

## 开源协作（分支约定）

- `main`：发布分支  
- `dev`：集成开发  
- `feature/*`：功能分支  
- `hotfix/*`：线上修复  

具体以仓库实际策略为准。

---

## 许可证

见仓库根目录 **`LICENSE`**。
