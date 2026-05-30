import os
import re
import sys
import time
import hmac
import binascii
from dataclasses import dataclass
from datetime import datetime
from typing import Tuple, Optional, List

from hashlib import pbkdf2_hmac

try:
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
    from cryptography.hazmat.backends import default_backend
except Exception:
    print("缺少依赖 cryptography，请先安装: python -m pip install cryptography")
    sys.exit(3)

# 导入备份模块
from paths import OUTPUT_DIR, PLAINTEXT_DIR, DICT_PATH, CANDIDATES_PATH

try:
    from backup_script import perform_backup
    BACKUP_AVAILABLE = True
except ImportError:
    BACKUP_AVAILABLE = False
    print("[警告] 备份模块不可用，跳过自动备份")

# 常量盐值（与 hbe.js 保持一致）
SALT_R = "hexo-blog-encrypt的作者们都是大帅比!".encode("utf-8")
SALT_O = "hexo-blog-encrypt是地表最强Hexo加密插件!".encode("utf-8")
PREFIX = "<hbe-prefix></hbe-prefix>".encode("utf-8")

# 失败记录数据结构（用于AUTO模式批量尝试的失败缓存）
@dataclass
class FailedAttempt:
    password: str
    start_ts: float
    end_ts: float
    error_msg: str = ""  # 存储异常信息（如有）

# 全局缓存：仅用于AUTO模式下的字典/候选列表失败记录
failed_attempts: List[FailedAttempt] = []

def parse_hbe_html(html_path: str) -> Tuple[str, str]:
    """从离线 HTML 中提取密文和 HMAC 摘要（十六进制）。"""
    if not os.path.isfile(html_path):
        raise FileNotFoundError(f"密文文件不存在: {html_path}")
    with open(html_path, "r", encoding="utf-8", errors="ignore") as f:
        content = f.read()
    # 允许换行与空白，做宽松匹配
    m = re.search(r"<script[^>]*data-hmacdigest=\"([0-9a-fA-F]+)\"[^>]*>([0-9a-fA-F]+)</script>", content, re.DOTALL)
    if not m:
        raise ValueError("未找到 hbeData 脚本块或格式不符（data-hmacdigest + 十六进制密文）")
    hmac_hex = m.group(1)
    cipher_hex = m.group(2)
    return cipher_hex.strip(), hmac_hex.strip()

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
    # 前缀校验
    if not plaintext.startswith(PREFIX):
        return False
    # HMAC 校验
    dig = hmac.new(hmac_key, plaintext, "sha256").hexdigest()
    return dig.lower() == expected_hmac_hex.lower()

