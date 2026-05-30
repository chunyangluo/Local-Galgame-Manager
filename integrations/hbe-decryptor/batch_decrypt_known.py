import sys
import re
import hmac
import binascii
from pathlib import Path
from typing import List, Tuple
from hashlib import pbkdf2_hmac
import time
import csv
import json
from datetime import datetime

from paths import ROOT

try:
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
    from cryptography.hazmat.backends import default_backend
except Exception:
    print("缺少依赖 cryptography，请先安装: python -m pip install cryptography")
    sys.exit(3)

# 常量（与 hbe.js 一致）
SALT_R = "hexo-blog-encrypt的作者们都是大帅比!".encode("utf-8")
SALT_O = "hexo-blog-encrypt是地表最强Hexo加密插件!".encode("utf-8")
PREFIX = "<hbe-prefix></hbe-prefix>".encode("utf-8")


def parse_hbe_html(html_path: Path) -> Tuple[str, str]:
    """从离线 HTML 中提取密文与 HMAC 摘要（十六进制）。"""
    if not html_path.is_file():
        raise FileNotFoundError(f"密文文件不存在: {html_path}")
    content = html_path.read_text(encoding="utf-8", errors="ignore")
    m = re.search(r"<script[^>]*data-hmacdigest=\"([0-9a-fA-F]+)\"[^>]*>([0-9a-fA-F]+)</script>", content, re.DOTALL)
    if not m:
        raise ValueError("未找到 hbeData 脚本块或格式不符（data-hmacdigest + 十六进制密文）")
    hmac_hex = m.group(1).strip()
    cipher_hex = m.group(2).strip()
    return cipher_hex, hmac_hex


def derive_keys(password: str) -> Tuple[bytes, bytes, bytes]:
    """派生 AES 密钥、HMAC 密钥与 128-bit IV。"""
    pw_bytes = password.encode("utf-8")
    aes_key = pbkdf2_hmac("sha256", pw_bytes, SALT_R, 1024, dklen=32)
    hmac_key = pbkdf2_hmac("sha256", pw_bytes, SALT_R, 1024, dklen=32)
    iv = pbkdf2_hmac("sha256", pw_bytes, SALT_O, 512, dklen=16)
    return aes_key, hmac_key, iv


def aes_cbc_decrypt(cipher_hex: str, key: bytes, iv: bytes) -> bytes:
    data = binascii.unhexlify(cipher_hex)
    cipher = Cipher(algorithms.AES(key), modes.CBC(iv), backend=default_backend())
    decryptor = cipher.decryptor()
    plaintext_padded = decryptor.update(data) + decryptor.finalize()
    # PKCS#7 去填充
    pad_len = plaintext_padded[-1]
    if pad_len < 1 or pad_len > 16:
        return plaintext_padded
    if any(b != pad_len for b in plaintext_padded[-pad_len:]):
        return plaintext_padded
    return plaintext_padded[:-pad_len]


def verify_success(plaintext: bytes, hmac_key: bytes, expected_hmac_hex: str) -> bool:
    if not plaintext.startswith(PREFIX):
        return False
    dig = hmac.new(hmac_key, plaintext, "sha256").hexdigest()
    return dig.lower() == expected_hmac_hex.lower()


def write_plaintext(output_dir: Path, src_name: str, plaintext: bytes) -> Path:
    """保存明文为 .html 文件；去除前缀标记。"""
    output_dir.mkdir(parents=True, exist_ok=True)
    # 去除前缀标记
    if plaintext.startswith(PREFIX):
        plaintext = plaintext[len(PREFIX):]
    text = plaintext.decode("utf-8", errors="ignore")
    out_path = output_dir / (Path(src_name).name)
    out_path.write_text(text, encoding="utf-8", errors="ignore")
    return out_path


def find_html_files(ciphertext_dir: Path) -> List[Path]:
    """在指定目录下查找所有 .html 文件（仅一层）。"""
    if not ciphertext_dir.exists():
        return []
    return [p for p in ciphertext_dir.glob("*.html") if p.is_file()]


