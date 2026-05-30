# 子项目名称

> 状态：草稿 | 可独立运行 | 已接入主程序

## 用途

（一句话说明本工具做什么。）

## 单独运行

```bash
cd integrations/子项目名称
pip install -r requirements.txt   # 若有
python -m your_package            # 或具体命令
```

## 与 Local Galgame Manager 对接

- **配置项**：（例如主程序 settings / 对话框中的路径）
- **产出物**：（例如 SQLite、JSON 目录）
- **主程序入口**：（菜单名、服务模块路径，未对接则写「待实现」）

## 依赖

- Python 3.10+
- （列出主要第三方库）

## 目录说明

```
.
├── README.md
├── requirements.txt    # 可选
├── pyproject.toml      # 可选
├── your_package/       # 或 src/
└── tests/              # 可选
```

## 备注

（许可证、已知限制、代理/Cookie 等运维说明。）
