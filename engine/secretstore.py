"""Kho API key của người dùng — tách khỏi file project.

- Lưu ở HOME_DIR (%LOCALAPPDATA%\\MangaForge\\secrets.dat): KHÔNG nằm trong Documents (thường đồng bộ OneDrive)
  và không theo thư mục project khi bạn chia sẻ project cho người khác.
- Trên Windows: mã hoá bằng DPAPI (CryptProtectData, phạm vi người dùng hiện tại) — chỉ đúng tài khoản Windows
  trên đúng máy này giải mã được.
- Trên Linux: giới hạn quyền truy cập file cho chủ sở hữu. Dữ liệu lưu ở dạng base64, không mã hoá.
- Giao diện chỉ nhận về dạng che (••••abcd), không bao giờ nhận lại key đầy đủ.
"""
import base64
import json
import os
import sys
import tempfile
import threading

from config import HOME_DIR

PATH = os.path.join(HOME_DIR, "secrets.dat")
_lock = threading.Lock()
_ENTROPY = b"MangaForge.secrets.v1"


if sys.platform == "win32":
    import ctypes
    from ctypes import wintypes

    class _Blob(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]

    def _blob(b):
        buf = ctypes.create_string_buffer(b, len(b))
        return _Blob(len(b), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char))), buf

    def _protect(data: bytes) -> bytes:
        src, _k1 = _blob(data)
        ent, _k2 = _blob(_ENTROPY)
        out = _Blob()
        if not ctypes.windll.crypt32.CryptProtectData(ctypes.byref(src), "MangaForge", ctypes.byref(ent),
                                                      None, None, 0x1, ctypes.byref(out)):  # UI_FORBIDDEN
            raise OSError("CryptProtectData thất bại")
        try:
            return ctypes.string_at(out.pbData, out.cbData)
        finally:
            ctypes.windll.kernel32.LocalFree(out.pbData)

    def _unprotect(data: bytes) -> bytes:
        src, _k1 = _blob(data)
        ent, _k2 = _blob(_ENTROPY)
        out = _Blob()
        if not ctypes.windll.crypt32.CryptUnprotectData(ctypes.byref(src), None, ctypes.byref(ent),
                                                        None, None, 0x1, ctypes.byref(out)):
            raise OSError("CryptUnprotectData thất bại (key được tạo bởi tài khoản/máy khác?)")
        try:
            return ctypes.string_at(out.pbData, out.cbData)
        finally:
            ctypes.windll.kernel32.LocalFree(out.pbData)
else:  # máy không phải Windows: chỉ giới hạn quyền đọc file cho chủ sở hữu
    def _protect(data: bytes) -> bytes:
        return base64.b64encode(data)

    def _unprotect(data: bytes) -> bytes:
        return base64.b64decode(data)


def _load():
    if not os.path.exists(PATH):
        return {}
    try:
        return json.loads(_unprotect(open(PATH, "rb").read()).decode("utf8"))
    except Exception as e:
        print("Không đọc được kho key:", e)
        return {}


def _save(d):
    os.makedirs(HOME_DIR, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".secrets-", dir=HOME_DIR)
    try:
        with os.fdopen(fd, "wb") as f:
            if sys.platform != "win32" and os.fstat(f.fileno()).st_mode & 0o077:
                raise PermissionError("Thư mục lưu API key phải hỗ trợ quyền file riêng tư.")
            f.write(_protect(json.dumps(d).encode("utf8")))
        os.replace(tmp, PATH)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def get(provider):
    with _lock:
        return _load().get(provider, "")


def set(provider, key):
    with _lock:
        d = _load()
        if key:
            d[provider] = key.strip()
        else:
            d.pop(provider, None)
        _save(d)


def mask(key):
    if not key:
        return ""
    return "••••" + key[-4:] if len(key) > 8 else "••••"


def status():
    """{provider: '••••abcd'} — để giao diện biết provider nào đã có key."""
    with _lock:
        return {p: mask(k) for p, k in _load().items() if k}
