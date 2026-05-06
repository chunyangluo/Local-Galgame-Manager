# Local Galgame Manager

Local-first Galgame manager for Windows 10/11.

## 项目简介

`Local Galgame Manager` 是一个纯本地、离线可用的 Galgame 管理工具，核心目标是：

- 快速扫描游戏目录并识别启动入口
- 统一展示和启动游戏，减少手动找路径成本
- 支持用户手动纠错（自定义名称/启动路径），且优先级高于自动扫描
- 提供收藏、分类、游玩记录、备份恢复等基础管理能力

## V1.0 功能

- 扫描与导入
  - 支持指定扫描根目录
  - 智能识别游戏启动 `exe`
  - 过滤常见非游戏目录（补丁/修正/工具/运行库等）
  - 支持复杂嵌套目录结构（如 `PC/.../...`）
- 游戏库管理
  - 一键启动 / 管理员启动
  - 收藏、分类、搜索筛选
  - 封面自动匹配 + 手动设置
- 用户与数据
  - 多本地用户隔离
  - 游玩记录与时长统计
  - 备份导出与恢复
- 系统能力
  - 托盘最小化
  - 开机自启
  - 桌面快捷方式生成
- 无 UI CLI
  - 支持命令行扫描和导出 JSON/文件

## 技术栈

- Python
- PySide6
- SQLite
- PyInstaller

## 快速开始

```bash
pip install -r requirements.txt
python -m app.main
```

## 命令行扫描（无 UI）

输出 JSON 到终端：

```bash
python -m app.cli --root "E:\private\galgame" --json
```

导出到文件（UTF-8）：

```bash
python -m app.cli --root "E:\private\galgame" --json --output "E:\private\galgame\scan_result.json"
```

扫描并写入数据库：

```bash
python -m app.cli --root "E:\private\galgame" --import-db
```

## 打包

```powershell
./build.ps1
```

打包后输出目录：

- `dist/LocalGalgameManager/`

## 开源协作

- `main`: 发布分支
- `dev`: 集成开发分支
- `feature/*`: 功能开发
- `hotfix/*`: 线上修复
