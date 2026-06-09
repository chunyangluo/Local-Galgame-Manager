"""Smart Locale Emulator configuration: detect, generate .le.config files."""

from __future__ import annotations

import re
import uuid
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Optional

# Default LE profile for galgames (Japanese locale)
DEFAULT_JA_PROFILE = {
    "name": "Run in Japanese",
    "guid": str(uuid.uuid5(uuid.NAMESPACE_URL, "lgm-ja-jp-default")),
    "location": "ja-JP",
    "timezone": "Tokyo Standard Time",
    "run_as_admin": False,
    "redirect_registry": True,
    "is_advanced_redirection": True,
    "run_with_suspend": False,
}

DEFAULT_ZH_PROFILE = {
    "name": "Run in Simplified Chinese",
    "guid": str(uuid.uuid5(uuid.NAMESPACE_URL, "lgm-zh-cn-default")),
    "location": "zh-CN",
    "timezone": "China Standard Time",
    "run_as_admin": False,
    "redirect_registry": True,
    "is_advanced_redirection": True,
    "run_with_suspend": False,
}

DEFAULT_ZH_TW_PROFILE = {
    "name": "Run in Traditional Chinese",
    "guid": str(uuid.uuid5(uuid.NAMESPACE_URL, "lgm-zh-tw-default")),
    "location": "zh-TW",
    "timezone": "Taipei Standard Time",
    "run_as_admin": False,
    "redirect_registry": True,
    "is_advanced_redirection": True,
    "run_with_suspend": False,
}

DEFAULT_KO_PROFILE = {
    "name": "Run in Korean",
    "guid": str(uuid.uuid5(uuid.NAMESPACE_URL, "lgm-ko-kr-default")),
    "location": "ko-KR",
    "timezone": "Korea Standard Time",
    "run_as_admin": False,
    "redirect_registry": True,
    "is_advanced_redirection": True,
    "run_with_suspend": False,
}

# Map profile string to default profile dict
PROFILE_MAP: dict[str, dict] = {
    "ja-JP": DEFAULT_JA_PROFILE,
    "zh-CN": DEFAULT_ZH_PROFILE,
    "zh-TW": DEFAULT_ZH_TW_PROFILE,
    "ko-KR": DEFAULT_KO_PROFILE,
}

# Path keywords suggesting Japanese games
_JP_PATH_KEYWORDS = [
    "日本", "japanese", "jp", "日版",
]


def read_le_global_profiles(leproc_path: str) -> list[dict]:
    """Read profiles from LEConfig.xml next to LEProc.exe."""
    if not leproc_path:
        return []
    le_dir = Path(leproc_path).parent
    config_path = le_dir / "LEConfig.xml"
    if not config_path.is_file():
        return []
    try:
        tree = ET.parse(config_path)
        root = tree.getroot()
        profiles = []
        for profile_elem in root.iter("Profile"):
            p = {
                "name": profile_elem.get("Name", ""),
                "guid": profile_elem.get("Guid", ""),
                "location": "",
                "timezone": "",
                "run_as_admin": False,
                "redirect_registry": False,
                "is_advanced_redirection": False,
                "run_with_suspend": False,
            }
            loc = profile_elem.find("Location")
            if loc is not None and loc.text:
                p["location"] = loc.text
            tz = profile_elem.find("Timezone")
            if tz is not None and tz.text:
                p["timezone"] = tz.text
            for flag_name in ("RunAsAdmin", "RedirectRegistry", "IsAdvancedRedirection", "RunWithSuspend"):
                elem = profile_elem.find(flag_name)
                if elem is not None and elem.text:
                    snake = re.sub(r'(?<!^)(?=[A-Z])', '_', flag_name).lower()
                    p[snake] = elem.text.lower() == "true"
            profiles.append(p)
        return profiles
    except ET.ParseError:
        return []


def detect_recommended_le_profile(game_dir: str | Path, launch_exe: str | Path) -> str:
    """Detect whether a game likely needs LE and return the recommended profile string.

    Returns:
        "" if LE not needed, "ja-JP" for Japanese, "zh-CN" for Chinese, etc.
    """
    game_dir = Path(game_dir)
    launch_exe = Path(launch_exe)

    # Check path keywords
    dir_str = str(game_dir).lower()

    for kw in _JP_PATH_KEYWORDS:
        if kw in dir_str:
            return "ja-JP"

    # Check for Japanese galgame engine indicators
    try:
        for item in game_dir.rglob("*"):
            if item.is_file():
                suffix = item.suffix.lower()
                if suffix in (".xp3", ".ks", ".tjs", ".ypf"):
                    return "ja-JP"
                # Only check a reasonable number of files
                name_lower = item.name.lower()
                if name_lower in ("data.xp3", "patch.xp3", "script.xp3"):
                    return "ja-JP"
    except OSError:
        pass

    # Default: no LE needed
    return ""


