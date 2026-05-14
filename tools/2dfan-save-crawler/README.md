# 2DFan 存档位置爬虫（独立工具）

从 [2DFan](https://2dfan.com/) 的 **下载资源页**（`/downloads/<id>`）抓取标题与正文，用规则抽取「存档位置 / 解压路径 / AppData 等」线索，写入 **独立 SQLite**，供主程序或其它脚本做离线匹配。

## 合规与使用前提

- 请先阅读站点 [robots.txt](https://2dfan.com/robots.txt) 与使用条款；本工具默认 **限速、小批量**，仅作个人整理与本地检索，请勿高频爬全站。
- 请求使用常见浏览器 `User-Agent`；可在 `dfan_save_crawler/fetch.py` 里调整 `X-DFan-Save-Crawler` 等标识。
- 解析结果为 **启发式**，不保证与每台机器路径一致；需人工复核后再写入主库 `custom_save_root`。

## 安装

```bash
cd tools/2dfan-save-crawler
pip install -r requirements.txt
# 或：pip install -e .
python -m dfan_save_crawler init --db data/2dfan_saves.sqlite3
```

## 初始化数据库

```bash
python -m dfan_save_crawler init --db data/2dfan_saves.sqlite3
```

## 爬取下载列表（分页）

从 `https://2dfan.com/downloads?page=N` 拉列表，再逐个打开详情页（默认只处理标题含「存档」的条目，可加 `--all` 全开）：

```bash
python -m dfan_save_crawler crawl --db data/2dfan_saves.sqlite3 --start-page 1 --max-pages 3 --delay 1.5
```

常用参数：

| 参数 | 说明 |
|------|------|
| `--delay` | 每次请求间隔秒数（默认 1.2） |
| `--all` | 不只爬标题含「存档」的，整页都进详情 |
| `--max-downloads` | 本次最多处理多少条详情（防止一次跑太大） |
| `--curl-cffi` | 使用 `curl_cffi` 模拟 Chrome TLS（需 `pip install curl_cffi`） |
| `--cookie` | 浏览器 **整段** `Cookie` 请求头（与开发者工具里复制的一致；值里可含多个 `=`） |
| `--cookie-file` | 从 UTF-8 文件读取同上内容，避免命令行转义；勿提交到 git，可用 `data/cookies.txt`（已在 `.gitignore`） |
| `--no-warm` | 跳过 GET `/` 预热（仅调试用；默认会先访问首页再拉列表） |

`httpx` 默认 **`trust_env=True`**，会读取环境变量里的代理（与常见工具一致）。在**同一终端会话**里先设置再运行 `crawl` 即可。

**CMD（示例端口按你本机修改）：**

```bat
set HTTP_PROXY=http://127.0.0.1:62871
set HTTPS_PROXY=http://127.0.0.1:62871
python -m dfan_save_crawler crawl --max-pages 3 --delay 1.5
```

（小写 `http_proxy` / `https_proxy` 在多数环境下也可被识别。）

**PowerShell：**

```powershell
$env:HTTP_PROXY = "http://127.0.0.1:62871"
$env:HTTPS_PROXY = "http://127.0.0.1:62871"
python -m dfan_save_crawler crawl --max-pages 3 --delay 1.5
```

使用 `--curl-cffi` 时，一般也会继承系统/环境里的代理设置；若仍失败，请核对本地代理软件是否允许 **127.0.0.1** 入站、端口是否与上一致。

## 导出为 JSONL（给主程序对接）

```bash
python -m dfan_save_crawler export --db data/2dfan_saves.sqlite3 --out hints.jsonl
```

## 数据库表结构（摘要）

- `crawl_pages`：每个 `download_id` 一页，存 URL、标题、简介、正文纯文本、抓取时间。
- `save_hints`：从正文抽取的线索（原文片段、类型、置信度），外键 `download_id`。

如遇列表页 **HTTP 403**，爬虫会先 **GET /** 预热再请求 `/downloads`（可用 `--no-warm` 跳过调试）。请依次尝试：

1. **`--cookie-file data/cookies.txt`**：从浏览器复制 **整段 Cookie**（需含较新的 `cf_clearance`），与浏览器 **同一网络 / 同一代理**。  
2. **`--curl-cffi`**：部分环境 TLS 指纹异常时可改善。  
3. 终端设置 **`HTTP_PROXY` / `HTTPS_PROXY`**（若浏览器走系统代理，命令行也需一致）。

403 时程序会打印 **`body_preview_ascii`**（避免 GBK 控制台乱码）；若仍无法判断，请用浏览器打开同一 URL 对比是否出现人机验证。

仍被拦截时，只能降低频率、缩小 `--max-pages`，或改用手动录入主程序 `custom_save_root`。

主程序侧后续可做：按游戏名 / VNDB 标题模糊关联 `crawl_pages.title`，再取 `save_hints` 中高置信度路径建议。

## 离线测试

```bash
cd tools/2dfan-save-crawler
pip install pytest beautifulsoup4
python -m pytest tests -q
```
