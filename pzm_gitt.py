#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# File auto-generated - pzm self-decryptor
import requests, struct, base64, json
from argon2.low_level import hash_secret_raw, Type
from ecdsa import VerifyingKey, NIST521p
from Crypto.Cipher import AES


import sys
import importlib
import types
import threading
import time
import traceback
import builtins
import os
from types import MappingProxyType
from typing import Dict, Any

# ---------------- ProxyModule ----------------
class ProxyModule(types.ModuleType):
    __slots__ = ("_orig", "_token", "_internal_changes")

    def __init__(self, orig_module, token):
        super().__init__(getattr(orig_module, "__name__", "<anon>"))
        object.__setattr__(self, "_orig", orig_module)
        object.__setattr__(self, "_token", token)
        object.__setattr__(self, "_internal_changes", {})

    def __getattribute__(self, name):
        if name in ("_orig", "_token", "_internal_changes", "__class__", "__name__"):
            return object.__getattribute__(self, name)
        orig = object.__getattribute__(self, "_orig")
        try:
            return getattr(orig, name)
        except AttributeError:
            raise AttributeError(name)

    def __setattr__(self, name, value):
        if isinstance(value, tuple) and len(value) == 2 and value[1] is self._token:
            real_value = value[0]
            setattr(self._orig, name, real_value)
            self._internal_changes[name] = real_value
            return
        raise AttributeError(f"Module '{self.__name__}' is read-only via ProxyModule.")

    def _force_set(self, name, value, token):
        if token is not self._token:
            raise RuntimeError("invalid token")
        setattr(self._orig, name, value)
        self._internal_changes[name] = value


# ---------------- Watchdog implementation ----------------

UocGiTaoBotDangCapDeSongHoaDongThiTotBietBao = [
    "requests.Session.request",
    "ssl.SSLSocket.send",
    "ssl.SSLSocket.recv",
    "http",
    "httpx",
    "aiohttp",
    "http.client",
    "http.server",
    "urllib",
    "urllib.request",
    "urllib.parse",
    "socket",
    "asyncio",
    "selectors",
    "xmlrpc.client",
    "xmlrpc.server",
    "email",
    "json",
    "urllib3",
    "pycurl",
    "curl",
    "curllib",
    "builtins.__import__",
]

