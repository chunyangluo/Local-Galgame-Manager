from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

import yaml
from pydantic import BaseModel, Field


class AppConfig(BaseModel):
    host: str = "0.0.0.0"
    port: int = 9600
    api_key: str = ""


class DirectoriesConfig(BaseModel):
    watch: str = ""
    target: str = "./"
    archive: str = "./data/archive"
    failed: str = "./data/failed"
    temp: str = "./data/temp"
    logs: str = "./data/logs"
    upload: str = "./data/upload"
    game_save: str = ""


class SevenZipConfig(BaseModel):
    path: str = "./bin/7za.exe"


class PasswordsConfig(BaseModel):
    file: str = "./config/passwords.json"
    encrypt: bool = False
    encryption_key: str = ""


class WatcherConfig(BaseModel):
    debounce_seconds: float = 3.0
    stable_check_interval: float = 0.5
    stable_threshold: int = 2
    ignore_suffixes: list[str] = Field(default_factory=lambda: [
        ".baiduyun.p.downloading",
        ".baiduyun.downloading",
        ".baiduyun.downloading.cfg",
        ".uploading",
        ".baiduyun.uploading",
        ".tmp",
        ".bd!",
        ".part",
        ".pcs",
    ])


class ExtractionConfig(BaseModel):
    max_recursive_depth: int = 5
    enable_magic_detection: bool = True
    default_target_dir: str = ""


class GameDetectionConfig(BaseModel):
    enabled: bool = True
    keywords: list[str] = Field(default_factory=lambda: [
        "game", "Game", "游戏", "汉化", "中文", "pc", "PC",
        "steam", "Steam", "visual novel", "Visual Novel",
        "galgame", "Galgame"
    ])
    min_size_mb: int = 50


class IsoImagesConfig(BaseModel):
    """After RAR/7z unpack: expand ISO (+MDS sidecar) into installable files."""

    enabled: bool = True
    try_mount_fallback: bool = True
    move_iso_to_subfolder: bool = True
    disc_subfolder: str = "_disc_images"


class PostProcessConfig(BaseModel):
    enabled: bool = True
    move_game_dir: bool = True
    delete_archive: bool = False
    game_detection: GameDetectionConfig = Field(default_factory=GameDetectionConfig)
    iso_images: IsoImagesConfig = Field(default_factory=IsoImagesConfig)


class LoggingConfig(BaseModel):
    level: str = "INFO"
    rotation: str = "00:00"
    retention: str = "0 days"
    format: str = "{time:YYYY-MM-DD HH:mm:ss} | {level} | {message}"


class Settings(BaseModel):
    app: AppConfig = Field(default_factory=AppConfig)
    directories: DirectoriesConfig = Field(default_factory=DirectoriesConfig)
    seven_zip: SevenZipConfig = Field(default_factory=SevenZipConfig)
    passwords: PasswordsConfig = Field(default_factory=PasswordsConfig)
    watcher: WatcherConfig = Field(default_factory=WatcherConfig)
    extraction: ExtractionConfig = Field(default_factory=ExtractionConfig)
    post_process: PostProcessConfig = Field(default_factory=PostProcessConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)

    @classmethod
    def from_yaml(cls, path: str | Path) -> "Settings":
        p = Path(path)
        if not p.exists():
            return cls()
        with open(p, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        return cls(**data)

    def resolve_paths(self, base_dir: str | Path | None = None) -> None:
        base = Path(base_dir or os.getcwd())
        for field_name in self.directories.model_fields:
            raw = getattr(self.directories, field_name)
            # 已绝对路径的直接使用，否则拼接 base_dir
            p = Path(raw)
            if p.is_absolute():
                resolved = p.resolve()
            else:
                resolved = (base / raw).resolve()
            setattr(self.directories, field_name, str(resolved))
            Path(resolved).mkdir(parents=True, exist_ok=True)

        # 处理 7za 和 passwords 路径
        if Path(self.seven_zip.path).is_absolute():
            self.seven_zip.path = str(Path(self.seven_zip.path).resolve())
        else:
            self.seven_zip.path = str((base / self.seven_zip.path).resolve())
            
        if Path(self.passwords.file).is_absolute():
            self.passwords.file = str(Path(self.passwords.file).resolve())
        else:
            self.passwords.file = str((base / self.passwords.file).resolve())


_settings: Optional[Settings] = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        raise RuntimeError("Settings not initialized. Call init_settings() first.")
    return _settings


def init_settings(config_path: str | Path | None = None) -> Settings:
    global _settings
    if config_path is None:
        config_path = Path(__file__).resolve().parent.parent / "config" / "config.yaml"
    _settings = Settings.from_yaml(config_path)
    base_dir = Path(config_path).resolve().parent.parent
    _settings.resolve_paths(base_dir)
    return _settings
