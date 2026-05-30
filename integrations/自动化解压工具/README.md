# 自动解压工具

全自动游戏压缩包解压工具，监控下载目录 → 识别格式 → 密码尝试 → 解压 → 识别游戏 → 整理到游戏库，全程无需人工干预。

## 功能特性

- **目录监控**：实时监控下载目录，自动检测新压缩包
- **多格式支持**：ZIP、7Z、RAR、ISO、LZ4 等
- **分卷 SFX 原生解压**：Python 原生处理 Bandizip 分卷自解压包（`.exe + .e01 + .e02`），无需安装第三方软件
- **AES 加密 + XZ/LZMA2**：支持 AES-256 加密 ZIP 和 compress_type=95 (XZ/LZMA2) 压缩
- **伪装压缩包检测**：自动识别 MP4/AVI/JPG 等伪装的 ZIP/RAR/7Z 压缩包
- **7z 分卷组**：自动识别 `.7z.001 + .002` 分卷组，整体解压
- **智能密码尝试**：固定优先级（6868 > 9）+ 成功次数排序，自动匹配密码
- **嵌套解压**：自动递归解压嵌套压缩包，识别游戏目录后自动停止
- **游戏目录识别**：剥空壳简化路径，只输出1个游戏根目录到游戏库
- **同名覆盖**：重复解压同名游戏直接覆盖，不生成 `_1/_2` 后缀
- **验收报告**：每次运行自动生成简易摘要 + 详细报告
- **REST API**：提供 API 接口手动触发和状态查询

## 快速开始

### 运行方式

```bash
# 双击启动（推荐）
start.bat

# 命令行启动
python main.py                    # 启动监控 + API
python main.py --scan             # 启动时先扫描已有文件
python main.py --no-watch --scan  # 仅扫描一次，不启动监控
```

### 配置说明

编辑 `config/config.yaml`：

```yaml
directories:
  watch: "D:\\Download\\galgame"        # 监控目录
  target: "D:\\Download\\galgame\\_extract"  # 解压输出目录
  archive: "D:\\Download\\galgame\\_archive" # 已处理归档目录
  failed: "D:\\Download\\galgame\\_failed"   # 失败文件目录
  temp: "D:\\Download\\galgame\\_temp"       # 临时目录（建议与监控目录同盘）
  game_save: "E:\\private\\galgame"          # 游戏最终存放目录

extraction:
  max_recursive_depth: 3               # 嵌套解压最大深度

post_process:
  enabled: true
  move_game_dir: true
  game_detection:
    enabled: true
    min_size_mb: 200                   # 游戏目录最小体积（MB）
```

### 密码本

编辑 `config/passwords.json`：

```json
{
  "passwords": ["6868", "9", "唯ai雪莉酒", "风花雪月"]
}
```

密码尝试顺序：6868 最优先 → 9 次之 → 其余按成功次数降序

## 解压流程

```
扫描监控目录
    ↓
格式识别（magic签名 → 扩展名 → 伪装检测）
    ↓
┌─ 分卷SFX(.exe+.e01) → Python原生合并修补解压
├─ 7z分卷(.001+.002)  → 7za整体解压
├─ 伪装压缩包(MP4等)  → 偏移定位 + ZIP解压
├─ LZ4压缩包          → 7za外层解压 + 内层解压
└─ 常规压缩包          → 7za解压
    ↓
密码尝试（无密码 → 空密码 → 密码本）
    ↓
嵌套检测（后缀拦截 .apk/.xlsx 等 + 体积过滤 <200MB）
    ↓
游戏目录识别（剥空壳 → 找根目录 → 排除安卓/小目录）
    ↓
移动到游戏库（同名覆盖）
    ↓
归档原压缩包 + 生成验收报告
```

## 目录结构

```
自动化解压工具/
├── core/                         # 核心模块
│   ├── extractor.py              # 解压引擎
│   ├── archive_detector.py       # 格式识别 + 分卷检测 + 伪装检测
│   ├── file_manager.py           # 游戏目录识别 + 文件管理
│   ├── password_manager.py       # 密码管理（优先级 + 成功排序）
│   ├── report_generator.py       # 验收报告生成
│   ├── watcher.py                # 目录监控服务
│   ├── config.py                 # 配置管理
│   └── logger.py                 # 日志 + 控制台输出
├── api/                          # REST API
│   ├── app.py
│   ├── models.py
│   ├── middleware.py
│   └── routes/
├── config/
│   ├── config.yaml               # 主配置
│   └── passwords.json            # 密码本
├── bin/
│   └── 7za.exe                   # 7-Zip CLI
├── extract_report/               # 验收报告输出目录
├── main.py                       # 主入口
├── start.bat                     # 启动脚本
└── requirements.txt
```

## 过滤规则

### 嵌套解压拦截

| 规则 | 说明 |
|------|------|
| 后缀黑名单 | `.apk` `.xlsx` `.doc` `.gz` `.bz2` `.tar` 等直接跳过 |
| 体积过滤 | 非分卷单文件 <200MB 跳过，分卷组计算总大小 |
| 安卓排除 | 含 `AndroidManifest.xml` / `classes.dex` 的目录不处理 |
| 深度兜底 | 最大嵌套3层，到达强制停止 |

### 游戏目录判定

| 规则 | 说明 |
|------|------|
| 空壳剥除 | 只含1个子目录且无exe/dll的中间目录自动跳过 |
| 有效条件 | 含 `.exe` 或游戏引擎数据（`.ypf` `.xp3` `.rpa` 等）或 ≥200MB |
| 安卓排除 | 含安卓特征文件的目录不视为游戏 |
| 唯一输出 | 每个压缩包只输出1个游戏根目录 |

## 技术栈

- Python 3.11+
- 7-Zip CLI — 常规压缩包解压核心
- pyzipper — AES 加密 ZIP 解压
- lz4 — LZ4 帧格式解压（.zip.lz4 外层处理）
- lzma — XZ/LZMA2 压缩解压（compress_type=95）
- FastAPI + Uvicorn — REST API
- Watchdog — 目录监控
- Loguru — 日志管理
- Rich — 控制台美化

## 安装依赖

```bash
pip install -r requirements.txt
```

## API 接口

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/health` | 服务状态 |
| POST | `/api/extract/path` | 指定路径解压 |
| POST | `/api/extract/upload` | 上传文件解压 |
| GET | `/api/passwords` | 查询密码本 |
| POST | `/api/passwords` | 新增密码 |
| GET | `/api/logs/today` | 查询当日日志 |
| POST | `/api/scan` | 手动触发扫描 |

API 文档：`http://localhost:9600/docs`

## 注意事项

1. **7-Zip**：常规压缩包依赖 `bin/7za.exe`，请确保存在
2. **磁盘空间**：分卷合并会创建与源文件总大小相当的临时文件，建议临时目录与监控目录在同一磁盘
3. **权限**：确保对监控目录、解压目录和游戏保存目录有读写权限
4. **同名覆盖**：重复解压同名游戏会**删除旧目录**再移动新目录，请注意数据安全

## 已知限制（后续优化）

| 问题 | 说明 | 影响 |
|------|------|------|
| 空壳剥除不彻底 | 伪装压缩包（如 MP4 伪装 ZIP）解压后，嵌套层级较深时可能只剥到中间目录（如 `08`），未能定位到最终游戏目录名 | 游戏目录名不精确，但内容完整 |

## 许可证

MIT License
