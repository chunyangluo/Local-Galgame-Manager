# 数据库设计（SQLite）

## 核心表
- `users`：本地账户。
- `settings`：全局配置与当前用户。
- `scan_roots`：扫描根目录配置。
- `games`：游戏主数据（名称、根目录、启动EXE、封面）。
- `play_records`：启动记录与时长。
- `favorites`：用户收藏关系。
- `categories`：用户自定义分类。
- `game_categories`：游戏与分类多对多关系。

## 设计要点
- `games.root_dir` 唯一，支持重复扫描时自动更新。
- 用户相关表均通过 `user_id` 隔离数据。
- 统计数据由 `play_records` 聚合得出，避免冗余写入。
