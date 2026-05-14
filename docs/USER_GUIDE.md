# 用户使用手册（V2）

## 启动

- 安装依赖：`pip install -r requirements.txt`
- 启动程序：`python -m app.main`

## 日常使用流程

1. 点击「添加目录」，选择游戏根目录。
2. 点击「全量扫描」，识别本地游戏并自动执行 VNDB 批量导入（默认 6 线程）。
3. 导入结束后查看结果弹窗（成功/失败统计与失败原因）。
4. 在列表中双击或右键启动游戏；需要时可用「管理员启动」或「LE 转区启动」。

## 存档管理（V2）

### 入口

- 游戏列表右键：`存档管理…`
- 游戏详情窗口：`存档管理…`

### 功能

- 手动指定存档目录并保存到 `custom_save_root`
- 自动发现候选路径（内置规则 + 启发式扫描 + **可选 2DFan 线索库**）
- 一键打开存档目录
- 备份为 ZIP（写入 `save-backups/<user_id>/<game_id>/`）
- 还原所选 ZIP（覆盖前自动创建“还原前自动备份”）
- 备份列表：时间、名称、大小、重命名、删除
- 备份/还原均为后台任务，窗口显示进度与当前文件
- **2DFan 联动（可选）**：
  - 使用本仓库 **`tools/2dfan-save-crawler`** 抓取并生成 SQLite 后，在主程序 **「更多」→「2DFan 线索库与爬虫…」** 或 **存档管理** 窗口配置该文件路径（全局一次即可）
  - 自动发现时若库中标题与当前游戏能对上，且解析出的文件夹在您电脑上存在，会作为候选列出（带 **`[2DFan]`** 前缀）；线索仅供参考，请自行核对后再「保存路径」

### 自行构建 2DFan 线索库（方法 B）

在**本仓库**内用自带爬虫生成 `data/2dfan_saves.sqlite3`，再回主程序配置路径即可。

1. 终端进入目录（按你的克隆路径修改）：
   - Windows：`cd …\Local-Galgame-Manager\tools\2dfan-save-crawler`
2. 安装爬虫依赖（首次）：
   - `pip install -r requirements.txt`
3. 初始化数据库：
   - `python -m dfan_save_crawler init --db data/2dfan_saves.sqlite3`
4. 抓取列表与详情（示例：从第 1 页起共爬 10 页；默认只处理标题含「存档」的条目）：
   - `python -m dfan_save_crawler crawl --max-pages 10`
   - 与上面等价写法（显式数据库路径）：`python -m dfan_save_crawler crawl --db data/2dfan_saves.sqlite3 --max-pages 10`
   - 可选：加 `--delay 1.5` 降低请求频率；遇 **HTTP 403** 时见该目录下 `README.md`（`--curl-cffi` / `--cookie` / **HTTP_PROXY、HTTPS_PROXY** 等）
5. 生成文件位置：`tools/2dfan-save-crawler/data/2dfan_saves.sqlite3`
6. 回到主程序：**「更多」→「2DFan 线索库与爬虫…」**（或**存档管理**里）填入该文件并保存；再对该游戏使用**自动发现**。

### 自动备份（启动前）

- 系统区有开关：`启动前备份: ON/OFF`
- 开启后，启动游戏前会尝试对 `custom_save_root` 自动打包备份
- 存档目录为空或无效时会自动跳过，不阻塞游戏启动

### 校验与安全

- 每个 ZIP 备份都会记录 `SHA256`
- 还原前先校验；若校验不通过会阻止还原，避免损坏包覆盖当前存档

## VNDB 批量导入（无鉴权）

- 顶部工具栏提供 `VNDB 导入` 按钮，可对当前库再次补全元数据
- 导入后可写入：
  - 标题（原文/本地化）
  - 简介、评分、平台、语言
  - 主封面 URL、截图 URL 列表
- 封面策略：
  - 优先使用缓存封面
  - 缓存缺失时用在线 URL 占位并触发后台修复

## VNDB 失败原因说明

- `timeout`：请求超时
- `no_match`：未匹配条目
- `http_error`：接口返回 HTTP 错误
- `parse_error`：返回结构异常
- `rate_limit`：触发限流
- `network_error`：本地网络不可用

## 常用功能

- 修正启动 EXE
- 收藏 / 取消收藏
- 新建分类 / 分配分类（逗号分隔）
- 设置封面（本地导入）
- 创建桌面快捷方式
- 导出备份 / 恢复备份（数据库级）

## 运行建议（VNDB Public No-Auth）

- 默认 6 线程，适合常见批量导入
- 大量任务可能触发短时 `rate_limit`
- 失败条目可直接再次执行 VNDB 导入

## 多用户

- 右上角下拉切换本地用户
- 「新建用户」创建独立的收藏、分类、游玩记录与存档备份记录
