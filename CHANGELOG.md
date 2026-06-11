# Changelog

## v2.2.1
- **帮助与首次引导**：新增分 tab 帮助对话框（快速入门、交互演示、功能手册、常见问题、工具与链接）；首次启动欢迎页；反馈邮箱与使用声明醒目展示。
- **BUG 修复**：FDM 启动时使用 `SW_SHOWNORMAL`，修复「打开 FDM / 添加任务」成功但界面无响应的问题；设置与 FDM 对话框补充官方下载链接。
- **发布安全**：自动化解压 `config.yaml` / `passwords.json` 首次运行复制到用户数据目录；仓库内仅保留空模板；`build.ps1` 增加发布前校验，阻止本机路径与密码记录入包。
- **视频内容**：扫描与启动支持 `content_type=video` 游戏目录。
- **界面优化**：帮助字体与对话框尺寸加大；一键工作流日志区最小高度与步骤区滚动布局优化；子对话框窗口层级统一（`dialog_presenter`）。
- **文档与截图**：README / 帮助主图与 `docs/assets/` 同步最新演示截图；扩展 `RELEASE_CHECKLIST.md` 新用户冒烟步骤。
- **测试**：pytest **211** 项全通过；功能自检 **14** 项全通过（含帮助与自动化解压 UI）。

## v2.2.0
- **BUG 修复**：启动失败时仅移除失败游戏的启动状态，不再误清所有游戏的 `_launching_game_ids`。
- **BUG 修复**：VNDB 限速器改为释放锁后再 sleep，修复多线程串行化问题，批量导入恢复真正并发。
- **BUG 修复**：`read_image_size_fast` 添加文件访问异常保护，防止文件被删除或权限变化时封面搜索崩溃。
- **BUG 修复**：`_merge_metadata` 添加 `fetchone()` 返回 None 检查，防止并发删除游戏时迁移事务崩溃。
- **BUG 修复**：`_collect_image_candidates` 中 `rglob` 添加权限错误保护，防止无权限子目录导致封面搜索崩溃。
- **界面优化**：全局样式表补全 `QScrollBar:horizontal`、`QToolTip`、`QSlider`、`QSpinBox`、`QDateEdit` 等控件样式。
- **界面优化**：主题管理器同步补全，浅色/深色主题自动适配新增控件。
- **界面优化**：进度条填充改为渐变色，视觉层次更丰富。
- **界面优化**：移除 `game_detail_dialog`、`delete_game_confirm_dialog`、`save_manager_window` 等对话框中的硬编码颜色，统一由全局主题控制。
- **界面优化**：卡片占位图渐变增加色阶，过渡更自然。
- **测试**：pytest **191** 项全通过；功能自检 **11** 项全通过。

## v2.0.12
- **解压类型分类处理**：`INSTALLER_NAMES` 移除 `launcher.exe`/`start.exe`（常见游戏启动器，非安装程序）；`detect_game_directory()` 仅在 ISO 展开后走安装程序检测路径，普通游戏不再被误标为"安装盘"；`guide_from_post_process()` 仅在 ISO 镜像展开时才触发安装引导，普通压缩包不再弹出 setup.exe 提示。
- **嵌套解压 ISO 感知**：`expand_disc_images_in_directory()` 检测嵌套解压中已展开的 ISO（`_disc_images/` 子目录），确保光盘安装提示正确触发。
- **善后优化**：归档/失败迁移后自动清理空父目录；游戏入库后自动提升单层包装目录（如 `5209-PC/Snow...` → `Snow...`）。
- **功能自检增强**：新增 5 项自检（path_utils、auto_extract_integration、iso_handler_basics、disc_install_guide、archive_detector），总计 **11** 项；pytest **191** 项全通过。
- **打包依赖修复**：`build.ps1` 从 `--hidden-import` 改为 `--collect-all`；`requirements.txt` 新增 `pydantic-settings`、`fastapi`、`uvicorn`、`python-multipart`。
- **配置默认值**：`DirectoriesConfig` 默认值改为空字符串，由 `auto_extract_service` 提供合理默认路径。

