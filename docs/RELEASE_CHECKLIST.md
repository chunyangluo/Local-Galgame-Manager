# 发布检查清单

- [ ] `pip install -r requirements.txt`
- [ ] `python -m pytest -q`
- [ ] `python -m py_compile app/main.py`
- [ ] 手工验证：扫描导入、启动、收藏、分类、封面、备份恢复、用户切换
- [ ] 手工验证：数据管理删除、游戏详情删除、可选删安装目录
- [ ] （可选）`python scripts/migrate_game_paths.py` 预览旧库路径迁移
- [ ] 运行 `./build.ps1` 生成打包产物
- [ ] 更新 `CHANGELOG.md` / `README.md` 版本号
- [ ] 打 Tag（如 `v2.0.11`）
- [ ] 发布 Release（安装版/绿色版）