def _read_local_profiles(target_exe: str | Path) -> list[dict]:
    """Read profiles from LEConfig.xml next to the target exe (game-shipped LE)."""
    if not target_exe:
        return []
    local_config = Path(target_exe).parent / "LEConfig.xml"
    if not local_config.is_file():
        return []
    try:
        tree = ET.parse(str(local_config))
        root = tree.getroot()
        profiles = []
        for profile_elem in root.iter("Profile"):
            p = {
                "name": profile_elem.get("Name", ""),
                "guid": profile_elem.get("Guid", ""),
                "location": "",
                "timezone": "",
                "run_as_admin": False,
                "redirect_registry": False,
                "is_advanced_redirection": False,
                "run_with_suspend": False,
            }
            loc = profile_elem.find("Location")
            if loc is not None and loc.text:
                p["location"] = loc.text
            tz = profile_elem.find("Timezone")
            if tz is not None and tz.text:
                p["timezone"] = tz.text
            for flag_name in ("RunAsAdmin", "RedirectRegistry", "IsAdvancedRedirection", "RunWithSuspend"):
                elem = profile_elem.find(flag_name)
                if elem is not None and elem.text:
                    snake = re.sub(r'(?<!^)(?=[A-Z])', '_', flag_name).lower()
                    p[snake] = elem.text.lower() == "true"
            profiles.append(p)
        return profiles
    except ET.ParseError:
        return []


def find_le_profile_guid(leproc_path: str, locale: str, target_exe: str = "") -> str:
    """Find the real profile GUID from LEConfig.xml for the given locale.

    When a game ships its own LE (LEProc.exe + LEConfig.xml in game dir),
    the local LEConfig.xml takes priority — the local LEProc will only
    recognize GUIDs from its own LEConfig.xml.

    Args:
        leproc_path: Path to LEProc.exe (global)
        locale: Locale string like "ja-JP", "zh-CN"
        target_exe: Path to the game exe (for local LEConfig.xml lookup)

    Returns:
        The GUID string from LEConfig.xml, or empty string if not found.
    """
    # Priority: local LEConfig.xml (game-shipped LE) > global LEConfig.xml
    sources: list[list[dict]] = []
    if target_exe:
        local_profiles = _read_local_profiles(target_exe)
        if local_profiles:
            sources.append(local_profiles)
    profiles_global = read_le_global_profiles(leproc_path)
    if profiles_global:
        sources.append(profiles_global)

    for profiles in sources:
        for p in profiles:
            loc = p.get("location", "")
            if loc and locale.lower() in loc.lower():
                return p.get("guid", "")
        # Fallback: if only one profile exists, use it
        if len(profiles) == 1:
            return profiles[0].get("guid", "")
    return ""


def _resolve_profile_and_guid(
    leproc_path: str, profile: str, target_exe: str = ""
) -> tuple[dict, str]:
    """Resolve the profile dict and real GUID for .le.config generation.

    When a game ships its own LE (LEProc.exe + LEConfig.xml in game dir),
    we use the full profile settings from the local LEConfig.xml — not our
    defaults — because the local LE may require specific settings
    (e.g. RunAsAdmin=true, IsAdvancedRedirection=false).

    Returns:
        (profile_dict, real_guid_string)
    """
    # Priority: local LEConfig.xml > global LEConfig.xml > our defaults
    sources: list[tuple[list[dict], str]] = []
    if target_exe:
        local_profiles = _read_local_profiles(target_exe)
        if local_profiles:
            sources.append((local_profiles, "local"))
    if leproc_path:
        global_profiles = read_le_global_profiles(leproc_path)
        if global_profiles:
            sources.append((global_profiles, "global"))

    for profiles, source in sources:
        for p in profiles:
            loc = p.get("location", "")
            if loc and profile.lower() in loc.lower():
                return p, p.get("guid", "")
        # Fallback: single profile
        if len(profiles) == 1:
            return profiles[0], profiles[0].get("guid", "")

    # No matching profile found: use our defaults
    p = PROFILE_MAP.get(profile, DEFAULT_JA_PROFILE)
    return p, p["guid"]


