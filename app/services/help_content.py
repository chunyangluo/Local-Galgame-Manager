"""Help / welcome copy, demo steps, and HTML sections for the in-app guide."""

from __future__ import annotations

import sys
from pathlib import Path

from app.services.app_branding import APP_DISPLAY_NAME

APP_HELP_VERSION = "v2.2.1"
UI_PREF_WELCOME_SHOWN = "welcome_guide_shown"

SUPPORT_EMAIL = "2221565884@qq.com"
SUPPORT_NOTICE = "如有使用问题、功能建议或 BUG 反馈，可发送邮件至："
USAGE_DISCLAIMER = (
    "郑重声明：本软件仅作个人学习交流使用，无任何商业用途，"
    "严禁任何个人或团体用于商业盈利、二次分发等商用行为。"
)

# Readable body copy for help HTML (QTextBrowser).
HELP_BODY_FONT_PX = 14
HELP_HEADING2_FONT_PX = 17
HELP_HEADING3_FONT_PX = 15
HELP_NOTICE_FONT_PX = 14
HELP_FOOTER_FONT_PX = 13

_HELP_STYLE = f"""
<style>
    body {{ font-family: 'Microsoft YaHei', 'Segoe UI', sans-serif; color: #C8D0DC; font-size: {HELP_BODY_FONT_PX}px; }}
    h2 {{ color: #6A9FD8; font-size: {HELP_HEADING2_FONT_PX}px; border-bottom: 1px solid #3D4759; padding-bottom: 4px; margin-top: 16px; }}
    h3 {{ color: #8AB4E0; font-size: {HELP_HEADING3_FONT_PX}px; margin-top: 12px; }}
    p, li {{ font-size: {HELP_BODY_FONT_PX}px; line-height: 1.7; }}
    ul, ol {{ padding-left: 20px; }}
    a {{ color: #6A9FD8; text-decoration: none; }}
    a:hover {{ text-decoration: underline; }}
    .shortcut {{ background: #2E3644; padding: 2px 6px; border-radius: 3px; font-family: monospace; font-size: {HELP_BODY_FONT_PX}px; }}
    .links-box {{ background: #252B36; border: 1px solid #3D4759; border-radius: 6px; padding: 10px 14px; margin: 8px 0; }}
    .tip {{ background: rgba(106, 159, 216, 0.12); border-left: 3px solid #6A9FD8; padding: 8px 12px; margin: 10px 0; font-size: {HELP_BODY_FONT_PX}px; }}
    .notice-box {{ background: #2A2230; border: 1px solid #C97A4A; border-radius: 8px; padding: 12px 14px; margin: 0 0 14px 0; }}
    .notice-box p {{ margin: 0 0 8px 0; font-size: {HELP_NOTICE_FONT_PX}px; line-height: 1.7; }}
    .notice-box p:last-child {{ margin-bottom: 0; }}
    .notice-contact {{ color: #E5E7EB; }}
    .notice-disclaimer {{ color: #E8B080; font-weight: 600; }}
</style>
"""


def support_contact_html() -> str:
    return (
        f'{SUPPORT_NOTICE}'
        f'<a href="mailto:{SUPPORT_EMAIL}">{SUPPORT_EMAIL}</a>'
    )


def notice_html() -> str:
    return f"""
    <div class="notice-box">
        <p class="notice-contact"><b>📧 反馈联系</b> — {support_contact_html()}</p>
        <p class="notice-disclaimer">{USAGE_DISCLAIMER}</p>
    </div>
    """

WELCOME_TAGLINE = (
    "在 Windows 上管理本地 Galgame 库：扫描目录、匹配 VNDB 元数据、"
    "一键解压导入、启动与存档备份。"
)

WELCOME_STEPS: tuple[tuple[str, str], ...] = (
    ("① 添加目录", "在工具栏「库」分组点击「添加目录」，选择游戏安装文件夹。"),
    ("② 扫描入库", "「导入游戏」→ 全量扫描，或「扫描并 VNDB 导入」自动补封面与简介。"),
    ("③ 启动游玩", "双击游戏卡片启动；右键可 LE 转区、存档管理、编辑路径等。"),
)

