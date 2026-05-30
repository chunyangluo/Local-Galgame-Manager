from __future__ import annotations

import shutil
from pathlib import Path

from loguru import logger

from core.config import get_settings
from core.extractor import ExtractResult
from core.logger import (
    ui_game_found, ui_game_moved, ui_game_move_fail, ui_archive_done,
    print_warning,
)


class FileManager:
    def __init__(self) -> None:
        self._settings = get_settings()

    def archive_file(self, file_path: str | Path) -> str:
        if self._settings.post_process.delete_archive:
            return self.delete_file(file_path)
        src = Path(file_path).resolve()
        if not src.exists():
            logger.warning(f"归档源文件不存在: {src}")
            return ""
        
        archive_dir = Path(self._settings.directories.archive)
        archive_dir.mkdir(parents=True, exist_ok=True)
        dest = archive_dir / src.name
        
        if dest.exists():
            logger.info(f"文件已在归档目录中，删除监控目录中的副本: {src.name}")
            if src.parent != archive_dir:
                try:
                    src.unlink()
                    logger.info(f"已删除监控目录中的重复文件: {src.name}")
                except Exception as e:
                    logger.warning(f"删除监控目录中重复文件失败: {src.name} | {e}")
            return str(dest)
        
        stem = src.stem
        suffix = src.suffix
        existing_conflicts = list(archive_dir.glob(f"{stem}_*{suffix}"))
        if existing_conflicts:
            logger.info(f"发现同名冲突文件 {existing_conflicts}，删除监控目录中的文件: {src.name}")
            if src.parent != archive_dir:
                try:
                    src.unlink()
                    logger.info(f"已删除监控目录中的重复文件: {src.name}")
                except Exception as e:
                    logger.warning(f"删除监控目录中重复文件失败: {src.name} | {e}")
            return str(dest)
        
        shutil.move(str(src), str(dest))
        ui_archive_done(src.name)
        return str(dest)

    def delete_file(self, file_path: str | Path) -> str:
        src = Path(file_path).resolve()
        if not src.exists():
            logger.warning(f"删除文件不存在: {src}")
            return ""
        src.unlink()
        ui_archive_done(src.name)
        return str(src)

    def move_to_failed(self, file_path: str | Path, reason: str = "") -> str:
        src = Path(file_path).resolve()
        if not src.exists():
            logger.warning(f"失败迁移源文件不存在: {src}")
            return ""
        failed_dir = Path(self._settings.directories.failed)
        failed_dir.mkdir(parents=True, exist_ok=True)
        dest = failed_dir / src.name
        dest = self._resolve_conflict(dest)
        shutil.move(str(src), str(dest))
        logger.warning(f"失败迁移: {src.name} -> {dest.name} | 原因={reason}")
        return str(dest)

    def archive_split_sfx_files(self, files: list[str]) -> list[str]:
        if self._settings.post_process.delete_archive:
            return self.delete_files(files)
        archive_dir = Path(self._settings.directories.archive)
        archive_dir.mkdir(parents=True, exist_ok=True)
        archived = []
        
        watch_dir = Path(self._settings.directories.watch)
        
        for i, f in enumerate(files):
            src = Path(f).resolve()
            if not src.exists():
                continue
            
            dest = archive_dir / src.name
            
            if dest.exists():
                logger.info(f"分卷文件已在归档目录中，删除监控目录中的副本: {src.name}")
                if src.parent != archive_dir:
                    try:
                        src.unlink()
                        logger.info(f"已删除监控目录中的重复文件: {src.name}")
                    except Exception as e:
                        logger.warning(f"删除监控目录中重复文件失败: {src.name} | {e}")
                archived.append(str(dest))
                continue
            
            stem = src.stem
            suffix = src.suffix
            existing_conflicts = list(archive_dir.glob(f"{stem}_*{suffix}"))
            if existing_conflicts:
                logger.info(f"发现同名冲突文件 {existing_conflicts}，删除监控目录中的文件: {src.name}")
                if src.parent != archive_dir:
                    try:
                        src.unlink()
                        logger.info(f"已删除监控目录中的重复文件: {src.name}")
                    except Exception as e:
                        logger.warning(f"删除监控目录中重复文件失败: {src.name} | {e}")
                archived.append(str(dest))
                continue
            
            if src.parent == archive_dir:
                logger.info(f"文件已在归档目录中，跳过: {src.name}")
                archived.append(str(src))
                continue
            
            shutil.move(str(src), str(dest))
            archived.append(str(dest))
            ui_archive_done(src.name)
        return archived

    def delete_files(self, files: list[str]) -> list[str]:
        deleted = []
        for f in files:
            src = Path(f).resolve()
            if not src.exists():
                continue
            src.unlink()
            deleted.append(str(src))
        print_step(f"删除分卷自解压包", f"{len(deleted)}个文件")
        return deleted

    def move_split_sfx_to_failed(self, files: list[str], reason: str = "") -> list[str]:
        failed_dir = Path(self._settings.directories.failed)
        failed_dir.mkdir(parents=True, exist_ok=True)
        moved = []
        for f in files:
            src = Path(f).resolve()
            if not src.exists():
                continue
            dest = failed_dir / src.name
            dest = self._resolve_conflict(dest)
            shutil.move(str(src), str(dest))
            moved.append(str(dest))
        print_warning(f"分卷包失败迁移: {len(moved)}个文件 | 原因={reason}")
        return moved

    ANDROID_MARKERS: set[str] = {
        "AndroidManifest.xml", "classes.dex", "resources.arsc",
    }

    ANDROID_DIRS: set[str] = {
        "meta-inf", "meta_inf", "assets", "res", "classes",
        "android", "lib", "libs",
    }

    GAME_ENGINE_EXTENSIONS: set[str] = {
        ".ypf", ".xp3", ".rpy", ".rpyc", ".rpa", ".rpym",
        ".ks", ".tjs", ".nscripta", ".nscriptdat",
        ".pck", ".dat", ".pak", ".arc", ".bin",
    }

    @staticmethod
    def _quick_dir_size(dir_path: Path, max_files: int = 500) -> int:
        total = 0
        count = 0
        try:
            for f in dir_path.rglob("*"):
                if f.is_file():
                    try:
                        total += f.stat().st_size
                    except OSError:
                        pass
                    count += 1
                    if count >= max_files:
                        break
        except Exception:
            pass
        return total

    def detect_game_directory(self, extract_dir: str) -> list[Path]:
        cfg = self._settings.post_process.game_detection
        if not cfg.enabled:
            logger.info("游戏目录识别未启用")
            return []

        target = Path(extract_dir).resolve()
        logger.info(f"检测游戏目录: extract_dir={extract_dir}, target={target}, exists={target.exists()}")
        if not target.exists():
            logger.warning(f"解压目录不存在: {target}")
            return []

        min_size_bytes = cfg.min_size_mb * 1024 * 1024

        android_marker_names = {"AndroidManifest.xml", "classes.dex", "resources.arsc"}
        android_dir_names = {"meta-inf", "meta_inf", "assets", "res", "classes", "android", "lib", "libs"}
        game_engine_ext = {".ypf", ".xp3", ".rpy", ".rpyc", ".rpa", ".rpym", ".ks", ".tjs", ".pck", ".pak", ".arc"}

        def is_android_dir(dir_path: Path) -> bool:
            try:
                for item in dir_path.iterdir():
                    if item.is_file() and item.name in android_marker_names:
                        return True
                    if item.is_dir() and item.name.lower() in android_dir_names:
                        return True
            except Exception:
                pass
            return False

        def is_wrapper_dir(dir_path: Path) -> bool:
            """空壳目录：只包含一个子目录，没有其他有意义的内容"""
            items = list(dir_path.iterdir())
            dirs = [i for i in items if i.is_dir()]
            files = [i for i in items if i.is_file()]
            
            # 有多个子目录或大量文件，不是空壳
            if len(dirs) > 1:
                return False
            # 有exe或游戏数据文件，不是空壳
            for f in files:
                if f.suffix.lower() in {".exe", ".dll"} | game_engine_ext:
                    return False
            # 只有一个子目录且没有重要文件 → 是空壳
            if len(dirs) == 1 and len(files) <= 2:
                return True
            return False

        def find_game_root(dir_path: Path, max_depth: int = 8) -> Path:
            """从解压目录出发，剥掉空壳，找到游戏真正的根目录"""
            current = dir_path
            for _ in range(max_depth):
                if not current.is_dir():
                    break
                
                items = list(current.iterdir())
                subdirs = [i for i in items if i.is_dir()]
                files = [i for i in items if i.is_file()]
                
                # 排除安卓目录
                non_android_dirs = [d for d in subdirs if not is_android_dir(d)]
                
                # 如果有多个非安卓子目录，当前就是根
                if len(non_android_dirs) > 1:
                    break
                
                # 如果有exe或游戏数据文件，当前就是根
                has_game_file = any(
                    f.suffix.lower() in {".exe", ".dll"} | game_engine_ext
                    for f in files
                )
                if has_game_file:
                    break
                
                # 如果只有一个子目录且是空壳，继续深入
                if len(non_android_dirs) == 1 and is_wrapper_dir(current):
                    current = non_android_dirs[0]
                    continue
                
                break
            
            return current

        # 找到游戏根目录
        game_root = find_game_root(target)
        
        # 如果游戏根目录就是 target 本身，检查子目录
        if game_root == target:
            subdirs = [d for d in target.iterdir() if d.is_dir() and not is_android_dir(d)]
            if len(subdirs) == 1:
                game_root = find_game_root(subdirs[0])
            elif len(subdirs) > 1:
                # 多个子目录，选有exe的或最大的
                best = None
                best_score = -1
                for d in subdirs:
                    root = find_game_root(d)
                    size = self._quick_dir_size(root)
                    has_exe = any(f.suffix.lower() == ".exe" for f in root.iterdir() if f.is_file())
                    score = (1000 if has_exe else 0) + size
                    if score > best_score:
                        best_score = score
                        best = root
                if best:
                    game_root = best

        # 最终校验：排除安卓目录和太小的目录
        if is_android_dir(game_root):
            logger.info(f"排除安卓目录: {game_root.name}")
            return []
        
        size = self._quick_dir_size(game_root)
        if size < min_size_bytes:
            has_exe = any(f.suffix.lower() == ".exe" for f in game_root.iterdir() if f.is_file())
            has_game_data = any(f.suffix.lower() in game_engine_ext for f in game_root.iterdir() if f.is_file())
            if not (has_exe or has_game_data):
                logger.info(f"目录太小且无游戏特征，跳过: {game_root.name} ({size/1024/1024:.1f}MB)")
                return []

        ui_game_found(game_root.name, size / 1024 / 1024)
        logger.info(f"游戏根目录: {game_root.name} ({size/1024/1024:.1f}MB)")
        
        return [game_root]

    def move_game_to_save_dir(self, game_dirs, cover_callback=None):
        """移动游戏目录，返回列表 [(最终路径, 是否覆盖)]"""
        if not self._settings.post_process.move_game_dir:
            return []

        save_dir = Path(self._settings.directories.game_save)
        save_dir.mkdir(parents=True, exist_ok=True)
        moved = []

        for game_dir in game_dirs:
            if not game_dir.exists():
                logger.warning(f"游戏目录不存在: {game_dir}")
                continue

            dest = save_dir / game_dir.name
            is_cover = False

            try:
                if dest.exists():
                    is_cover = True
                    logger.info("检测到同名游戏目录，执行覆盖操作")
                    if cover_callback:
                        cover_callback()
                    try:
                        shutil.rmtree(dest)
                        logger.info("旧目录已清理")
                    except PermissionError:
                        logger.warning(f"权限错误，无法删除旧目录: {dest}")
                        ui_game_move_fail(game_dir.name, f"权限错误，旧目录删除失败，跳过覆盖")
                        continue
                    except Exception as e:
                        logger.error(f"删除旧目录失败: {e}")
                        ui_game_move_fail(game_dir.name, f"旧目录删除失败: {e}，跳过覆盖")
                        continue

                shutil.move(str(game_dir), str(dest))
                if is_cover:
                    logger.info("游戏目录覆盖完成")
                moved.append((str(dest), is_cover))
                ui_game_moved(game_dir.name, str(dest))
            except PermissionError:
                import time
                import gc
                gc.collect()
                time.sleep(1)
                try:
                    shutil.copytree(str(game_dir), str(dest), dirs_exist_ok=True)
                    shutil.rmtree(str(game_dir), ignore_errors=True)
                    moved.append((str(dest), is_cover))
                    ui_game_moved(game_dir.name, str(dest))
                except Exception as e2:
                    logger.error(f"权限错误 (重试也失败: {e2})")
                    ui_game_move_fail(game_dir.name, f"权限错误 (重试也失败: {e2})")
            except Exception as e:
                logger.error(f"游戏目录移动失败: {e}")
                ui_game_move_fail(game_dir.name, str(e))

        return moved

    def _rename_generic_game_dir(self, game_dir: Path, archive_name: str) -> Path:
        generic_names = {"data", "output", "extract", "temp", "release", "game"}
        if game_dir.name.lower() in generic_names and archive_name:
            stem = archive_name
            for suffix in (".exe", ".e01", ".e02", ".zip", ".7z", ".rar"):
                if stem.lower().endswith(suffix):
                    stem = stem[: -len(suffix)]
                    break
            new_dir = game_dir.parent / stem
            logger.info(f"尝试重命名游戏目录: {game_dir} -> {new_dir} (archive_name={archive_name}, stem={stem})")
            if not new_dir.exists():
                try:
                    game_dir.rename(new_dir)
                    logger.info(f"重命名游戏目录成功: {game_dir.name} -> {stem}")
                    return new_dir
                except Exception as e:
                    logger.error(f"重命名游戏目录失败: {e}")
            else:
                logger.info(f"目标目录已存在: {new_dir}")
        return game_dir

    def handle_post_process(self, result, cover_callback=None):
        if not self._settings.post_process.enabled:
            return {}

        result_info = {}
        moved_games = []

        if result.success and result.extract_dir:
            logger.info(f"开始后处理: extract_dir={result.extract_dir}, file_name={result.file_name}")
            game_dirs = self.detect_game_directory(result.extract_dir)
            logger.info(f"检测到游戏目录: {game_dirs}")
            if game_dirs:
                renamed_dirs = []
                for gd in game_dirs:
                    logger.info(f"处理游戏目录: {gd}")
                    renamed = self._rename_generic_game_dir(gd, result.file_name)
                    logger.info(f"重命名结果: {gd} -&gt; {renamed}")
                    renamed_dirs.append(renamed)
                logger.info(f"准备移动的目录: {renamed_dirs}")
                moved = self.move_game_to_save_dir(renamed_dirs, cover_callback=cover_callback)
                result_info["game_directories"] = [str(g) for g in renamed_dirs]
                result_info["game_save_dir"] = self._settings.directories.game_save
                result_info["moved_games"] = moved
                moved_games = moved
                logger.info(f"移动结果: {moved}")

        return result_info, moved_games

    def handle_extract_result(self, result, skip_post_process=False, cover_callback=None):
        post_result = {}
        all_moved_games = []
        logger.info(f"handle_extract_result: success={result.success}, is_split_sfx={result.is_split_sfx}, extract_dir={result.extract_dir}, file_name={result.file_name}, depth={result.depth}")

        if result.is_split_sfx and result.split_sfx_files:
            if result.success:
                existing_files = [f for f in result.split_sfx_files if Path(f).exists()]
                if existing_files:
                    logger.info(f"归档分卷文件: {existing_files}")
                    self.archive_split_sfx_files(existing_files)
                else:
                    logger.info(f"分卷文件已不存在，跳过归档")
            else:
                self.move_split_sfx_to_failed(result.split_sfx_files, result.error)
        else:
            if result.success:
                if Path(result.file_path).exists():
                    self.archive_file(result.file_path)
                else:
                    logger.info(f"归档源文件已不存在，跳过归档: {result.file_path}")
            else:
                if Path(result.file_path).exists():
                    self.move_to_failed(result.file_path, result.error)
                else:
                    logger.info(f"失败迁移源文件已不存在，跳过迁移: {result.file_path}")

        moved_games = []
        if result.success and not skip_post_process and result.depth == 0:
            if result.extract_dir and Path(result.extract_dir).exists():
                logger.info("调用 handle_post_process")
                post_result, moved_games = self.handle_post_process(result, cover_callback=cover_callback)
                all_moved_games.extend(moved_games)
            else:
                logger.info(f"解压目录已不存在，跳过后处理: {result.extract_dir}")

        for nested in result.nested_results:
            nested_post, _ = self.handle_extract_result(nested, skip_post_process=True, cover_callback=cover_callback)
            if nested_post:
                post_result.setdefault("nested_post_process", []).append(nested_post)

        return post_result, all_moved_games

    @staticmethod
    def _resolve_conflict(dest: Path) -> Path:
        # 不做后缀追加，由 move_game_to_save_dir 负责删除覆盖
        return dest
