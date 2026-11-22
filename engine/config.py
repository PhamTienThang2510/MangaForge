"""Đường dẫn của MangaForge. Không có đường dẫn cố định: mọi thứ suy ra từ vị trí mã nguồn + thư mục người dùng.

Biến môi trường (tuỳ chọn) để ghi đè:
  MF_DATA    thư mục dữ liệu người dùng (project, font tự thêm)   mặc định: Documents/MangaForge
  MF_HOME    thư mục máy (model AI, engine Python)               mặc định: %LOCALAPPDATA%/MangaForge
  MF_MODELS  thư mục model AI                                     mặc định: MF_HOME/models
  MF_WEB     thư mục giao diện web                                 mặc định: <repo>/web
  MF_FONTS   thư mục font đi kèm                                   mặc định: <repo>/fonts
"""
import os
import sys

ENGINE_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_DIR = os.path.dirname(ENGINE_DIR)


def _documents():
    if sys.platform == "win32":
        try:  # thư mục Documents thật (kể cả khi bị chuyển sang OneDrive / ổ khác)
            import ctypes
            from ctypes import wintypes
            buf = ctypes.create_unicode_buffer(wintypes.MAX_PATH)
            if ctypes.windll.shell32.SHGetFolderPathW(None, 5, None, 0, buf) == 0 and buf.value:
                return buf.value
        except Exception:
            pass
    return os.path.join(os.path.expanduser("~"), "Documents")


def _local_appdata():
    if sys.platform == "win32":
        return os.environ.get("LOCALAPPDATA") or os.path.join(os.path.expanduser("~"), "AppData", "Local")
    return os.environ.get("XDG_DATA_HOME") or os.path.join(os.path.expanduser("~"), ".local", "share")


DATA_DIR = os.environ.get("MF_DATA") or os.path.join(_documents(), "MangaForge")
HOME_DIR = os.environ.get("MF_HOME") or os.path.join(_local_appdata(), "MangaForge")
MODELS_DIR = os.environ.get("MF_MODELS") or os.path.join(HOME_DIR, "models")
WEB_DIR = os.environ.get("MF_WEB") or os.path.join(REPO_DIR, "web")
FONTS_DIR = os.environ.get("MF_FONTS") or os.path.join(REPO_DIR, "fonts")
PROJECTS_DIR = os.path.join(DATA_DIR, "projects")
USER_FONTS_DIR = os.path.join(DATA_DIR, "fonts")  # font người dùng tự thêm qua nút "Thêm font"
DETECTOR_SRC = os.path.join(ENGINE_DIR, "vendor", "comic_text_detector")

for _d in (PROJECTS_DIR, USER_FONTS_DIR, MODELS_DIR):
    try:
        os.makedirs(_d, exist_ok=True)
    except OSError as _e:
        # Windows Defender "Controlled folder access" chặn tạo thư mục trong Documents -> Windows trả về WinError 2 khó hiểu.
        # Dấu MF_WRITE_BLOCKED để app desktop nhận ra và báo người dùng chọn thư mục khác.
        raise SystemExit(f"MF_WRITE_BLOCKED: không tạo được thư mục {_d} ({_e}). "
                         "Có thể Windows Defender (Controlled folder access) hoặc quyền truy cập đang chặn.")
if DETECTOR_SRC not in sys.path:
    sys.path.insert(0, DETECTOR_SRC)