def write_summary(rows: List[dict], output_root: Path) -> Tuple[Path, Path]:
    output_root.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    csv_path = output_root / f"decrypt_summary_{ts}.csv"
    json_path = output_root / f"decrypt_summary_{ts}.json"
    headers = ["解密结果", "开始时间", "耗时", "错误信息", "尝试密码", "文件大小", "文件名"]
    with open(csv_path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=headers)
        writer.writeheader()
        for r in rows:
            writer.writerow({k: r.get(k, "") for k in headers})
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False, indent=2)
    print(f"汇总已生成：CSV -> {csv_path}")
    print(f"汇总已生成：JSON -> {json_path}")
    return csv_path, json_path


def batch_decrypt(password: str, ciphertext_dir: Path, output_dir: Path) -> Tuple[int, int]:
    aes_key, hmac_key, iv = derive_keys(password)
    files = find_html_files(ciphertext_dir)
    if not files:
        print(f"未在目录中找到 .html 文件: {ciphertext_dir}")
        return 0, 0

    ok_count = 0
    fail_count = 0
    rows: List[dict] = []
    print(f"开始批量解密，共 {len(files)} 个文件，使用已知密码。")

    for html_file in files:
        start_ts = time.time()
        err = ""
        ok = False
        try:
            cipher_hex, hmac_hex = parse_hbe_html(html_file)
            plaintext = aes_cbc_decrypt(cipher_hex, aes_key, iv)
            ok = verify_success(plaintext, hmac_key, hmac_hex)
            if ok:
                out_path = write_plaintext(output_dir, html_file.name, plaintext)
                ok_count += 1
                print(f"[成功] {html_file.name} -> {out_path}")
            else:
                fail_count += 1
                err = "校验不通过（前缀或HMAC不匹配）"
                print(f"[失败] {html_file.name}: {err}")
        except Exception as e:
            fail_count += 1
            err = str(e)
            print(f"[异常] {html_file.name}: {e}")
        end_ts = time.time()
        rows.append({
            "解密结果": "成功" if ok else "失败",
            "开始时间": datetime.fromtimestamp(start_ts).strftime("%Y-%m-%d %H:%M:%S"),
            "耗时": round(end_ts - start_ts, 3),
            "错误信息": err,
            "尝试密码": password,
            "文件大小": html_file.stat().st_size if html_file.exists() else 0,
            "文件名": html_file.name,
        })

    # 汇总写出到 output 根目录
    output_root = output_dir.parent
    write_summary(rows, output_root)

    print(f"完成：成功 {ok_count}，失败 {fail_count}。输出目录: {output_dir}")
    return ok_count, fail_count


def resolve_default_paths(ciphertext_dir_arg: str = None, output_dir_arg: str = None) -> Tuple[Path, Path]:
    """根据传入参数或默认规则解析目录路径。默认：脚本同级的 ./ciphertext 与 ./output/plaintext。"""
    base_dir = ROOT
    ciphertext_dir = Path(ciphertext_dir_arg).resolve() if ciphertext_dir_arg else base_dir / "ciphertext"
    output_dir = Path(output_dir_arg).resolve() if output_dir_arg else base_dir / "output" / "plaintext"
    return ciphertext_dir, output_dir


def main():
    # 用法：python batch_decrypt_known.py <password> [ciphertext_dir] [output_dir]
    if len(sys.argv) < 2:
        print("用法：python batch_decrypt_known.py <密码> [密文目录] [明文输出目录]")
        print("默认：密文目录=脚本同级的 ./ciphertext，输出目录=脚本同级的 ./output/plaintext")
        sys.exit(1)

    password = sys.argv[1]
    ciphertext_dir_arg = sys.argv[2] if len(sys.argv) >= 3 else None
    output_dir_arg = sys.argv[3] if len(sys.argv) >= 4 else None

    ciphertext_dir, output_dir = resolve_default_paths(ciphertext_dir_arg, output_dir_arg)
    ok_count, fail_count = batch_decrypt(password, ciphertext_dir, output_dir)

    if fail_count == 0 and ok_count > 0:
        sys.exit(0)
    elif ok_count == 0 and fail_count == 0:
        # 没有文件可处理
        sys.exit(1)
    else:
        sys.exit(2)


if __name__ == "__main__":
    main()