# 发布检查清单

## 自动检查

- [ ] `pip install -r requirements.txt`
- [ ] `python -m pytest tests/ -q`
- [ ] `python -m app.feature_selftest --with-ui --json`
- [ ] `python -m py_compile app/main.py`
- [ ] （可选）`python scripts/migrate_game_paths.py` 预览旧库路径迁移

## 打包前模板检查

- [ ] `integrations/自动化解压工具/config/config.yaml` 不包含维护者本机盘符路径（如 `D:\...` / `E:\...`）
- [ ] `integrations/自动化解压工具/config/passwords.json` 为空模板：`passwords`、`success_map`、`success_counts` 都为空
- [ ] `app/assets/help-main-window.png` 与 `docs/assets/main-window.png` 已同步为最新版主界面截图
- [ ] `docs/assets/` 中演示截图已从 `软件演示图片/` 更新

## 打包与包内容校验

- [ ] 运行 `./build.ps1` 生成打包产物
- [ ] `dist/builds/latest/LocalGalgameManager/LocalGalgameManager.exe` 存在
- [ ] `dist/builds/latest/LocalGalgameManager/_internal/app/assets/help-main-window.png` 存在
- [ ] `dist/builds/latest/LocalGalgameManager/_internal/integrations/自动化解压工具/bin/7za.exe` 存在
- [ ] 打包后的 `config.yaml` 不包含本机盘符路径
- [ ] 打包后的 `passwords.json` 仍为空模板

## 新用户体验冒烟

使用临时 `LOCALAPPDATA` 模拟新用户，避免复用维护者本机数据：

```powershell
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
```

- [ ] 首次启动欢迎/帮助页可读，反馈邮箱与郑重声明醒目
- [ ] 主界面截图、帮助页主图显示正常
- [ ] 添加目录 → 扫描 → 普通启动（可用临时 exe/cmd 冒烟）
- [ ] 一键工作流 UI 可打开，日志栏可读
- [ ] 自动化解压 UI 可打开，运行时配置生成到 `%LOCALAPPDATA%\LocalGalgameManager\data\auto_extract\config\`
- [ ] FDM / LE / 2DFan / VNDB 等外部依赖在帮助页和设置中有清晰提示
- [ ] 手工验证：收藏、隐藏、分类、封面、备份恢复、用户切换
- [ ] 手工验证：数据管理删除、游戏详情删除、可选删安装目录

## 发布资料

- [ ] 更新 `CHANGELOG.md` / `README.md` 版本号与截图
- [ ] 打 Tag（如 `v2.2.0`）
- [ ] 发布 Release（安装版/绿色版）
