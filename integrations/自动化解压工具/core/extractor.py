from __future__ import annotations

import asyncio
import os
import shutil
import struct
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from loguru import logger

from core.archive_detector import (
    detect_archive_type, detect_split_volume_set, detect_7z_split_volume_set,
    is_7z_split_part, check_volume_integrity, detect_disguised_archive,
    SEVENZ_SPLIT_RE,
)
from core.config import get_settings
from core.logger import (
    ui_split_detected, ui_split_integrity_ok, ui_split_integrity_fail,
    ui_extract_start, ui_password_try, ui_password_success,
    ui_extract_success, ui_extract_fail,
    ui_merge_progress, ui_extract_progress,
    format_size, format_duration,
    print_step, print_error,
)
from core.password_manager import PasswordManager


@dataclass
class ExtractResult:
    success: bool = False
    file_path: str = ""
    file_name: str = ""
    extract_dir: str = ""
    used_password: str = ""
    error: str = ""
    archive_type: str = ""
    is_split_sfx: bool = False
    split_sfx_files: list[str] = field(default_factory=list)
    nested_results: list["ExtractResult"] = field(default_factory=list)
    depth: int = 0


class Extractor:
    def __init__(self, password_manager: PasswordManager) -> None:
        self.password_manager = password_manager
        self._settings = get_settings()

    def _get_7z_path(self) -> str:
        return self._settings.seven_zip.path

    def _detect_sfx_header_size(self, exe_path: str) -> int:
        try:
            with open(exe_path, 'rb') as f:
                data = f.read(2 * 1024 * 1024)
                idx = data.find(b'PK\x03\x04')
                if idx >= 0:
                    return idx
        except OSError:
            pass
        return -1

    def _merge_split_volumes(
        self, exe_path: str, volume_files: list[str], sfx_size: int, merged_path: Path
    ) -> None:
        CHUNK = 64 * 1024 * 1024
        with open(merged_path, 'wb') as out:
            with open(exe_path, 'rb') as f:
                f.seek(sfx_size)
                while True:
                    d = f.read(CHUNK)
                    if not d:
                        break
                    out.write(d)
            for vol in volume_files:
                with open(vol, 'rb') as f:
                    while True:
                        d = f.read(CHUNK)
                        if not d:
                            break
                        out.write(d)

    def _patch_merged_zip(
        self,
        merged_path: Path,
        exe_path: str,
        volume_files: list[str],
        sfx_size: int,
    ) -> None:
        exe_zip_size = os.path.getsize(exe_path) - sfx_size
        disk_sizes = [exe_zip_size]
        for vol in volume_files:
            disk_sizes.append(os.path.getsize(vol))

        disk_offsets = [0]
        for i in range(len(disk_sizes) - 1):
            disk_offsets.append(disk_offsets[-1] + disk_sizes[i])

        last_vol = volume_files[-1]
        last_vol_size = disk_sizes[-1]

        with open(last_vol, 'rb') as f:
            f.seek(-65536, 2)
            tail = f.read()

        eocd_sig_pos = tail.rfind(b'PK\x05\x06')
        if eocd_sig_pos < 0:
            return

        eocd_in_vol = last_vol_size - len(tail) + eocd_sig_pos

        with open(last_vol, 'rb') as f:
            f.seek(eocd_in_vol)
            eocd_raw = f.read(22)

        eocd_num_entries = struct.unpack('<H', eocd_raw[8:10])[0]
        eocd_cd_size = struct.unpack('<I', eocd_raw[12:16])[0]
        eocd_cd_offset = struct.unpack('<I', eocd_raw[16:20])[0]

        use_zip64 = eocd_num_entries == 0xFFFF or eocd_cd_offset == 0xFFFFFFFF

        if use_zip64:
            z64_sig_pos = tail.rfind(b'PK\x06\x06')
            if z64_sig_pos < 0:
                return
            z64_in_vol = last_vol_size - len(tail) + z64_sig_pos

            with open(last_vol, 'rb') as f:
                f.seek(z64_in_vol)
                z64_data = f.read(56)

            z64_entries_total = struct.unpack('<Q', z64_data[32:40])[0]
            z64_cd_offset = struct.unpack('<Q', z64_data[48:56])[0]
            num_entries = z64_entries_total
            cd_offset_in_vol = z64_cd_offset
        else:
            num_entries = eocd_num_entries
            cd_offset_in_vol = eocd_cd_offset

        cd_abs = disk_offsets[-1] + cd_offset_in_vol

        entries = []
        with open(last_vol, 'rb') as f:
            f.seek(cd_offset_in_vol)
            for _ in range(num_entries):
                sig = f.read(4)
                if sig != b'PK\x01\x02':
                    break
                head = f.read(42)
                name_len = struct.unpack('<H', head[24:26])[0]
                extra_len = struct.unpack('<H', head[26:28])[0]
                comment_len = struct.unpack('<H', head[28:30])[0]
                disk_start = struct.unpack('<H', head[30:32])[0]
                local_header_offset_32 = struct.unpack('<I', head[38:42])[0]
                compress_size_32 = struct.unpack('<I', head[16:20])[0]
                file_size_32 = struct.unpack('<I', head[20:24])[0]
                name = f.read(name_len)
                extra = bytearray(f.read(extra_len))
                comment = f.read(comment_len)

                actual_offset = local_header_offset_32
                epos = 0
                while epos + 4 <= len(extra):
                    eid = struct.unpack('<H', extra[epos:epos + 2])[0]
                    esize = struct.unpack('<H', extra[epos + 2:epos + 4])[0]
                    if eid == 0x0001:
                        z64_pos = epos + 4
                        if file_size_32 == 0xFFFFFFFF and z64_pos + 8 <= epos + 4 + esize:
                            z64_pos += 8
                        if compress_size_32 == 0xFFFFFFFF and z64_pos + 8 <= epos + 4 + esize:
                            z64_pos += 8
                        if local_header_offset_32 == 0xFFFFFFFF and z64_pos + 8 <= epos + 4 + esize:
                            actual_offset = struct.unpack('<Q', extra[z64_pos:z64_pos + 8])[0]
                    epos += 4 + esize

                if disk_start == 0:
                    new_offset = actual_offset - sfx_size
                elif disk_start < len(disk_offsets):
                    new_offset = disk_offsets[disk_start] + actual_offset
                else:
                    new_offset = actual_offset

                filtered_extra = bytearray()
                epos = 0
                while epos + 4 <= len(extra):
                    eid = struct.unpack('<H', extra[epos:epos + 2])[0]
                    esize = struct.unpack('<H', extra[epos + 2:epos + 4])[0]
                    if eid != 0x0001:
                        filtered_extra.extend(extra[epos:epos + 4 + esize])
                    epos += 4 + esize

                need_z64_offset = new_offset > 0xFFFFFFFF
                if need_z64_offset:
                    z64_field = struct.pack('<HH', 0x0001, 8) + struct.pack('<Q', new_offset)
                    filtered_extra.extend(z64_field)

                new_head = bytearray(head)
                struct.pack_into('<H', new_head, 30, 0)
                if need_z64_offset:
                    struct.pack_into('<I', new_head, 38, 0xFFFFFFFF)
                else:
                    struct.pack_into('<I', new_head, 38, new_offset)
                struct.pack_into('<H', new_head, 26, len(filtered_extra))

                entries.append({
                    'head': new_head,
                    'name': name,
                    'extra': filtered_extra,
                    'comment': comment,
                })

        with open(merged_path, 'r+b') as f:
            f.seek(cd_abs)
            for entry in entries:
                f.write(b'PK\x01\x02')
                f.write(entry['head'])
                f.write(entry['name'])
                f.write(entry['extra'])
                f.write(entry['comment'])

            cd_end_pos = f.tell()
            cd_size = cd_end_pos - cd_abs
            n = len(entries)

            need_z64 = n > 0xFFFF or cd_size > 0xFFFFFFFF or cd_abs > 0xFFFFFFFF

            if need_z64:
                z64_eocd_pos = cd_end_pos
                z64_eocd = bytearray(56)
                struct.pack_into('<I', z64_eocd, 0, 0x06064B50)
                struct.pack_into('<Q', z64_eocd, 4, 44)
                struct.pack_into('<H', z64_eocd, 12, 45)
                struct.pack_into('<H', z64_eocd, 14, 45)
                struct.pack_into('<I', z64_eocd, 16, 0)
                struct.pack_into('<I', z64_eocd, 20, 0)
                struct.pack_into('<Q', z64_eocd, 24, n)
                struct.pack_into('<Q', z64_eocd, 32, n)
                struct.pack_into('<Q', z64_eocd, 40, cd_size)
                struct.pack_into('<Q', z64_eocd, 48, cd_abs)
                f.write(z64_eocd)

                z64_loc = bytearray(20)
                struct.pack_into('<I', z64_loc, 0, 0x07064B50)
                struct.pack_into('<I', z64_loc, 4, 0)
                struct.pack_into('<Q', z64_loc, 8, z64_eocd_pos)
                struct.pack_into('<I', z64_loc, 16, 1)
                f.write(z64_loc)

            eocd = bytearray(22)
            struct.pack_into('<I', eocd, 0, 0x06054B50)
            struct.pack_into('<H', eocd, 4, 0)
            struct.pack_into('<H', eocd, 6, 0)
            struct.pack_into('<H', eocd, 8, 0xFFFF if n > 0xFFFF else n)
            struct.pack_into('<H', eocd, 10, 0xFFFF if n > 0xFFFF else n)
            struct.pack_into('<I', eocd, 12, 0xFFFFFFFF if cd_size > 0xFFFFFFFF else cd_size)
            struct.pack_into('<I', eocd, 16, 0xFFFFFFFF if cd_abs > 0xFFFFFFFF else cd_abs)
            struct.pack_into('<H', eocd, 20, 0)
            f.write(eocd)

            f.truncate(f.tell())

    @staticmethod
    def _install_xz_decompressor_patch() -> None:
        import lzma
        import pyzipper
        from pyzipper.zipfile_aes import AESZipExtFile

        if getattr(pyzipper.zipfile.ZipExtFile, '_xz_patched', False):
            return

        class XZDecompressObj:
            def __init__(self):
                self._decompressor = lzma.LZMADecompressor()
                self._eof = False

            def decompress(self, data, max_length=0):
                if max_length > 0:
                    result = self._decompressor.decompress(data, max_length)
                else:
                    result = self._decompressor.decompress(data)
                if self._decompressor.eof:
                    self._eof = True
                return result

            @property
            def eof(self):
                return self._eof

            @property
            def unconsumed_tail(self):
                return getattr(self._decompressor, 'unconsumed_tail', b'')

            @property
            def unused_data(self):
                return getattr(self._decompressor, 'unused_data', b'')

            def flush(self):
                return b''

        _orig = pyzipper.zipfile.ZipExtFile.get_decompressor
        def _patched(self, compress_type):
            if compress_type == 95:
                return XZDecompressObj()
            return _orig(self, compress_type)
        pyzipper.zipfile.ZipExtFile.get_decompressor = _patched

        _orig_aes = AESZipExtFile.get_decompressor
        def _patched_aes(self, compress_type):
            if compress_type == 95:
                return XZDecompressObj()
            return _orig_aes(self, compress_type)
        AESZipExtFile.get_decompressor = _patched_aes

        pyzipper.zipfile.ZipExtFile._xz_patched = True

    def _extract_from_patched_zip(
        self, merged_path: Path, output_dir: str, password: Optional[str] = None
    ) -> tuple[bool, str]:
        import pyzipper

        self._install_xz_decompressor_patch()

        pwd_bytes = password.encode('utf-8') if password else None

        try:
            with pyzipper.AESZipFile(merged_path, 'r') as zf:
                file_list = [i for i in zf.infolist() if not i.is_dir()]
                total = len(file_list)
                for idx, info in enumerate(file_list, 1):
                    dest = os.path.join(output_dir, info.filename)
                    os.makedirs(os.path.dirname(dest), exist_ok=True)
                    if idx % max(1, total // 10) == 0 or idx == total:
                        ui_extract_progress(idx, total, info.filename)
                    with zf.open(info.filename, pwd=pwd_bytes) as src, \
                         open(dest, 'wb') as out:
                        shutil.copyfileobj(src, out)

                for info in zf.infolist():
                    if info.is_dir():
                        os.makedirs(os.path.join(output_dir, info.filename), exist_ok=True)
            return True, ""
        except Exception as e:
            return False, str(e)

    def _run_python_split_extract(
        self, split_info: dict, output_dir: str, password: Optional[str] = None
    ) -> tuple[bool, str]:
        all_files = split_info["all_files"]

        exe_file = None
        volume_files = []
        for f in all_files:
            if f.lower().endswith('.exe'):
                exe_file = f
            else:
                volume_files.append(f)
        volume_files.sort()

        if not exe_file:
            return False, "未找到 .exe 分卷文件"

        sfx_size = self._detect_sfx_header_size(exe_file)
        if sfx_size <= 0:
            return False, "无法检测 SFX 头部大小（非 ZIP SFX 格式）"

        total_size = os.path.getsize(exe_file) - sfx_size
        for vol in volume_files:
            total_size += os.path.getsize(vol)

        ui_merge_progress(f"SFX 头部: {sfx_size} 字节 | 分卷数: {len(volume_files) + 1} | 总大小: {format_size(total_size)}")

        merged_path = Path(output_dir) / "_merged_temp.zip"
        try:
            t0 = time.monotonic()
            ui_merge_progress("正在合并分卷文件...")
            self._merge_split_volumes(exe_file, volume_files, sfx_size, merged_path)
            merge_time = time.monotonic() - t0
            ui_merge_progress(f"合并完成 ({format_duration(merge_time)}, {format_size(os.path.getsize(merged_path))})")

            t0 = time.monotonic()
            ui_merge_progress("正在修补中央目录...")
            self._patch_merged_zip(merged_path, exe_file, volume_files, sfx_size)
            patch_time = time.monotonic() - t0
            ui_merge_progress(f"修补完成 ({format_duration(patch_time)})")

            ui_merge_progress("正在解压文件...")
            return self._extract_from_patched_zip(merged_path, output_dir, password)
        except Exception as e:
            return False, str(e)
        finally:
            if merged_path.exists():
                try:
                    merged_path.unlink()
                except OSError:
                    pass

    def _extract_disguised_zip(
        self, file_path: str, output_dir: str, password: Optional[str] = None
    ) -> tuple[bool, str]:
        try:
            file_size = os.path.getsize(file_path)
            zip_start = self._find_zip_start(file_path)
            if zip_start < 0:
                return False, "伪装文件中未找到 ZIP 数据"

            ui_merge_progress(f"检测到伪装 ZIP: 偏移 {format_size(zip_start)}, 大小 {format_size(file_size - zip_start)}")

            zip_part = Path(output_dir) / "_disguised_temp.zip"
            try:
                with open(file_path, 'rb') as fin, open(zip_part, 'wb') as fout:
                    fin.seek(zip_start)
                    remaining = file_size - zip_start
                    while remaining > 0:
                        chunk = min(remaining, 64 * 1024 * 1024)
                        data = fin.read(chunk)
                        if not data:
                            break
                        fout.write(data)
                        remaining -= len(data)

                return self._run_extract(str(zip_part), output_dir, password)
            finally:
                if zip_part.exists():
                    try:
                        zip_part.unlink()
                    except OSError:
                        pass
        except Exception as e:
            return False, str(e)

    @staticmethod
    def _find_zip_start(file_path: str) -> int:
        chunk_size = 100 * 1024 * 1024
        with open(file_path, 'rb') as f:
            offset = 0
            while True:
                data = f.read(chunk_size)
                if not data:
                    break
                idx = data.find(b'PK\x03\x04')
                if idx >= 0:
                    return offset + idx
                offset += len(data)
        return -1

    def _build_extract_cmd(
        self, archive_path: str, output_dir: str, password: Optional[str] = None
    ) -> list[str]:
        cmd = [self._get_7z_path(), "x", archive_path, f"-o{output_dir}", "-aoa", "-y"]
        if password is not None:
            cmd.append(f"-p{password}")
        else:
            # password 为 None 时使用空密码（-p 不带参数）
            cmd.append("-p")
        return cmd

    def _run_extract(
        self, archive_path: str, output_dir: str, password: Optional[str] = None
    ) -> tuple[bool, str]:
        cmd = self._build_extract_cmd(archive_path, output_dir, password)
        return self._run_extract_with_cmd(cmd)
    
    def _run_extract_with_cmd(
        self, cmd: list[str]
    ) -> tuple[bool, str]:
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = subprocess.SW_HIDE
        creationflags = subprocess.CREATE_NO_WINDOW

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=3600,
                startupinfo=startupinfo,
                creationflags=creationflags,
                encoding="utf-8",
                errors="replace",
            )
            if result.returncode == 0:
                return True, ""
            stderr = result.stderr or result.stdout or ""
            return False, stderr.strip()
        except subprocess.TimeoutExpired:
            return False, "解压超时"
        except FileNotFoundError:
            return False, f"7za.exe 未找到: {self._get_7z_path()}"
        except Exception as e:
            return False, str(e)

    def _is_password_error(self, error_msg: str) -> bool:
        keywords = ["wrong password", "password", "encrypted", "密码"]
        lower = error_msg.lower()
        return any(k in lower for k in keywords)

    def _is_damaged_error(self, error_msg: str) -> bool:
        keywords = ["crc", "damaged", "broken", "corrupt", "unexpected end"]
        lower = error_msg.lower()
        return any(k in lower for k in keywords)

    def _is_missing_volume_error(self, error_msg: str) -> bool:
        keywords = ["volume", "required volume", "next volume", "分卷"]
        lower = error_msg.lower()
        return any(k in lower for k in keywords)

    def _classify_error(self, error: str, has_passwords: bool) -> str:
        if self._is_missing_volume_error(error):
            return "分卷自解压包异常: 分卷文件缺失"
        if self._is_password_error(error):
            return "加密压缩包，密码本为空" if not has_passwords else "密码本中无匹配密码"
        if self._is_damaged_error(error):
            return "压缩包文件损坏"
        return error

    async def _try_extract_with_passwords(
        self,
        extract_fn,
        extract_arg,
        temp_dir: Path,
        is_split: bool,
    ) -> tuple[bool, str, str]:
        passwords = self.password_manager.get_passwords()
        total_attempts = 1 + len(passwords)

        ui_password_try(1, total_attempts, "(无密码)")
        success, error = await asyncio.to_thread(extract_fn, extract_arg, str(temp_dir), None)
        used_pwd = ""

        if not success:
            for i, pwd in enumerate(passwords):
                if temp_dir.exists():
                    shutil.rmtree(temp_dir, ignore_errors=True)
                temp_dir.mkdir(parents=True, exist_ok=True)
                ui_password_try(i + 2, total_attempts, self._mask_pwd(pwd))
                success, error = await asyncio.to_thread(extract_fn, extract_arg, str(temp_dir), pwd)
                if success:
                    used_pwd = pwd
                    self.password_manager.record_success(str(extract_arg), pwd)
                    ui_password_success(self._mask_pwd(pwd))
                    break

            if not success:
                error = self._classify_error(error, bool(passwords))

        return success, error, used_pwd

    async def extract(
        self,
        file_path: str | Path,
        custom_password: Optional[str] = None,
        output_dir: Optional[str] = None,
        depth: int = 0,
    ) -> ExtractResult:
        file_path = Path(file_path).resolve()
        file_name = file_path.name

        # 对于 .lz4 文件，先尝试正常流程（_extract_lz4_outer）
        # 只有当 detect_archive_type 识别为 lz4 时才会走 _extract_lz4_outer
        # 所以我们先不做任何特殊处理，让正常流程走
        
        # 正常流程
        atype = detect_archive_type(file_path)

        if atype is None:
            return ExtractResult(
                success=False,
                file_path=str(file_path),
                file_name=file_name,
                error="不支持的压缩格式",
                depth=depth,
            )

        # 处理 lz4 包裹的情况（作为备选方案）
        if atype == "lz4":
            return await self._extract_lz4_outer(file_path, custom_password, output_dir, depth)

        original_path = file_path
        split_7z = detect_7z_split_volume_set(file_path)
        if not split_7z:
            part_7z = is_7z_split_part(file_path)
            if part_7z:
                file_path = Path(part_7z["first_part"])
                split_7z = detect_7z_split_volume_set(file_path)
        if split_7z:
            if output_dir is None:
                output_dir = self._settings.directories.target
            return await self._extract_7z_split_group(
                split_7z,
                Path(output_dir),
                depth=depth,
                custom_password=custom_password,
                delete_sources=False,
                is_split_sfx=True,
                source_path=str(original_path),
            )

        split_info = detect_split_volume_set(file_path)
        is_split = split_info is not None

        settings = self._settings
        max_depth = settings.extraction.max_recursive_depth
        if output_dir is None:
            output_dir = settings.directories.target

        temp_dir = Path(settings.directories.temp) / f"extract_{file_path.stem}_{os.getpid()}_{depth}"
        temp_dir.mkdir(parents=True, exist_ok=True)

        extract_path = str(file_path)

        if split_info:
            extract_path = split_info["extract_entry"]
            ui_split_detected(split_info["base_name"], split_info["volume_count"])

            is_complete, msg = check_volume_integrity(split_info)
            if not is_complete:
                ui_split_integrity_fail(msg)
                return ExtractResult(
                    success=False,
                    file_path=str(file_path),
                    file_name=file_name,
                    error=msg,
                    archive_type=atype,
                    is_split_sfx=True,
                    split_sfx_files=split_info["all_files"],
                    depth=depth,
                )
            ui_split_integrity_ok()

        extract_fn = self._run_python_split_extract if is_split else self._run_extract
        engine = "Python(合并修补)" if is_split else "7-Zip"

        is_disguised = not is_split and detect_disguised_archive(file_path) is not None
        if is_disguised:
            extract_fn = self._extract_disguised_zip
            engine = "Python(伪装ZIP)"

        ui_extract_start(file_name, engine)

        t_start = time.monotonic()

        try:
            if custom_password:
                success, error = await asyncio.to_thread(
                    extract_fn, split_info if is_split else extract_path,
                    str(temp_dir), custom_password
                )
                used_pwd = custom_password if success else ""
                if not success:
                    return ExtractResult(
                        success=False,
                        file_path=str(file_path),
                        file_name=file_name,
                        error=f"自定义密码解压失败: {error}",
                        archive_type=atype,
                        is_split_sfx=is_split,
                        split_sfx_files=split_info["all_files"] if split_info else [],
                        depth=depth,
                    )
            else:
                extract_arg = split_info if is_split else extract_path
                success, error, used_pwd = await self._try_extract_with_passwords(
                    extract_fn, extract_arg, temp_dir, is_split
                )

            if success:
                final_dir = Path(output_dir)
                final_dir.mkdir(parents=True, exist_ok=True)

                nested_results: list[ExtractResult] = []
                if depth < max_depth:
                    nested_results = await self._extract_nested(temp_dir, temp_dir, depth + 1)

                for item in temp_dir.iterdir():
                    dest = final_dir / item.name
                    dest = self._resolve_conflict(dest)
                    shutil.move(str(item), str(dest))

                elapsed = time.monotonic() - t_start
                type_label = "分卷自解压包" if is_split else atype
                detail = f"格式={type_label} | 密码={self._mask_pwd(used_pwd)}"
                if nested_results:
                    detail += f" | 递归解压{len(nested_results)}个嵌套包"
                ui_extract_success(file_name, detail, elapsed)

                return ExtractResult(
                    success=True,
                    file_path=str(file_path),
                    file_name=file_name,
                    extract_dir=str(final_dir),
                    used_password=used_pwd,
                    archive_type=atype,
                    is_split_sfx=is_split,
                    split_sfx_files=split_info["all_files"] if split_info else [],
                    nested_results=nested_results,
                    depth=depth,
                )
            else:
                elapsed = time.monotonic() - t_start
                type_label = "分卷自解压包" if is_split else atype
                ui_extract_fail(file_name, error, elapsed)
                return ExtractResult(
                    success=False,
                    file_path=str(file_path),
                    file_name=file_name,
                    error=error,
                    archive_type=atype,
                    is_split_sfx=is_split,
                    split_sfx_files=split_info["all_files"] if split_info else [],
                    depth=depth,
                )

        finally:
            if temp_dir.exists():
                shutil.rmtree(temp_dir, ignore_errors=True)

    async def _extract_lz4_outer(
        self,
        file_path: str | Path,
        custom_password: Optional[str],
        output_dir: Optional[str],
        depth: int
    ) -> ExtractResult:
        file_path = Path(file_path).resolve()
        file_name = file_path.name
        
        settings = self._settings
        if output_dir is None:
            output_dir = settings.directories.target
        
        t_start = time.monotonic()
        
        # ========== 方案一：Python lz4.frame 解压 ==========
        lz4_available = False
        try:
            import lz4.frame
            lz4_available = True
        except ImportError:
            logger.warning("lz4 库未安装，跳过 Python LZ4 解压，使用 7za 回退")
        
        if lz4_available:
            ui_extract_start(file_name, "Python(LZ4外层)")
            temp_dir_lz4 = Path(settings.directories.temp) / f"extract_lz4_{file_path.stem}_{os.getpid()}_{depth}"
            temp_dir_lz4.mkdir(parents=True, exist_ok=True)
            
            try:
                inner_file = temp_dir_lz4 / file_path.stem  # 去掉 .lz4 后缀
                
                print_step("使用Python lz4.frame解压外层", file_name)
                
                def _lz4_decompress():
                    with open(file_path, "rb") as f_in:
                        compressed = f_in.read()
                    decompressed = lz4.frame.decompress(compressed)
                    with open(inner_file, "wb") as f_out:
                        f_out.write(decompressed)
                    return inner_file.stat().st_size
                
                decompressed_size = await asyncio.to_thread(_lz4_decompress)
                
                print_step(f"LZ4外层解压完成", f"{decompressed_size / 1024 / 1024:.1f}MB")
                
                # 识别内层文件格式
                inner_type = detect_archive_type(inner_file)
                
                if inner_type and inner_type != "lz4":
                    print_step("检测到内层压缩包", f"{inner_file.name} ({inner_type})")
                    
                    inner_result = await self.extract(
                        inner_file,
                        custom_password=custom_password,
                        output_dir=output_dir,
                        depth=depth,
                    )
                    inner_result.file_path = str(file_path)
                    inner_result.file_name = file_name
                    return inner_result
                else:
                    # 内层不是压缩包，直接移动到输出目录
                    final_dir = Path(output_dir)
                    final_dir.mkdir(parents=True, exist_ok=True)
                    dest = final_dir / inner_file.name
                    dest = self._resolve_conflict(dest)
                    shutil.move(str(inner_file), str(dest))
                    
                    elapsed = time.monotonic() - t_start
                    ui_extract_success(file_name, f"格式=lz4 | 密码=(无密码)", elapsed)
                    return ExtractResult(
                        success=True,
                        file_path=str(file_path),
                        file_name=file_name,
                        extract_dir=str(final_dir),
                        used_password="",
                        archive_type="lz4",
                        depth=depth,
                    )
            except Exception as e:
                logger.warning(f"Python lz4.frame 解压失败: {e}，回退到 7za")
                print_step("Python LZ4解压失败，回退7za", str(e)[:80])
            finally:
                if temp_dir_lz4.exists():
                    shutil.rmtree(temp_dir_lz4, ignore_errors=True)
        
        # ========== 方案二：7za 回退 ==========
        temp_dir_lz4 = Path(settings.directories.temp) / f"extract_lz4_{file_path.stem}_{os.getpid()}_{depth}"
        temp_dir_lz4.mkdir(parents=True, exist_ok=True)
        
        ui_extract_start(file_name, "7-Zip(LZ4外层)")
        
        try:
            success_lz4 = False
            error_lz4 = ""
            used_pwd = ""
            
            if custom_password:
                success_lz4, error_lz4 = await asyncio.to_thread(
                    self._run_extract, str(file_path), str(temp_dir_lz4), custom_password
                )
                used_pwd = custom_password
            else:
                passwords = self.password_manager.get_passwords()
                total_attempts = 2 + len(passwords)
                
                ui_password_try(1, total_attempts, "(真正无密码)")
                cmd_no_p = [self._get_7z_path(), "x", str(file_path), f"-o{temp_dir_lz4}", "-aoa", "-y"]
                success_lz4, error_lz4 = await asyncio.to_thread(
                    self._run_extract_with_cmd, cmd_no_p
                )
                
                if not success_lz4:
                    ui_password_try(2, total_attempts, "(空密码)")
                    success_lz4, error_lz4 = await asyncio.to_thread(
                        self._run_extract, str(file_path), str(temp_dir_lz4), None
                    )
                
                if not success_lz4:
                    for i, pwd in enumerate(passwords):
                        if temp_dir_lz4.exists():
                            shutil.rmtree(temp_dir_lz4, ignore_errors=True)
                        temp_dir_lz4.mkdir(parents=True, exist_ok=True)
                        
                        ui_password_try(i + 3, total_attempts, self._mask_pwd(pwd))
                        success_lz4, error_lz4 = await asyncio.to_thread(
                            self._run_extract, str(file_path), str(temp_dir_lz4), pwd
                        )
                        
                        if success_lz4:
                            used_pwd = pwd
                            break
            
            if not success_lz4:
                no_lz4_path = Path(file_path.parent) / file_path.stem
                shutil.copy(file_path, no_lz4_path)
                
                atype = detect_archive_type(no_lz4_path)
                if atype and atype != "lz4":
                    print_step("LZ4解压失败，尝试去掉.lz4后缀解压", f"{atype}")
                    result = await self.extract(no_lz4_path, custom_password, output_dir, depth)
                    result.file_path = str(file_path)
                    result.file_name = file_name
                    if no_lz4_path.exists():
                        no_lz4_path.unlink()
                    return result
                else:
                    if no_lz4_path.exists():
                        no_lz4_path.unlink()
                    ui_extract_fail(file_name, f"LZ4外层解压失败: {error_lz4}", time.monotonic() - t_start)
                    return ExtractResult(
                        success=False,
                        file_path=str(file_path),
                        file_name=file_name,
                        error=f"LZ4外层解压失败: {error_lz4}",
                        archive_type="lz4",
                        depth=depth,
                    )
            
            # 7za 解压成功，找内层压缩包
            inner_archive = None
            for item in temp_dir_lz4.iterdir():
                if item.is_file() and detect_archive_type(item):
                    inner_archive = item
                    break
            
            if inner_archive is None:
                final_dir = Path(output_dir)
                final_dir.mkdir(parents=True, exist_ok=True)
                for item in temp_dir_lz4.iterdir():
                    dest = final_dir / item.name
                    dest = self._resolve_conflict(dest)
                    shutil.move(str(item), str(dest))
                
                ui_extract_success(file_name, f"格式=lz4 | 密码={self._mask_pwd(used_pwd)}", time.monotonic() - t_start)
                return ExtractResult(
                    success=True,
                    file_path=str(file_path),
                    file_name=file_name,
                    extract_dir=str(final_dir),
                    used_password=used_pwd,
                    archive_type="lz4",
                    depth=depth,
                )
            
            print_step("检测到内部压缩包", f"{inner_archive.name}")
            inner_result = await self.extract(
                inner_archive,
                custom_password=custom_password,
                output_dir=output_dir,
                depth=depth,
            )
            inner_result.file_path = str(file_path)
            inner_result.file_name = file_name
            return inner_result
            
        finally:
            if temp_dir_lz4.exists():
                shutil.rmtree(temp_dir_lz4, ignore_errors=True)

    NESTED_SKIP_NAMES: set[str] = {
        "save", "saves", "存档", "备份", "backup", "backups",
        "patch", "patches", "补丁", "汉化补丁", "更新补丁",
        "config", "settings", "设定",
    }

    NESTED_SKIP_EXTENSIONS: set[str] = {
        ".rar", ".bak",
        ".apk", ".xlsx", ".xls", ".doc", ".docx", ".ppt", ".pptx",
        ".gz", ".bz2", ".tar",
    }

    NESTED_MAX_FILE_SIZE = 200 * 1024 * 1024

    async def _extract_nested(
        self, extract_dir: str | Path, output_dir: str, depth: int
    ) -> list[ExtractResult]:
        results = []
        extract_path = Path(extract_dir)
        
        # 检测是否是真正的游戏目录（不是全是压缩包的目录）
        _android_markers = {"AndroidManifest.xml", "classes.dex", "resources.arsc"}
        _android_dir_names = {"meta-inf", "meta_inf", "assets", "res", "classes", "android", "lib", "libs"}
        _game_engine_ext = {".ypf", ".xp3", ".rpy", ".rpyc", ".rpa", ".rpym", ".ks", ".tjs", ".pck", ".pak", ".arc"}
        
        def is_real_game_dir(dir_path: Path) -> bool:
            exclude_names = {"data", "temp", "logs", "archive", "failed", "upload", "output", "extract", "backup", "cache", "config", "lib", "libs", "meta-inf", "meta_inf", "assets", "res", "classes", "android", "nested_output", "_nested_output"}
            exclude_prefixes = ("lib", "meta-inf", "meta_inf", "res", "assets", "classes")
            name_lower = dir_path.name.lower()
            if name_lower in exclude_names or any(name_lower.startswith(p) for p in exclude_prefixes) or name_lower.isdigit():
                return False
            
            # 安卓特征排除
            for item in dir_path.iterdir():
                if item.is_file() and item.name in _android_markers:
                    return False
                if item.is_dir() and item.name.lower() in _android_dir_names:
                    return False
            
            has_exe = False
            has_game_data = False
            is_all_archives = True
            
            for item in dir_path.iterdir():
                if item.is_file():
                    if item.suffix.lower() == ".exe":
                        has_exe = True
                    if item.suffix.lower() in _game_engine_ext:
                        has_game_data = True
                        is_all_archives = False
                    archive_type = detect_archive_type(item)
                    if not archive_type:
                        has_game_data = True
                        is_all_archives = False
                else:
                    is_all_archives = False
            
            if is_all_archives:
                return False
            
            return has_exe or has_game_data
        
        # 检测是否已经有真正的游戏目录或游戏文件，如果有就停止嵌套处理
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
            if count >= max_files:
                return total
            return total
        
        def has_potential_game_dir(path: Path) -> tuple[bool, str]:
            min_size_bytes = 200 * 1024 * 1024
            exclude_names = {"data", "temp", "logs", "archive", "failed", "upload", "output", "extract", "backup", "cache", "config", "lib", "libs", "meta-inf", "meta_inf", "assets", "res", "classes", "android", "nested_output", "_nested_output"}
            exclude_prefixes = ("lib", "meta-inf", "meta_inf", "res", "assets", "classes")
            
            # 先检查根目录是否已经有游戏文件
            root_has_exe = False
            root_has_game_data = False
            for item in path.iterdir():
                if item.is_file():
                    if item.suffix.lower() == ".exe":
                        root_has_exe = True
                    if item.suffix.lower() in _game_engine_ext:
                        root_has_game_data = True
                    archive_type = detect_archive_type(item)
                    if not archive_type:
                        root_has_game_data = True
            if root_has_exe or root_has_game_data:
                root_size = _quick_dir_size(path)
                if root_size >= min_size_bytes:
                    return True, path.name
            
            # 再检查子目录
            for item in path.iterdir():
                if not item.is_dir():
                    continue
                name_lower = item.name.lower()
                if name_lower in exclude_names or any(name_lower.startswith(p) for p in exclude_prefixes):
                    continue
                # 安卓特征排除
                is_android = False
                for child in item.iterdir():
                    if child.is_file() and child.name in _android_markers:
                        is_android = True
                        break
                    if child.is_dir() and child.name.lower() in _android_dir_names:
                        is_android = True
                        break
                if is_android:
                    continue
                if not is_real_game_dir(item):
                    continue
                size = _quick_dir_size(item)
                if size >= min_size_bytes:
                    return True, item.name
            return False, ""
            
        has_game, game_dir_name = has_potential_game_dir(extract_path)
        if has_game:
            print_step(f"检测到游戏目录 [{game_dir_name}]，停止嵌套解压")
            return results

        processed_bases: set[str] = set()
        for item in list(extract_path.rglob("*")):
            if not item.is_file():
                continue
                
            # 再次检查是否已有游戏目录，有的话提前终止
            has_game, game_dir_name = has_potential_game_dir(extract_path)
            if has_game:
                print_step(f"检测到游戏目录 [{game_dir_name}]，提前停止嵌套解压")
                break

            split_7z = is_7z_split_part(item)
            if split_7z:
                base_stem = split_7z["base_stem"]
                if base_stem in processed_bases:
                    continue
                processed_bases.add(base_stem)
                first_part = split_7z.get("first_part")
                print_step(f"发现 7z 分卷组(嵌套)", f"{base_stem}.001+ (层级={depth})")
                if first_part:
                    split_info = detect_7z_split_volume_set(first_part)
                else:
                    split_info = detect_7z_split_volume_set(item)
                if split_info:
                    try:
                        nested_result = await self._extract_7z_split_group(
                            split_info, extract_path, depth,
                            delete_sources=True,
                            is_split_sfx=False,
                        )
                        if nested_result:
                            results.append(nested_result)
                        # 解压后检查是否有游戏目录
                        has_game, game_dir_name = has_potential_game_dir(extract_path)
                        if has_game:
                            print_step(f"解压后检测到游戏目录 [{game_dir_name}]，停止后续处理")
                            break
                    except Exception as e:
                        print_error(f"嵌套 7z 分卷解压异常: {item.name} | {e}")
                continue

            item_match = SEVENZ_SPLIT_RE.match(item.name)
            if item_match:
                base_stem = item_match.group(1)
                part_num = int(item_match.group(2))
                if part_num == 1 and base_stem not in processed_bases:
                    split_info = detect_7z_split_volume_set(str(item))
                    if split_info and split_info["volume_count"] >= 2:
                        processed_bases.add(base_stem)
                        print_step(f"发现 7z 分卷组(嵌套)", f"{base_stem}.001+ (层级={depth})")
                        try:
                            nested_result = await self._extract_7z_split_group(
                                split_info, extract_path, depth,
                                delete_sources=True,
                                is_split_sfx=False,
                            )
                            if nested_result:
                                results.append(nested_result)
                            has_game, game_dir_name = has_potential_game_dir(extract_path)
                            if has_game:
                                print_step(f"解压后检测到游戏目录 [{game_dir_name}]，停止后续处理")
                                break
                        except Exception as e:
                            print_error(f"嵌套 7z 分卷解压异常: {item.name} | {e}")
                        continue

            nested_type = detect_archive_type(item)
            if nested_type is None:
                continue

            if self._should_skip_nested(item, nested_type):
                continue

            print_step(f"发现嵌套压缩包", f"{item.name} (层级={depth})")
            try:
                result = await self.extract(
                    file_path=str(item),
                    output_dir=str(extract_path),
                    depth=depth,
                )
                results.append(result)
                if result.success and item.exists():
                    item.unlink()
                
                # 解压后列出目录内容，方便调试
                print_step(f"解压完成，当前目录内容:", "")
                for debug_item in extract_path.iterdir():
                    type_str = "📁" if debug_item.is_dir() else "📄"
                    print(f"  {type_str} {debug_item.name}")
                
                has_game, game_dir_name = has_potential_game_dir(extract_path)
                if has_game:
                    print_step(f"解压后检测到游戏目录 [{game_dir_name}]，停止后续处理")
                    break
            except Exception as e:
                print_error(f"嵌套解压异常: {item.name} | {e}")

        return results

    async def _extract_7z_split_group(
        self,
        split_info: dict,
        output_dir: Path,
        depth: int,
        *,
        delete_sources: bool = False,
        is_split_sfx: bool = False,
        custom_password: Optional[str] = None,
        source_path: Optional[str] = None,
    ) -> ExtractResult:
        all_files = split_info["all_files"]
        base_name = split_info["base_name"]
        entry_file = split_info["extract_entry"]
        engine_label = "7-Zip(7z分卷组)" if depth == 0 else "7-Zip(嵌套分卷组)"

        work_dir = output_dir / f"7z_split_{base_name}_{os.getpid()}_{depth}"
        work_dir.mkdir(parents=True, exist_ok=True)

        t0 = time.monotonic()
        ui_extract_start(f"{base_name}.001+", engine_label)

        if custom_password:
            success, error = await asyncio.to_thread(
                self._run_extract, entry_file, str(work_dir), custom_password
            )
            used_pwd = custom_password if success else ""
            if not success:
                error = f"自定义密码解压失败: {error}"
        else:
            passwords = self.password_manager.get_passwords()
            total_attempts = 1 + len(passwords)
            ui_password_try(1, total_attempts, "(无密码)")
            success, error = await asyncio.to_thread(
                self._run_extract, entry_file, str(work_dir), None
            )
            used_pwd = ""
            if not success:
                for i, pwd in enumerate(passwords):
                    if work_dir.exists():
                        shutil.rmtree(work_dir, ignore_errors=True)
                    work_dir.mkdir(parents=True, exist_ok=True)
                    ui_password_try(i + 2, total_attempts, self._mask_pwd(pwd))
                    success, error = await asyncio.to_thread(
                        self._run_extract, entry_file, str(work_dir), pwd
                    )
                    if success:
                        used_pwd = pwd
                        self.password_manager.record_success(entry_file, pwd)
                        ui_password_success(self._mask_pwd(pwd))
                        break
                if not success:
                    error = self._classify_error(error, bool(passwords))

        nested_results: list[ExtractResult] = []
        max_depth = self._settings.extraction.max_recursive_depth
        if success and depth < max_depth:
            nested_results = await self._extract_nested(work_dir, str(work_dir), depth + 1)

        if success:
            output_dir.mkdir(parents=True, exist_ok=True)
            for item in work_dir.iterdir():
                dest = output_dir / item.name
                dest = self._resolve_conflict(dest)
                try:
                    shutil.move(str(item), str(dest))
                except Exception:
                    pass

        elapsed = time.monotonic() - t0
        if success:
            detail = f"格式=7z分卷组({len(all_files)}个) | 密码={self._mask_pwd(used_pwd)}"
            if nested_results:
                detail += f" | 递归解压{len(nested_results)}个嵌套包"
            ui_extract_success(f"{base_name}.001+", detail, elapsed)
            if delete_sources:
                for f in all_files:
                    p = Path(f)
                    if p.exists():
                        try:
                            p.unlink()
                        except OSError:
                            pass
        else:
            ui_extract_fail(f"{base_name}.001+", error, elapsed)

        shutil.rmtree(work_dir, ignore_errors=True)

        result_path = source_path or entry_file
        return ExtractResult(
            success=success,
            file_path=result_path,
            file_name=Path(result_path).name,
            extract_dir=str(output_dir),
            used_password=used_pwd,
            archive_type="7z",
            is_split_sfx=is_split_sfx,
            split_sfx_files=all_files if is_split_sfx else [],
            nested_results=nested_results,
            depth=depth,
            error=error if not success else "",
        )

    NESTED_ANDROID_MARKERS: set[str] = {
        "AndroidManifest.xml", "classes.dex", "resources.arsc",
        "META-INF", "META-INF/",
    }

    def _should_skip_nested(self, item: Path, archive_type: str) -> bool:
        name_lower = item.name.lower()
        stem_lower = item.stem.lower()

        for skip in self.NESTED_SKIP_NAMES:
            if skip in stem_lower or skip in name_lower:
                return True

        if item.suffix.lower() in self.NESTED_SKIP_EXTENSIONS:
            logger.info(f"跳过嵌套压缩包(后缀拦截): {item.name}")
            return True

        try:
            file_size = item.stat().st_size
            if file_size < self.NESTED_MAX_FILE_SIZE:
                parent_lower = item.parent.name.lower()
                game_content_indicators = [
                    "www", "data", "audio", "bg", "cg", "img", "image",
                    "save", "font", "movie", "video", "bgm", "se", "me",
                    "game", "game_data", "resource", "assets",
                ]
                if any(ind in parent_lower for ind in game_content_indicators):
                    return True
                logger.info(f"跳过嵌套压缩包(体积不足200MB): {item.name} ({file_size / 1024 / 1024:.1f}MB)")
                return True
        except OSError:
            pass

        return False

    @staticmethod
    def _mask_pwd(pwd: str) -> str:
        if not pwd:
            return "(无密码)"
        if len(pwd) <= 2:
            return "*" * len(pwd)
        return pwd[0] + "*" * (len(pwd) - 2) + pwd[-1]

    @staticmethod
    def _resolve_conflict(dest: Path) -> Path:
        if not dest.exists():
            return dest
        stem = dest.stem if dest.is_file() else dest.name
        suffix = dest.suffix if dest.is_file() else ""
        parent = dest.parent
        counter = 1
        while True:
            new_name = f"{stem}_{counter}{suffix}"
            new_dest = parent / new_name
            if not new_dest.exists():
                return new_dest
            counter += 1
