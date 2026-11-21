"""Lưu trữ project: mỗi project là một thư mục chứa project.json + pages/ + work/."""
import os, json, re, shutil, threading
from config import PROJECTS_DIR

_lock = threading.RLock()
DEFAULT = {"lang": "ja", "glossary": [],
           "settings": {"provider": "gtx", "api_key": "", "model": "", "style": "", "notes": ""},
           "lettering": {"font": "BeVietnamPro-Bold", "color": "", "stroke_color": ""},
           "pages": []}


def _nat(s):
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", s)]


def safe(name):
    n = re.sub(r"[^\w\- ]", "_", name.strip(), flags=re.U)
    if not n:
        raise ValueError("Tên project không hợp lệ")
    return n


def pdir(name):
    return os.path.join(PROJECTS_DIR, safe(name))


def path(name, *p):
    return os.path.join(pdir(name), *p)


def list_projects():
    return sorted(d for d in os.listdir(PROJECTS_DIR) if os.path.isfile(os.path.join(PROJECTS_DIR, d, "project.json")))


def create(name):
    d = pdir(name)
    os.makedirs(os.path.join(d, "pages"), exist_ok=True)
    os.makedirs(os.path.join(d, "work"), exist_ok=True)
    if not os.path.exists(os.path.join(d, "project.json")):
        save(name, json.loads(json.dumps(DEFAULT)))
    return load(name)


def load(name):
    with _lock, open(path(name, "project.json"), encoding="utf8") as f:
        data = json.load(f)
    for k, v in DEFAULT.items():
        data.setdefault(k, json.loads(json.dumps(v)))
    old = (data.get("settings") or {}).get("api_key")
    if old:  # bản cũ lưu key dạng chữ thường trong project -> chuyển sang kho mã hoá rồi xoá khỏi file
        import secretstore
        if not secretstore.get(data["settings"].get("provider", "")):
            secretstore.set(data["settings"].get("provider", ""), old)
        data["settings"]["api_key"] = ""
        save(name, data)
    return data


def save(name, data):
    with _lock:
        tmp = path(name, "project.json.tmp")
        with open(tmp, "w", encoding="utf8") as f:
            json.dump(data, f, ensure_ascii=False, indent=1)
        os.replace(tmp, path(name, "project.json"))


def add_pages(name, files):
    """files: [(filename, bytes)] -> thêm vào project theo thứ tự tự nhiên."""
    data = load(name)
    existing = {p["file"] for p in data["pages"]}
    for fn, blob in sorted(files, key=lambda x: _nat(x[0])):
        fn = os.path.basename(fn)
        base, ext = os.path.splitext(fn)
        i = 1
        while fn in existing:
            fn = f"{base}_{i}{ext}"
            i += 1
        with open(path(name, "pages", fn), "wb") as f:
            f.write(blob)
        data["pages"].append({"file": fn, "status": "new", "blocks": [], "rev": 0})
        existing.add(fn)
    save(name, data)
    return data


def delete(name):
    shutil.rmtree(pdir(name), ignore_errors=True)