## v2.0.11
- **自动化解压增强**：RAR5 / 路径含 `[]` 回退系统 7-Zip 或 UnRAR；**ISO+MDS** 展开与 **setup.exe 安装引导**（建议子目录安装、整理散落安装）；桥接主程序事件与黄色操作面板。
- **隐藏游戏**：`Ctrl+H` 与右键隐藏；「更多」→「显示隐藏游戏」（默认关，重启不记忆）。
- **FDM**：工具箱 →「FDM 下载管理…」，配置 `fdm.exe`、打开 FDM、`--add` 添加任务。
- **托盘退出**：主窗口 × 最小化到托盘；托盘「退出程序」正确结束进程（`setQuitOnLastWindowClosed(False)`）。
- **自动化解压集成**：`integrations/自动化解压工具` 接入主程序；「更多」→「自动化解压工具…」支持目录配置（简洁/详细）、单次解压、扫描并解压（进度条、分文件反馈、可停止）、彩色日志与完成 Toast。
- **主界面体验**：工具栏分为「搜索与筛选 / 导入管理 / 视图与浏览」；统一主操作/辅助按钮样式；搜索历史下拉、游玩状态筛选与排序；分页显示总数/页码并支持跳转。
- **封面与卡片**：统一「暂无封面」占位、hover 提示与点击添加；联网拉取时卡片进度态；游玩次数/收藏 tooltip。
- **操作反馈**：轻量 Toast（备份、恢复、封面修复等）；错误弹窗附解决建议；扫描/VNDB 等保留进度条。
- **「更多」菜单**：按场景分组（高频操作、工具箱、设置）；备份/恢复与开机启动、启动前备份置于顶层可切换项。
- **测试**：新增自动解压、HBE、插件、路径迁移、删除服务等用例，全量 **166** 项通过。

## v2.0.10
- **HBE 解密集成**：`integrations/hbe-decryptor` 接入主程序；「更多」→「HBE 解密工具…」支持单文件（含 AUTO）与批量解密；依赖 `cryptography`。

## v2.0.9
- **插件系统 v1**：`BasePlugin` 多钩子（扫描变换/过滤、启动修改、生命周期）；插件包 `plugin.json` + `plugin.py`；示例插件自动安装到用户目录。
- **插件管理 UI**：显示版本/说明/钩子、打开目录、热重载、按插件名 JSON 配置（`plugin_configs`）。
- **脚手架**：`python scripts/scaffold_plugin.py <name>` 快速创建插件包。
- **文档**：重写 `docs/PLUGIN_GUIDE.md`。