class _AntiHookWatchdog:
    def __init__(self, paths=None, check_interval=2.0):
        self.paths = paths or UocGiTaoBotDangCapDeSongHoaDongThiTotBietBao
        self.check_interval = check_interval
        self._token = object()
        self._orig_modules: Dict[str, Any] = {}
        self._proxy_modules: Dict[str, ProxyModule] = {}
        self._orig_import = builtins.__import__
        self._installed = False
        self._stop_evt = threading.Event()
        self._watcher_thread = None

    def _import_if_exists(self, name):
        try:
            return importlib.import_module(name)
        except Exception:
            return None

    def _base_module_of(self, dotted):
        parts = dotted.split(".")
        return parts[0]

    def _wrap_module(self, name):
        mod = self._import_if_exists(name)
        if mod is None:
            return False, "missing"
        if name in self._proxy_modules:
            return True, "already-proxied"
        self._orig_modules[name] = mod
        proxy = ProxyModule(mod, self._token)
        sys.modules[name] = proxy
        orig = mod
        for mname, mobj in list(sys.modules.items()):
            try:
                if mobj is orig or mobj is proxy:
                    continue
                for attr, val in list(vars(mobj).items()):
                    if val is orig:
                        try:
                            setattr(mobj, attr, proxy)
                        except Exception:
                            pass
            except Exception:
                pass

        return True, "proxied"

    def _wrap_builtins_import(self):
        orig_import = self._orig_import
        proxydict = self._proxy_modules

        def _my_import(name, globals=None, locals=None, fromlist=(), level=0):
            mod = orig_import(name, globals, locals, fromlist, level)
            base = name.split(".")[0]
            if base in proxydict:
                return proxydict[base]
            return mod

        builtins.__import__ = _my_import

    def _restore_original_import(self):
        builtins.__import__ = self._orig_import

    def install(self):
        if self._installed:
            return {"status": "already_installed"}
        results = {}
        module_bases = set(self._base_module_of(p) for p in self.paths)
        for base in module_bases:
            if base == "builtins":
                continue
            ok, msg = self._wrap_module(base)
            results[base] = msg

        if "builtins.__import__" in self.paths:
            self._wrap_builtins_import()
            results["builtins.__import__"] = "wrapped"
        self._saved_dotted = {}
        for dotted in self.paths:
            if dotted == "builtins.__import__":
                self._saved_dotted[dotted] = builtins.__import__
                continue
            parts = dotted.split(".")
            try:
                base_mod = importlib.import_module(parts[0])
                cur = base_mod
                for p in parts[1:]:
                    cur = getattr(cur, p)
                self._saved_dotted[dotted] = cur
            except Exception:
                self._saved_dotted[dotted] = None

        self._stop_evt.clear()
        self._watcher_thread = threading.Thread(target=self._watch_loop, daemon=True)
        self._watcher_thread.start()
        self._installed = True
        return {"status": "installed", "results": results}

    def _report_and_exit(self, msg, details=None):
        try:
            print("[watchdogantihook] DETECTED TAMPER — exiting now")
            print("reason:", msg)
            if details:
                print("details:", details)
            print("traceback:")
            traceback.print_stack()
        except Exception:
            pass
        os._exit(1)

    def _check_once(self):
        if "builtins.__import__" in self.paths:
            cur = builtins.__import__
            if cur is not self._orig_import:
                if cur is not builtins.__import__:
                    pass
            if cur is not builtins.__import__ and cur is not self._orig_import and not isinstance(cur, type(self._orig_import)):
                saved = self._saved_dotted.get("builtins.__import__", None)
                if saved is not None and cur is not saved:
                    self._report_and_exit("builtins.__import__ replaced externally", {"current": repr(cur), "expected": repr(saved)})

        for dotted, saved in list(self._saved_dotted.items()):
            if dotted == "builtins.__import__":
                continue
            try:
                parts = dotted.split(".")
                base_mod = importlib.import_module(parts[0])
                cur = base_mod
                for p in parts[1:]:
                    cur = getattr(cur, p)
            except Exception:
                cur = None
            if cur is saved:
                continue
            allowed = False
            if isinstance(cur, ProxyModule):
                allowed = True
            if saved is None:
                if cur is not None:
                    self._report_and_exit("unexpected new symbol created", {"dotted": dotted, "current": repr(cur)})
                continue
            if not allowed:
                base = parts[0]
                if base in self._proxy_modules:

                    proxy = self._proxy_modules[base]
                    pm_internal = getattr(proxy, "_internal_changes", {})
                    if parts[-1] in pm_internal:
                        allowed = True
                if not allowed:
                    self._report_and_exit("external tamper detected on dotted path", {"dotted": dotted, "expected": repr(saved), "current": repr(cur)})

    def _watch_loop(self):
        while not self._stop_evt.is_set():
            try:
                self._check_once()
            except Exception as e:
                try:
                    print("[watchdogantihook] watchdog internal error:", e)
                    traceback.print_exc()
                except Exception:
                    pass
                os._exit(1)
            time.sleep(self.check_interval)

    def uninstall(self):
        try:
            self._restore_original_import()
        except Exception:
            pass
        for name, orig in list(self._orig_modules.items()):
            try:
                sys.modules[name] = orig
            except Exception:
                pass
        self._stop_evt.set()
        if self._watcher_thread:
            self._watcher_thread.join(timeout=1.0)
        self._installed = False


# Public function
_WATCHDOG_SINGLETON: _AntiHookWatchdog = None

def watchdogantihook(paths=None, check_interval=2.0):
    global _WATCHDOG_SINGLETON
    if _WATCHDOG_SINGLETON is None:
        _WATCHDOG_SINGLETON = _AntiHookWatchdog(paths, check_interval)
    res = _WATCHDOG_SINGLETON.install()
    return res


# ---------------- Short demo ----------------
if __name__ == "__main__":
    print("Installing watchdogantihook() ...")
    r = watchdogantihook()
    print("result:", r)
    print("Watchdog running in background. Test monkeypatch by e.g.:\n  import requests\n  requests.Session.request = lambda *a, **k: None\nThen watchdog should detect and exit.")

META = {
  "enc_id": "60458",
  "api_url": "https://api-l7k1.onrender.com/data",
  "salt_b64": "rv22+nnI2pGIrfvu/3Drhw==",
  "nonce_b64": "RxWApqpHLrWSYHxk",
  "tag_b64": "CGEadjOmaq3pxbZ/KKGXKQ==",
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
