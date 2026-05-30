# HBE 解密工具（独立模块）

在**合法授权**前提下，离线解密 [Hexo Blog Encrypt](https://github.com/Mike-js/hexo-blog-encrypt)（HBE）保存的 HTML 页面。算法与随附的 `hbe.js`（浏览器端实现）一致。

**本文件夹可整体复制到任意路径单独使用**，不依赖上级仓库；所有路径均相对本目录解析。

## 与 Local Galgame Manager 集成

- 主程序入口：**「更多」→「HBE 解密工具…」**
- 服务桥接：`app/services/hbe_decrypt_service.py`
- 界面：`app/ui/dialogs/hbe_decrypt_dialog.py`
- 主程序需安装：`pip install cryptography`（已写入根目录 `requirements.txt`）

集成状态：**已接入主界面**（单文件 + 批量；AUTO 在后台线程运行）。

---

## 目录结构

```
hbe-decryptor/
├── README.md                 # 本文档（唯一说明入口）
├── requirements.txt          # Python 依赖
├── paths.py                  # 路径与环境变量（勿删）
├── decry-chunyang.py         # 单文件解密
├── batch_decrypt_known.py    # 批量解密
├── backup_script.py          # 备份（可选）
├── hbe.js                    # 前端加密参考
├── password_dict.txt         # 密码字典（一行一个，可自建）
├── password_dict.txt.example
├── candidates.txt            # 可选候选密码
├── candidates.txt.example
├── ciphertext/               # 批量模式：放入待解密 .html
├── output/                   # 运行后生成（可删）
│   ├── plaintext/            # 解密明文
│   ├── decrypt_report_*.txt
│   ├── failed_summary_report_*.txt
│   └── decrypt_summary_*.{csv,json}
└── backup/                   # 默认备份目录（运行后生成）
```

复制走时请至少包含：三个 `.py`、`paths.py`、`hbe.js`、`requirements.txt`、`ciphertext/`（可为空）。`password_dict.txt` 建议一并复制或从 `.example` 创建。

---

## 环境

- Python **3.8+**
- Windows / macOS / Linux 均可

```bash
cd hbe-decryptor
python -m pip install -r requirements.txt
```

---

## 单文件解密

在**本目录**下执行（密文路径可以是任意盘符的绝对路径）：

```bash
# 已知密码
python decry-chunyang.py "D:\path\to\encrypted.html" "your-password"

# AUTO：字典 → candidates.txt → 4～6 位纯数字穷举
python decry-chunyang.py "D:\path\to\encrypted.html" AUTO
```

### AUTO 顺序

1. `password_dict.txt` 中每条密码（失败不单独写报告，仅记日志）
2. `candidates.txt`（不存在则跳过）
3. 穷举 `1000`～`999999` 的纯数字字符串

成功后：

- 控制台打印报告路径
- 明文：`output/plaintext/plaintext_YYYYMMDD_HHMMSS.html`（已去掉 `<hbe-prefix></hbe-prefix>`）
- 密码会**追加**到 `password_dict.txt`（去重）

### 单文件输出说明

| 文件 | 说明 |
|------|------|
| `output/decrypt_report_*.txt` | 单次尝试报告（明确密码模式每次都有；AUTO 仅成功时） |
| `output/failed_summary_report_*.txt` | AUTO 字典/候选阶段失败汇总 |
| `output/plaintext/*.html` | 解密成功的明文 |

---

## 批量解密

将加密 HTML 放入 `ciphertext/`（**仅扫描该目录顶层** `*.html`，不递归子文件夹）。

```bash
# 默认：./ciphertext → ./output/plaintext
python batch_decrypt_known.py "your-password"

# 自定义目录
python batch_decrypt_known.py "your-password" "D:\ciphers" "D:\out\plain"
```

汇总写入 `output/` 根目录：

- `decrypt_summary_YYYYMMDD_HHMMSS.csv`
- `decrypt_summary_YYYYMMDD_HHMMSS.json`

| 字段 | 含义 |
|------|------|
| 解密结果 | 成功 / 失败 |
| 开始时间 | `YYYY-MM-DD HH:MM:SS` |
| 耗时 | 秒（3 位小数） |
| 错误信息 | 失败原因 |
| 尝试密码 | 本次使用的密码 |
| 文件大小 | 源文件字节数 |
| 文件名 | 源 `.html` 文件名 |

---

## 退出码

便于脚本/计划任务判断结果（PowerShell：`echo $LASTEXITCODE`）。

### `decry-chunyang.py`

| 码 | 含义 |
|----|------|
| 0 | 解密成功 |
| 1 | 参数不足 |
| 2 | 解密失败（含 AUTO 全部尝试失败） |
| 3 | 未安装 `cryptography` |

### `batch_decrypt_known.py`

| 码 | 含义 |
|----|------|
| 0 | 至少一个成功且无失败 |
| 1 | 目录中无 `.html` |
| 2 | 存在失败或全部失败 |
| 3 | 未安装 `cryptography` |

---

## 备份

运行 `decry-chunyang.py` 时会自动调用 `backup_script.py`（同目录导入失败则跳过）。

```bash
python backup_script.py
```

| 环境变量 | 作用 |
|----------|------|
| （默认） | 备份到本目录 `backup/` |
| `HBE_BACKUP_DIR` | 自定义备份目录，如 `D:\my-backup` |
| `HBE_BACKUP=0` | 禁用自动备份 |

备份文件：`password_dict.txt`、`decry-chunyang.py`、`candidates.txt`（可选）、`batch_decrypt_known.py`、`hbe.js`、`paths.py`。策略为覆盖复制。备份失败**不会**阻止解密继续。

---

## 常见问题

**路径含中文或空格**  
使用双引号包裹完整路径。

**提示未找到 hbeData**  
HTML 须含 HBE 特征：`<script ... data-hmacdigest="..." ...>十六进制密文</script>`。

**依赖已装仍报错**  
确认 `python -m pip show cryptography` 与运行脚本的是同一解释器。

**批量没有输出**  
确认 `ciphertext/` 下直接有 `.html` 文件。

**AUTO 数字穷举很慢**  
4 位约数千次、6 位可达近百万次；优先维护 `password_dict.txt` 与 `candidates.txt`。

**复制到新电脑后无法运行**  
在新目录执行 `pip install -r requirements.txt`；勿只复制 `.py` 而遗漏 `paths.py`。

---

## 合规

仅解密你有权访问的内容。`AUTO` 中的数字穷举仅适用于自有或已授权密文，不得用于未授权破解。

---

## 技术说明

- 密钥派生：PBKDF2-HMAC-SHA256，盐值与 `hbe.js` 中 `SALT_R` / `SALT_O` 一致。
- 加密：AES-256-CBC + PKCS#7。
- 校验：明文前缀 `<hbe-prefix></hbe-prefix>` + HMAC-SHA256。

修改算法时请同时核对 `hbe.js` 与本目录两个解密脚本。