## v2.0.8
- **数据管理**：「更多」→「数据管理…」浏览库内游戏并从库中删除；右键菜单与游戏详情均支持删除。
- **删除确认**：首次删除二次确认，可选「下次不再提示」；可选「同时删除游戏安装文件夹」；数据管理窗口可批量勾选删盘（跳过确认时仍有额外确认）。
- **路径规范化迁移**：`scripts/migrate_game_paths.py` / `python -m app.maintenance.migrate_paths` 合并因 `E:\` 与 `E:/` 等写法产生的重复记录，并统一 `root_dir` 与扫描路径。
- **稳定性修复**：备份恢复前关闭 SQLite 连接；删除游戏时先删磁盘再删库记录；删除安装目录时使用 `custom_launch_exe` 校验；`root_dir` 写入与增量扫描统一规范化；修复 `delete_games_not_in_scan` 的 `LIKE` 误匹配；启动后窗口标题捕获线程 `join`；每窗口独立 `_launching_game_ids`。

## v2.0.7
- **随机按钮优化**：紫粉渐变背景 + 脉冲呼吸灯效果，更加醒目。
- **随机逻辑改进**：改为完全独立的真随机模式（每次独立选择，支持重复选中）。
- **随机对话框增强**：新增「🔀 换一个」按钮，支持重新随机选择游戏。
- **视觉反馈增强**：网格视图卡片金色边框闪烁、列表视图紫色背景闪烁。
- **移除封面策略按钮**：简化工具栏布局。
- **帮助文档更新**：同步更新随机功能说明。

## v2.0.6
- **扫描器修复**：修复 `_should_skip_directory` 路径误判 BUG，现在只检查目录名而非完整路径。
- **测试覆盖**：新增 `test_cover_manager.py`、`test_vndb_service.py`、`test_search_service_full.py`，总计 136 个测试全部通过。
- **覆盖率统计**：接入 pytest-cov，核心模块覆盖率：scanner 93%、cover_manager 82%、search_service 100%。
- **CI/CD 配置**：添加 GitHub Actions 自动运行测试。
- **架构优化**：拆分 `MainWindow`（1500 行）为 6 个职责清晰的 Mixin（ScanMixin、VndbImportMixin、CoverMixin、LaunchMixin、GameActionMixin、ViewMixin），提升代码可维护性。

## v2.0.4
- **存档管理 V2**：独立窗口支持指定 `custom_save_root`、异步 ZIP 备份/还原、进度条、`SHA256` 校验与「启动前自动备份」开关（设置写入数据库）。
- **自动发现存档路径**：内置规则 + 启发式扫描；可选合并 **2DFan 线索库**（只读 SQLite，候选标记为 `[2DFan]`）。
- **2DFan 集成**：设置项 `twodfan_hints_db_path`；主窗口「更多」→「2DFan 线索库与爬虫…」向导；存档管理内快捷配置与库统计；`app/paths.py` 检测仓库内爬虫目录。
- **独立工具 `tools/2dfan-save-crawler`**：`dfan_save_crawler` CLI（init / crawl / export）、SQLite 表 `crawl_pages` / `save_hints`、请求限速、代理环境变量、`--cookie` / `--cookie-file`、首页预热与浏览器式请求头、403 调试提示；`scripts/configure_manager_twodfan.py` 一键写入管理器全局路径。
- **文档**：`README.md`、`docs/USER_GUIDE.md` 补充存档与 2DFan 自建流程。

## v2.0.3
- Fix persistent data reset issue by moving runtime data directory from `Path.cwd()/data` to `%LOCALAPPDATA%/LocalGalgameManager/data`.
- Unify data-dir resolution for both GUI (`app.main`) and CLI (`app.cli`) to ensure consistent library/config loading across launch methods.
- Add best-effort legacy data migration on startup (copy missing entries only, no overwrite) from old working-directory/executable-adjacent `data` folders.
- Improve startup crash dialog to show the actual absolute path of `startup.log`.

## v2.0.2
- Preserve local display names during VNDB imports (avoid forced English title overwrite).
- Stop automatic deletion of unmatched games during scan/VNDB workflow to prevent unexpected library shrink.
- Add `app.feature_selftest` module for one-command functional verification (DB, scanner, plugin, cover, VNDB parse, optional network/UI checks).
- Document self-test usage in README for faster release validation.

## v2.0.1
- Fix major UI freeze risk by removing synchronous network cover fetch from the UI thread.
- Add incremental game-card rendering in batches to keep the window responsive on large libraries.
- Improve cover fallback state when VNDB image cache is not ready (`等待缓存` placeholder).

## v2.0.0
- Switch to VNDB-first metadata import workflow with no-auth public API access.
- Add 6-thread VNDB batch import in UI with progress, cancellation, and result summary dialog.
- Extend database schema for VNDB metadata fields and add transactional `upsert_games_batch`.
- Support VNDB cover CDN integration with local cache and improved cover source labeling.
- Upgrade cover rendering with consistent ratio handling, centered crop strategy, and unified placeholders.
- Improve startup robustness and diagnostics; simplify single-instance behavior for stability.
- Add CLI VNDB import mode (`--vndb-import`, `--threads`) with structured summary output.
- Add plugin architecture for scan-result transformation (builtin + external plugins).
- Refine scanner exclusions to avoid importing project/build/dev folders as games.
- Update docs for VNDB-only workflow, operational limits, and plugin extension guide.

## v1.0.1
- Improve scanner accuracy for nested Galgame directory structures.
- Add scan-root management dialog (add/remove/clear) in UI.
- Support custom game name/start path overrides with higher priority than auto-scan.
- Fix desktop shortcut creation by generating Windows `.lnk` shortcuts with fallback.
- Exclude Local-Galgame-Manager project/build folders from scan results.
- Clear game library data when all scan roots are removed.

## v1.0.0
- Bootstrap project structure.
- Implement scanning/import and launcher foundations.