def generate_le_config(
    exe_path: str | Path,
    profile: str = "ja-JP",
    leproc_path: str = "",
) -> Path:
    """Generate a .le.config file next to the target exe.

    Args:
        exe_path: Path to the game's executable
        profile: Locale profile string (e.g. "ja-JP", "zh-CN")
        leproc_path: Path to LEProc.exe (used to look up real GUID)

    Returns:
        Path to the generated .le.config file
    """
    exe_path = Path(exe_path)
    config_path = exe_path.parent / f"{exe_path.name}.le.config"

    p, real_guid = _resolve_profile_and_guid(leproc_path, profile, target_exe=str(exe_path))
    # Use the real GUID from LEConfig.xml if available
    guid = real_guid if real_guid else p["guid"]

    # Force RunAsAdmin=false: admin elevation causes zombie processes and
    # invisible windows when launched from a non-admin parent process.
    p["run_as_admin"] = False

    root = ET.Element("LEConfig")
    profiles = ET.SubElement(root, "Profiles")
    profile_elem = ET.SubElement(profiles, "Profile")
    profile_elem.set("Name", p["name"])
    profile_elem.set("Guid", guid)
    profile_elem.set("MainMenu", "true")

    ET.SubElement(profile_elem, "Parameter")
    ET.SubElement(profile_elem, "Location").text = p["location"]
    ET.SubElement(profile_elem, "Timezone").text = p["timezone"]
    ET.SubElement(profile_elem, "RunAsAdmin").text = str(p["run_as_admin"]).lower()
    ET.SubElement(profile_elem, "RedirectRegistry").text = str(p["redirect_registry"]).lower()
    ET.SubElement(profile_elem, "IsAdvancedRedirection").text = str(p["is_advanced_redirection"]).lower()
    ET.SubElement(profile_elem, "RunWithSuspend").text = str(p["run_with_suspend"]).lower()

    tree = ET.ElementTree(root)
    ET.indent(tree, space="  ")
    tree.write(str(config_path), encoding="utf-8", xml_declaration=True)
    return config_path


def _is_guid_in_le_config(leproc_path: str, guid: str, target_exe: str = "") -> bool:
    """Check if a GUID exists in the LEConfig.xml that LEProc will actually read.

    When a game ships its own LE (LEProc.exe + LEConfig.xml in game dir),
    the local LEProc only reads the local LEConfig.xml. So we must check
    the local LEConfig.xml first if it exists.
    """
    if not guid:
        return False
    # If game has local LEProc.exe, only the local LEConfig.xml matters
    if target_exe:
        local_le_dir = Path(target_exe).parent
        has_local_leproc = (local_le_dir / "LEProc.exe").is_file()
        local_config = local_le_dir / "LEConfig.xml"
        if has_local_leproc and local_config.is_file():
            try:
                tree = ET.parse(str(local_config))
                for profile_elem in tree.getroot().iter("Profile"):
                    if profile_elem.get("Guid", "") == guid:
                        return True
                # GUID not found in local LEConfig.xml → invalid
                return False
            except ET.ParseError:
                pass
    # No local LE: check global LEConfig.xml
    if leproc_path:
        profiles = read_le_global_profiles(leproc_path)
        return any(p.get("guid", "") == guid for p in profiles)
    return False


def ensure_le_config(
    exe_path: str | Path,
    le_profile: str,
    leproc_path: str = "",
) -> Optional[Path]:
    """Ensure a .le.config exists for the given exe and profile.

    If a .le.config already exists with a valid GUID (one that exists in
    LEConfig.xml — either global or local) and RunAsAdmin=false, don't
    overwrite it. Otherwise regenerate the file.

    Returns:
        Path to the .le.config file, or None if not created
    """
    if not le_profile:
        return None
    exe_path = Path(exe_path)
    config_path = exe_path.parent / f"{exe_path.name}.le.config"
    if config_path.exists():
        try:
            tree = ET.parse(str(config_path))
            for profile_elem in tree.getroot().iter("Profile"):
                existing_guid = profile_elem.get("Guid", "")
                if existing_guid and _is_guid_in_le_config(
                    leproc_path, existing_guid, target_exe=str(exe_path)
                ):
                    # Check RunAsAdmin — must be false to keep the file
                    admin_elem = profile_elem.find("RunAsAdmin")
                    if admin_elem is not None and admin_elem.text and admin_elem.text.lower() == "true":
                        break  # RunAsAdmin=true, regenerate
                    return config_path  # GUID is valid and RunAsAdmin=false
                break
        except ET.ParseError:
            pass  # Corrupted file, regenerate
    return generate_le_config(exe_path, le_profile, leproc_path=leproc_path)


def remove_le_config(exe_path: str | Path) -> bool:
    """Remove the .le.config file for the given exe if it was generated by us.

    Returns True if file was removed, False otherwise.
    """
    exe_path = Path(exe_path)
    config_path = exe_path.parent / f"{exe_path.name}.le.config"
    if config_path.is_file():
        try:
            config_path.unlink()
            return True
        except OSError:
            pass
    return False