DEMO_STEPS: tuple[dict[str, str | None], ...] = (
    {
        "title": "添加扫描目录",
        "summary": "把游戏文件夹加入库",
        "body": (
            "首次使用请先告诉程序游戏装在哪里。\n\n"
            "点击「试一试」会打开文件夹选择框；选好后该路径会出现在扫描列表中。"
        ),
        "action": "add_root",
        "button": "试一试：添加目录",
        "hint": "也可在「更多 → 管理目录」中查看或删除已添加的路径。",
    },
    {
        "title": "扫描并导入",
        "summary": "识别 exe 并写入数据库",
        "body": (
            "添加目录后执行扫描，程序会查找子文件夹中的启动程序。\n\n"
            "推荐新用户选择「扫描并 VNDB 导入」，自动匹配 VNDB 封面与元数据。"
        ),
        "action": "scan_vndb",
        "button": "试一试：扫描并 VNDB 导入",
        "hint": "已有大量游戏时可用「增量扫描」只处理新增项。",
    },
    {
        "title": "浏览与启动",
        "summary": "网格/列表、搜索与右键菜单",
        "body": (
            "• 双击卡片 — 启动游戏（视频条目用系统播放器打开）\n"
            "• 右键 — LE 转区、调试启动、存档、封面、隐藏等\n"
            "• 搜索框 — 中/英/日关键词；<span class='shortcut'>Ctrl+F</span> 快速聚焦\n"
            "• 底部分页 — 大库按页浏览，可跳转页码"
        ),
        "action": None,
        "button": "",
        "hint": "收藏 <span class='shortcut'>Ctrl+D</span>，隐藏 <span class='shortcut'>Ctrl+H</span>，详情 <span class='shortcut'>Ctrl+I</span>。",
    },
    {
        "title": "一键工作流",
        "summary": "解压 → 扫描 → VNDB 一条龙",
        "body": (
            "下载资源包后，可用工具栏「🚀 一键工作流」串联：\n"
            "自动化解压 → 增量扫描 → 增量 VNDB 导入。\n\n"
            "工作流内还可打开 FDM 下载、密码本等辅助工具。"
        ),
        "action": "quick_workflow",
        "button": "试一试：打开一键工作流",
        "hint": "解压前建议在设置中配置 7-Zip；分卷/RAR5 等会自动选用合适工具。",
    },
    {
        "title": "设置与工具箱",
        "summary": "LE、FDM、封面策略、外观",
        "body": (
            "「更多 → 设置」可配置：\n"
            "• 双击启动方式（普通 / LE / 智能）\n"
            "• 封面获取策略、主题与字体\n"
            "• LEProc、FDM、2DFan 线索库路径\n\n"
            "工具箱还提供 HBE 解密、自动化解压、插件等扩展功能。"
        ),
        "action": "settings",
        "button": "试一试：打开设置",
        "hint": "LE 转区灰色时，请在工具路径中配置 LEProc.exe 并自动检测。",
    },
)


def resolve_help_screenshot() -> Path | None:
    """Main-window screenshot for welcome / demo tabs."""
    from app.services.paths import dev_repo_root

    candidates: list[Path] = []
    root = dev_repo_root()
    if root is not None:
        candidates.append(root / "docs" / "assets" / "main-window.png")
    app_assets = Path(__file__).resolve().parent.parent / "assets"
    candidates.append(app_assets / "help-main-window.png")
    candidates.append(app_assets / "main-window.png")
    if getattr(sys, "frozen", False):
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            base = Path(meipass)
            candidates.append(base / "docs" / "assets" / "main-window.png")
            candidates.append(base / "app" / "assets" / "help-main-window.png")
    for path in candidates:
        if path.is_file():
            return path
    return None


def should_show_welcome_guide(preferences: dict) -> bool:
    return not bool(preferences.get(UI_PREF_WELCOME_SHOWN))