def write_report(cipher_path: str, password: str, ok: bool, plaintext: Optional[bytes], start_ts: float, end_ts: float, out_dir: str) -> str:
    """生成单个密码尝试的报告（非批量场景）"""
    os.makedirs(out_dir, exist_ok=True)
    stamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    report_path = os.path.join(out_dir, f"decrypt_report_{stamp}.txt")
    lines = []
    lines.append(f"密文文件: {cipher_path}")
    lines.append(f"使用密码: {password}")
    lines.append(f"开始时间: {datetime.fromtimestamp(start_ts).strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append(f"结束时间: {datetime.fromtimestamp(end_ts).strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append(f"耗时(秒): {end_ts - start_ts:.3f}")
    lines.append(f"解密结果: {'成功' if ok else '失败'}")
    lines.append("")
    if ok and plaintext is not None:
        # 保存明文与预览
        preview = plaintext[:200].decode('utf-8', errors='ignore')
        lines.append("明文预览(前200字节, UTF-8):")
        lines.append(preview)
        # 同步保存完整明文（去除 HBE 前缀，与批量脚本一致）
        body = plaintext[len(PREFIX):] if plaintext.startswith(PREFIX) else plaintext
        os.makedirs(PLAINTEXT_DIR, exist_ok=True)
        plain_file = os.path.join(PLAINTEXT_DIR, f"plaintext_{stamp}.html")
        with open(plain_file, 'wb') as pf:
            pf.write(body)
        lines.append("")
        lines.append(f"完整明文: {plain_file}")
    with open(report_path, 'w', encoding='utf-8-sig') as rf:
        rf.write('\n'.join(lines))
    return report_path

def write_summary_failed_report(cipher_path: str, start_ts: float, end_ts: float, out_dir: str) -> str:
    """生成字典/候选列表批量尝试的汇总失败报告"""
    os.makedirs(out_dir, exist_ok=True)
    stamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    report_path = os.path.join(out_dir, f"failed_summary_report_{stamp}.txt")
    
    lines = []
    lines.append("=" * 50)
    lines.append("字典/候选列表批量尝试汇总失败报告")
    lines.append("=" * 50)
    lines.append(f"密文文件: {cipher_path}")
    lines.append(f"开始时间: {datetime.fromtimestamp(start_ts).strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append(f"结束时间: {datetime.fromtimestamp(end_ts).strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append(f"总耗时(秒): {end_ts - start_ts:.3f}")
    lines.append(f"尝试密码总数: {len(failed_attempts)}")
    lines.append(f"失败数: {len(failed_attempts)}")
    lines.append("")
    lines.append("详细失败记录:")
    lines.append("-" * 30)
    
    # 遍历所有失败记录，按顺序输出
    for idx, attempt in enumerate(failed_attempts, 1):
        lines.append(f"\n[{idx}] 尝试密码: {attempt.password}")
        lines.append(f"  开始时间: {datetime.fromtimestamp(attempt.start_ts).strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append(f"  耗时(秒): {attempt.end_ts - attempt.start_ts:.3f}")
        lines.append(f"  错误信息: {attempt.error_msg if attempt.error_msg else '无'}")
    
    with open(report_path, 'w', encoding='utf-8-sig') as rf:
        rf.write('\n'.join(lines))
    return report_path

CAND_PATH = str(CANDIDATES_PATH)

def load_password_dict(path: str = None) -> List[str]:
    if path is None:
        path = str(DICT_PATH)
    if not os.path.isfile(path):
        return []
    with open(path, 'r', encoding='utf-8', errors='ignore') as f:
        return [line.strip() for line in f if line.strip()]

def add_password_to_dict(password: str, path: str = None) -> None:
    if path is None:
        path = str(DICT_PATH)
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    existing = set(load_password_dict(path))
    if password and password not in existing:
        with open(path, 'a', encoding='utf-8') as f:
            f.write(password + '\n')

def read_candidates(path: str = CAND_PATH) -> List[str]:
    if not os.path.isfile(path):
        return []
    with open(path, 'r', encoding='utf-8', errors='ignore') as f:
        return [line.strip() for line in f if line.strip()]

def attempt_and_report(cipher_path: str, password: str, generate_report: bool = True) -> bool:
    """尝试解密并生成报告（支持静默失败模式）"""
    start_ts = time.time()
    error_msg = ""
    plaintext = None
    try:
        cipher_hex, hmac_hex = parse_hbe_html(cipher_path)
        aes_key, hmac_key, iv = derive_keys(password)
        plaintext = aes_cbc_decrypt(cipher_hex, aes_key, iv)
        ok = verify_success(plaintext, hmac_key, hmac_hex)
    except Exception as e:
        error_msg = str(e)
        ok = False
    end_ts = time.time()

    # 仅在非批量尝试时或成功时生成独立报告
    if generate_report:
        # 非批量尝试模式：生成报告并输出详细信息
        report_path = write_report(
            cipher_path, password, ok, plaintext if ok else None,
            start_ts, end_ts, str(OUTPUT_DIR)
        )
        print(f"解密 {'成功' if ok else '失败'}，报告: {report_path}")
        if error_msg:
            print(f"错误: {error_msg}")
    else:
        # 批量尝试模式（AUTO模式）：
        if ok:
            # 成功时生成报告
            report_path = write_report(
                cipher_path, password, ok, plaintext,
                start_ts, end_ts, str(OUTPUT_DIR)
            )
            print(f"解密成功！报告: {report_path}")
        else:
            # 失败时仅输出简洁日志，不生成单个报告
            print(f"密码 {password} 失败（{'无异常' if not error_msg else f'错误: {error_msg}'}）")
            # 缓存失败记录（用于生成汇总报告）
            failed_attempts.append(FailedAttempt(
                password=password,
                start_ts=start_ts,
                end_ts=end_ts,
                error_msg=error_msg
            ))

    if ok:
        add_password_to_dict(password)
        print(f"已将密码加入字典: {DICT_PATH}")
        print("提示: 完整明文已写入 output/plaintext 目录。")
    return ok

def brute_force_numeric(cipher_path: str) -> bool:
    """穷举4-6位纯数字密码并尝试解密"""
    print("字典和候选密码均失败，开始尝试4-6位纯数字密码...")
    
    # 尝试4位数字 (1000-9999)
    print("开始尝试4位数字密码...")
    for num in range(1000, 10000):
        password = str(num)
        if attempt_and_report(cipher_path, password, generate_report=False):
            return True
        # 每1000次尝试输出进度
        if num % 1000 == 0:
            print(f"已尝试4位数字: {num}/9999")
    
    # 尝试5位数字 (10000-99999)
    print("开始尝试5位数字密码...")
    for num in range(10000, 100000):
        password = str(num)
        if attempt_and_report(cipher_path, password, generate_report=False):
            return True
        if num % 5000 == 0:
            print(f"已尝试5位数字: {num}/99999")
    
    # 尝试6位数字 (100000-999999)
    print("开始尝试6位数字密码...")
    for num in range(100000, 1000000):
        password = str(num)
        if attempt_and_report(cipher_path, password, generate_report=False):
            return True
        if num % 10000 == 0:
            print(f"已尝试6位数字: {num}/999999")
    
    print("4-6位数字密码尝试完毕，均失败")
    return False

def main():
    # 首先执行自动备份
    if BACKUP_AVAILABLE:
        print("[系统] 正在执行自动备份...")
        try:
            backup_result = perform_backup()
            if backup_result.get("disabled"):
                pass
            elif backup_result["failed"] > 0:
                print(f"[警告] 备份过程中有 {backup_result['failed']} 个文件失败")
        except Exception as e:
            print(f"[警告] 自动备份失败: {str(e)}")
        print()
    
    if len(sys.argv) < 3:
        print("用法: python decry-chunyang.py <密文HTML路径> <授权密码或AUTO>")
        print("说明: 若使用 AUTO，则先尝试字典密码，再尝试候选密码，最后尝试4-6位纯数字密码")
        sys.exit(1)
    cipher_path = sys.argv[1]
    password = sys.argv[2]

    if password.upper() == 'AUTO':
        # 记录AUTO模式整体开始时间
        auto_start_ts = time.time()
        # 清空全局失败缓存（避免多次运行残留）
        global failed_attempts
        failed_attempts = []

        # 1) 先尝试字典（静默失败，不生成独立报告）
        dict_pwds = load_password_dict()
        if dict_pwds:
            print(f"优先尝试字典密码（{len(dict_pwds)}个）...")
            for pw in dict_pwds:
                if attempt_and_report(cipher_path, pw, generate_report=False):
                    return
        else:
            print("字典为空，跳过字典尝试。")
        
        # 2) 尝试候选列表（静默失败，不生成独立报告）
        cand_pwds = read_candidates()
        if cand_pwds:
            print(f"\n尝试候选列表（{len(cand_pwds)}个）...")
            for pw in cand_pwds:
                if attempt_and_report(cipher_path, pw, generate_report=False):
                    return
            print("候选列表均失败。")
        else:
            print("未提供候选列表 candidates.txt，跳过候选尝试。")
        
        # 生成汇总失败报告（仅字典/候选列表有失败记录时）
        if failed_attempts:
            auto_end_ts = time.time()
            report_path = write_summary_failed_report(
                cipher_path, auto_start_ts, auto_end_ts,
                str(OUTPUT_DIR)
            )
            print(f"\n字典/候选列表尝试完毕，汇总失败报告: {report_path}")
        
        # 3) 尝试4-6位纯数字密码
        if brute_force_numeric(cipher_path):
            return
        # 所有密码尝试都失败，生成最终汇总失败报告
        auto_end_ts = time.time()
        report_path = write_summary_failed_report(
            cipher_path, auto_start_ts, auto_end_ts,
            str(OUTPUT_DIR)
        )
        print(f"\n所有密码尝试完毕，均失败。汇总报告: {report_path}")
        sys.exit(2)

    # 明确密码（非AUTO模式）：保持原有独立报告逻辑
    ok = attempt_and_report(cipher_path, password, generate_report=True)
    sys.exit(0 if ok else 2)

if __name__ == '__main__':
    main()