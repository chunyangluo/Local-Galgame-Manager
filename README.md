# Local Galgame Manager

**版本**: v2.2.1 | [下载最新版](https://github.com/chunyangluo/Local-Galgame-Manager/releases/latest)

<p align="center">
  <img src="docs/assets/main-window.png" alt="Local Galgame Manager 主界面" width="820" />
</p>

---

## 核心亮点

1. **Windows 10/11** 本地 Galgame 库：多根目录扫描、识别启动 `exe`、大库网格分页 + 列表分批渲染。
2. 元数据 **VNDB 为主、Bangumi 为辅**；封面在线缓存、重试与本地回退（仅本地 / 本地优先 / 网图优先）。
3. **手动修改的名称、启动路径、封面、存档路径不会被扫描或 VNDB 覆盖**；存档 ZIP 备份/还原、游玩记录、多用户与 CLI。
4. **扩展工具**：插件钩子、HBE 解密、**自动化解压**（含 ISO+MDS 光盘包与安装引导、RAR 多卷分包、验收报告）、**FDM 下载**、**一键工作流**（解压→扫描→导入）、**调试启动**、**数据管理**（文件管理+一键清空）等，均在「更多」菜单进入。

操作细节见 **`docs/USER_GUIDE.md`**；插件见 **`docs/PLUGIN_GUIDE.md`**；发布步骤见 **`docs/RELEASE_CHECKLIST.md`**。

---

## 数据目录（简）

| 项目 | 说明 |
|------|------|
| 数据根 | `%LOCALAPPDATA%\LocalGalgameManager\data\`（见 `app/services/paths.py` / `app_data_dir.py`） |
| 主要文件 | `manager.sqlite3`、`covers/`、`save-backups/`、`plugins/`（用户插件） |

**覆盖规则**：`custom_name` / `custom_launch_exe` / `custom_cover_path` / `custom_save_root` 优先于扫描与 VNDB；扫描不会覆盖这些字段。

---

## 功能概览

### 扫描与库

- 多扫描根、全量/增量扫描、扫描后 **VNDB 批量导入**（多线程，可取消）
- **增量扫描并增量 VNDB 导入** — 仅处理新游戏，最快方式
- **🚀 一键工作流** — 自动解压 → 增量扫描 → 增量 VNDB 导入，全流程一键完成
- **路径迁移**（一次性）：`python scripts/migrate_game_paths.py`（预览）→ `--apply --backup`
- **数据管理**：「更多」→「数据管理…」— 数据库管理（批量删除）+ 文件管理（目录概览、文件浏览、一键清空归档/失败目录）

### 主界面（v2.0.11）

| 区域 | 能力 |
|------|------|
| **搜索与筛选** | 关键词搜索（含历史记录下拉）、状态筛选（全部/收藏/已玩/未玩）、排序（更新/添加/游玩/名称） |
| **导入管理** | 添加目录、导入游戏（全量/增量/扫描+VNDB）、VNDB 导入、刷新 |
| **视图与浏览** | 网格/列表、随机、游玩历史、日志；网格底栏 **共 N 款 · 第 X/Y 页** + 页码跳转 |
| **游戏卡片** | 封面占位与加载态、hover 高亮、游玩次数/收藏说明、无封面可点击添加；**Ctrl+H** 或右键 **隐藏/取消隐藏** |

**「更多」菜单**（按场景分组）：管理目录、数据管理、新建用户、导出/恢复备份、开机启动与启动前备份开关、**显示隐藏游戏**（默认关，重启不记忆）→ 游戏详情/游玩历史 → **工具箱**（HBE、自动化解压、插件、LE、2DFan、**FDM**）→ 设置/界面设置。

**托盘**：点窗口 **×** 为最小化到托盘；托盘菜单 **「退出程序」** 才会结束进程。

### 界面截图

以下截图来自 `软件演示图片/`，发布前如界面有明显变化，请先更新该目录截图，再同步到 `docs/assets/` 与帮助页资源。

<p align="center">
  <img src="docs/assets/main-window.png" alt="主界面" width="820" />
</p>

<p align="center">
  <img src="docs/assets/quick-workflow.png" alt="一键工作流页面" width="620" />
</p>

| 功能 | 截图 |
|------|------|
| 自动化解压工具 | <img src="docs/assets/auto-extract.png" alt="自动化解压工具页面" width="420" /> |
| 随机选择 | <img src="docs/assets/random-picker.png" alt="随机选择页面" width="420" /> |
| 历史记录 | <img src="docs/assets/play-history.png" alt="历史记录页面" width="420" /> |
| 系统日志 | <img src="docs/assets/log-window.png" alt="系统日志页面" width="420" /> |
| Locale Emulator 配置 | <img src="docs/assets/locale-emulator-settings.png" alt="LE 配置页面" width="420" /> |

### 存档管理

- 右键或详情 **「存档管理…」**：指定 `custom_save_root`、ZIP 备份/还原（SHA256）、自动发现（含可选 2DFan 线索库）
- **启动前备份**：「更多」中 `启动前备份: ON/OFF`

### 扩展工具（`integrations/`）

| 工具 | 入口 | 说明 |
|------|------|------|
| **HBE 解密** | 更多 → HBE 解密工具… | `integrations/hbe-decryptor`，需 `cryptography` |
| **自动化解压** | 更多 → 自动化解压工具… | 监控目录、扫描解压（进度、可停止）；**RAR5 / 路径含 `[]`** 会回退系统 7-Zip/UnRAR；**ISO+MDS** 展开镜像后自动提示安装（仅光盘镜像触发，普通压缩包不会）；解压后自动清理空目录、提升单层包装目录；建议装到 `game_save` 下子目录，勿直接装到游戏库根目录；可 **整理散落安装**） |
| **FDM** | 工具箱 → FDM 下载管理… | 配置 `fdm.exe` 后打开 Free Download Manager 或 `--add` 添加任务 |
| **插件** | 工具箱 → 插件管理… | 扫描/启动钩子；`data/plugins/` + 示例包 |
| **2DFan** | 工具箱 → 2DFan 线索库 / 一键爬取 | 配合 `tools/2dfan-save-crawler` |

独立子项目说明见 **`integrations/README.md`**。

### Locale Emulator（LE）

安装 [Locale Emulator](https://github.com/xupefei/Locale-Emulator/releases) 后，**更多 → 工具箱 → Locale 模拟器 (LE)…** 配置 `LEProc.exe`；右键/详情 **LE 转区启动**。

---

## 技术栈

- Python 3.12+ · PySide6 · SQLite · PyInstaller · pytest + 功能自检（含 UI 冒烟）
- 主窗口 **Mixin 架构**：`scan` / `vndb_import` / `cover` / `launch` / `game_action` / `view`

---

## 快速开始

### 开发运行（源码）

```bash
pip install -r requirements.txt
python -m app.main
```

数据写入 `%LOCALAPPDATA%\LocalGalgameManager\data\`，与打包 exe **共用同一数据目录**。

### 打包版运行（日常推荐）

先执行一次 `./build.ps1`（见下节），之后可直接启动：

```powershell
dist\builds\latest\LocalGalgameManager\LocalGalgameManager.exe
```

`build.ps1` 会更新桌面快捷方式，并同步 `dist\builds\latest\` 为最近一次成功构建。

### CLI 速查

```bash
python -m app.cli --root "D:\Games\Galgame" --import-db
python -m app.cli --root "D:\Games\Galgame" --vndb-import --threads 6 --import-db --json
python -m app.feature_selftest          # 功能自检（11 项）
python -m app.feature_selftest --with-network  # 含 VNDB 网络检查
python -m app.feature_selftest --with-ui       # 含 UI 冒烟测试
```

完整参数：`python -m app.cli --help`

---

## Windows 打包

```powershell
./build.ps1
```

产物：

| 路径 | 说明 |
|------|------|
| `dist\builds\<yyyyMMdd-HHmmss>\LocalGalgameManager\` | 带时间戳的当次构建 |
| `dist\builds\latest\LocalGalgameManager\` | 稳定入口（快捷方式指向此处） |

`build.ps1` 开始前会尝试结束已运行的 `LocalGalgameManager` 进程。

---

## 发布收尾流程（维护者）

在项目根目录 **PowerShell** 中按序执行（版本号以当前发布为准，示例 **v2.0.12**）：

```powershell
# 0. 结束旧实例（源码 / 打包版进程名相同）
Stop-Process -Name LocalGalgameManager -Force -ErrorAction SilentlyContinue

# 1. 测试与源码冒烟
python -m pytest tests/ -q
python -m app.feature_selftest --with-ui --json

# 2. 打包（内含停进程 + pip + PyInstaller + 复制到 latest）
#    build.ps1 会校验自动化解压模板：禁止本机盘符路径、禁止密码/成功记录入包
./build.ps1

# 2b. 用临时 LOCALAPPDATA 模拟新用户首次启动
$exe = "dist\builds\latest\LocalGalgameManager\LocalGalgameManager.exe"
$tmp = Join-Path $env:TEMP ("lgm-release-smoke-" + [guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Path $tmp -Force | Out-Null
$oldLocalAppData = $env:LOCALAPPDATA
$env:LOCALAPPDATA = $tmp
$p = Start-Process -FilePath $exe -PassThru
Start-Sleep -Seconds 8
if ($p.HasExited) { throw "打包版首次启动后异常退出" }
Stop-Process -Id $p.Id -Force
$env:LOCALAPPDATA = $oldLocalAppData

# 2c. 人工检查新用户体验
# - 首次启动欢迎/帮助页可读，主界面截图正常
# - 添加目录 → 扫描 → 普通启动（可用临时 exe/cmd 冒烟）
# - 一键工作流与自动化解压 UI 可打开
# - 自动化解压运行时配置位于 %LOCALAPPDATA%\LocalGalgameManager\data\auto_extract\config\
# - FDM / LE / 2DFan / VNDB 等外部依赖在帮助页和设置中有清晰提示

# 3. 打 zip（将 BUILD_ID 与版本号替换为实际值）
$ver = "v2.0.12"
$buildId = (Get-ChildItem dist\builds -Directory | Sort-Object LastWriteTime -Descending | Select-Object -First 1).Name
$zip = "dist\builds\LocalGalgameManager-$ver-win64.zip"
Compress-Archive -Path "dist\builds\$buildId\LocalGalgameManager" -DestinationPath $zip -Force

# 4. 确认 CHANGELOG.md / README.md 版本与下载链接已更新

# 5. 提交并推送
git add -A
git status
git commit -m "v2.2.0: 综合设置对话框、密码本管理、菜单优化"
git push origin main

# 6. 标签与 GitHub Release（需 gh CLI 已登录）
git tag v2.2.0
git push origin v2.2.0
gh release create v2.2.0 --title "Local Galgame Manager v2.2.0" --notes-file CHANGELOG.md $zip
```

| 步骤 | 说明 |
|------|------|
| 测试 | `pytest` 与 `feature_selftest --with-ui` 全绿后再打包 |
| `build.ps1` | 打包前关闭正在运行的 exe，并阻止本机路径/密码记录进入发布包 |
| 新用户冒烟 | 必须用临时 `LOCALAPPDATA` 启动打包版，确认首次启动、数据目录、帮助页、扫描与自动化解压入口正常 |
| 版本 | 同步 `README` 顶部、`CHANGELOG` 首段、`gh release` 标签 |
| `gh` | [GitHub CLI](https://cli.github.com/) + `gh auth login` |

更细的检查项：**`docs/RELEASE_CHECKLIST.md`**。

---

## 文档索引

| 路径 | 内容 |
|------|------|
| `docs/USER_GUIDE.md` | 用户操作指南 |
| `docs/PLUGIN_GUIDE.md` | 插件开发 |
| `docs/DB_DESIGN.md` | 数据库设计 |
| `docs/RELEASE_CHECKLIST.md` | 发布清单 |
| `CHANGELOG.md` | 版本记录 |
| `integrations/` | HBE、自动化解压等子项目 |
| `tools/2dfan-save-crawler/` | 2DFan 线索爬虫 |
| `scripts/migrate_game_paths.py` | 路径规范化维护 |

---

## 分支约定

- `main`：发布分支  
- `dev` / `feature/*` / `hotfix/*`：按仓库实际策略使用  

---

## FAQ（节选）

**Q：改界面后要重启吗？**  
A：要。保存 `.py` 后需重新启动进程；「刷新」只重载数据库列表。

**Q：数据在哪？如何迁移？**  
A：`%LOCALAPPDATA%\LocalGalgameManager\data\`；可用 **更多 → 导出备份 / 恢复备份**。

**Q：VNDB 封面一直失败？**  
A：后台下载到 `covers/`；右键 **重新获取封面**；检查网络与封面策略（USER_GUIDE）。

**Q：游戏启动闪退？**
A：使用右键「调试启动」查看退出码和诊断建议；或在游戏详情中设置 LE 转区配置（per-game）。

**Q：自动化解压卡住？**
A：扫描页有进度条与「停止」；大文件/RAR5/ISO 耗时较长属正常，可看底部彩色日志。**仅光盘镜像（ISO+MDS）** 展开后会提示安装 setup.exe，普通压缩包不会弹出安装提示。安装时建议装到 **子文件夹**（勿装到游戏库根目录）。

**Q：归档目录占空间？**
A：「更多」→「数据管理」→「文件管理」→ 一键清空归档目录。

**Q：想一键完成下载→解压→导入？**
A：点击工具栏「🚀 一键工作流」，自动执行：解压监控目录 → 增量扫描 → 增量 VNDB 导入。

**Q：托盘点了退出还在？**  
A：请用托盘 **「退出程序」**；仅关主窗口 **×** 会最小化到托盘。

**Q：隐藏的游戏去哪了？**  
A：「更多」→ 打开 **「显示隐藏游戏」**（每次启动默认关闭）；或选中游戏按 **Ctrl+H** 取消隐藏。

**Q：同游戏两条记录？**  
A：运行 `python scripts/migrate_game_paths.py` 预览后 `--apply --backup`。

---

## 许可证

见仓库根目录 **`LICENSE`**。