def guide_html() -> str:
    return f"""{_HELP_STYLE}
    {notice_html()}
    <p><b>{APP_DISPLAY_NAME} {APP_HELP_VERSION}</b></p>
    <div class="tip">新用户建议顺序：<b>添加目录 → 扫描并 VNDB 导入 → 双击启动</b>。完整流程可在「交互演示」页签逐步体验。</div>

    <h2>工具栏</h2>
    <h3>库 · 导入</h3>
    <ul>
        <li><b>添加目录</b> — 加入扫描根路径</li>
        <li><b>导入游戏</b> — 全量/增量扫描；扫描并 VNDB 导入；增量扫描并增量 VNDB（最快）</li>
        <li><b>VNDB 导入</b> — 对已有记录补元数据</li>
        <li><b>🚀 一键工作流</b> — 解压 → 增量扫描 → 增量 VNDB</li>
    </ul>
    <h3>搜索 · 视图</h3>
    <ul>
        <li><b>搜索 / 筛选 / 排序</b> — 关键词、收藏/已玩状态、多种排序</li>
        <li><b>网格 / 列表</b> — 分页浏览大库</li>
        <li><b>随机 / 历史 / 日志</b> — 随机选游戏、游玩记录、运行日志</li>
    </ul>

    <h2>「更多」菜单</h2>
    <ul>
        <li><b>管理目录 / 数据管理</b> — 扫描路径、备份恢复、批量清理</li>
        <li><b>工具箱</b> — HBE、自动化解压、FDM、插件、LE、2DFan</li>
        <li><b>设置</b> — 启动、封面、外观、工具路径、高级</li>
        <li><b>托盘</b> — 关窗口可选后台运行；托盘「退出程序」才真正结束</li>
    </ul>

    <h2>工具箱要点</h2>
    <ul>
        <li><b>自动化解压</b> — RAR/7z 分卷、ISO+MDS 光盘包、伪装视频压缩包；验收报告</li>
        <li><b>FDM</b> — 打开下载器或 <code>--add</code> 添加链接（见「工具与链接」）</li>
        <li><b>密码本</b> — 解压密码优先级与统计</li>
    </ul>

    <h2>启动与视频</h2>
    <ul>
        <li><b>LE 转区 / 管理员 / 调试启动</b> — 右键或详情；失败可自动重试</li>
        <li><b>视频条目</b> — 真实视频文件单独识别，系统播放器打开，跳过 VNDB</li>
    </ul>
    """


def faq_html() -> str:
    return f"""{_HELP_STYLE}
    {notice_html()}
    <h2>常见问题</h2>
    <ul>
        <li><b>游戏未识别？</b> — 确认目录含 .exe，重新全量扫描</li>
        <li><b>启动 exe 不对？</b> — 右键「编辑名称/路径」；或依赖自动搜索替代 exe</li>
        <li><b>启动闪退？</b> — 「调试启动」查看退出码；或配置 LE 转区</li>
        <li><b>封面不显示？</b> — 调整封面策略或右键重新获取</li>
        <li><b>解压卡住？</b> — 查看日志；大包、ISO 展开耗时较长属正常</li>
        <li><b>隐藏游戏找不到？</b> — 「更多」开启「显示隐藏游戏」或 <span class="shortcut">Ctrl+H</span></li>
        <li><b>FDM 未安装？</b> — 见「工具与链接」官方下载，再在设置中指定 <code>fdm.exe</code></li>
        <li><b>缺少 7-Zip？</b> — 安装 7-Zip 并加入 PATH</li>
        <li><b>归档占空间？</b> — 数据管理 → 文件管理 → 清空归档目录</li>
    </ul>
    <p style="color:#5A6474;font-size:{HELP_FOOTER_FONT_PX}px;">完整说明见仓库 <code>docs/USER_GUIDE.md</code></p>
    """


def links_html() -> str:
    return f"""{_HELP_STYLE}
    {notice_html()}
    <h2>推荐工具与外链</h2>
    <div class="links-box">
    <ul style="margin:0;">
        <li><b>FDM</b> — <a href="https://www.freedownloadmanager.org/zh/">官方中文站</a>（免费、开源）</li>
        <li><b>Locale Emulator</b> — <a href="https://github.com/xupefei/Locale-Emulator/releases">GitHub Releases</a></li>
        <li><b>7-Zip</b> — <a href="https://www.7-zip.org/">7-zip.org</a></li>
        <li><b>VNDB</b> — <a href="https://vndb.org/">vndb.org</a></li>
        <li><b>2DFan</b> — <a href="https://www.2dfan.com/">2dfan.com</a></li>
        <li><b>本项目</b> — <a href="https://github.com/chunyangluo/Local-Galgame-Manager">GitHub</a>
            · <a href="https://github.com/chunyangluo/Local-Galgame-Manager/releases/latest">最新版</a></li>
    </ul>
    </div>
    """
