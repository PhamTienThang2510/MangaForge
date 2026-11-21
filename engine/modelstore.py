"""Tải model AI từ NGUỒN GỐC (không phát hành lại kèm app), kiểm tra SHA-256.

  python modelstore.py --status                 # liệt kê model nào đã có / còn thiếu
  python modelstore.py --download [--json]      # tải các model còn thiếu (--json: in tiến độ dạng JSON cho app desktop)
  python modelstore.py --import-from <thư mục>  # chép model sẵn có trên máy nếu checksum khớp (khỏi tải lại)

Giấy phép từng model: xem THIRD_PARTY_NOTICES.md.
"""
import argparse
import hashlib
import json
import os
import shutil
import sys
import time

import requests

from config import MODELS_DIR

HF = "https://huggingface.co/kha-white/manga-ocr-base/resolve/main/"
MODELS = [
    # (đường dẫn trong MODELS_DIR, URL nguồn gốc, sha256, kích thước byte, ghi chú)
    ("text_segmentation/comictextdetector.pt.onnx",
     "https://github.com/zyddnys/manga-image-translator/releases/download/beta-0.3/comictextdetector.pt.onnx",
     "1a86ace74961413cbd650002e7bb4dcec4980ffa21b2f19b86933372071d718f", 94669756,
     "Phát hiện chữ — comic-text-detector (GPL-3.0)"),
    ("inpaint/anime-manga-big-lama.pt",
     "https://github.com/Sanster/models/releases/download/AnimeMangaInpainting/anime-manga-big-lama.pt",
     "479d3afdcb7ed2fd944ed4ebcc39ca45b33491f0f2e43eb1000bd623cfb41823", 205717870,
     "Xoá chữ — LaMa tinh chỉnh cho manga (dreMaz/AnimeMangaInpainting, MIT)"),
    ("manga_ocr/pytorch_model.bin", HF + "pytorch_model.bin",
     "c63e0bb5b3ff798c5991de18a8e0956c7ee6d1563aca6729029815eda6f5c2eb", 444135475,
     "OCR tiếng Nhật — manga-ocr (Apache-2.0)"),
    ("manga_ocr/config.json", HF + "config.json",
     "8c0e395de8fa699daaac21aee33a4ba9bd1309cfbff03147813d2a025f39f349", 77546, ""),
    ("manga_ocr/preprocessor_config.json", HF + "preprocessor_config.json",
     "af4eb4d79cf61b47010fc0bc9352ee967579c417423b4917188d809b7e048948", 228, ""),
    ("manga_ocr/special_tokens_map.json", HF + "special_tokens_map.json",
     "303df45a03609e4ead04bc3dc1536d0ab19b5358db685b6f3da123d05ec200e3", 112, ""),
    ("manga_ocr/tokenizer_config.json", HF + "tokenizer_config.json",
     "d775ad1deac162dc56b84e9b8638f95ed8a1f263d0f56f4f40834e26e205e266", 486, ""),
    ("manga_ocr/vocab.txt", HF + "vocab.txt",
     "344fbb6b8bf18c57839e924e2c9365434697e0227fac00b88bb4899b78aa594d", 24072, ""),
]
# EasyOCR (Hàn/Trung/Anh) tự tải model của nó lần đầu dùng — không nằm trong danh sách bắt buộc.

_ok_cache = {}


def sha256(path, cb=None):
    h = hashlib.sha256()
    done = 0
    with open(path, "rb") as f:
        while True:
            b = f.read(4 << 20)
            if not b:
                break
            h.update(b)
            done += len(b)
            if cb:
                cb(done)
    return h.hexdigest()


def _ok(rel, sha, size):
    """Đã có và đúng? Kiểm kích thước luôn; checksum đầy đủ chỉ tính 1 lần rồi ghi dấu ra file .ok."""
    p = os.path.join(MODELS_DIR, rel)
    if not os.path.isfile(p) or os.path.getsize(p) != size:
        return False
    stamp = p + ".ok"
    key = f"{sha}:{size}:{int(os.path.getmtime(p))}"
    if os.path.isfile(stamp) and open(stamp).read().strip() == key:
        return True
    if sha256(p) != sha:
        return False
    open(stamp, "w").write(key)
    return True


def status():
    return [{"file": rel, "ok": _ok(rel, sha, size), "size": size, "note": note}
            for rel, url, sha, size, note in MODELS]


def missing():
    return [m for m in MODELS if not _ok(m[0], m[2], m[3])]


def all_ready():
    return not missing()


def _emit(as_json, **kw):
    if as_json:
        print(json.dumps(kw, ensure_ascii=False), flush=True)
    elif kw.get("event") == "file":
        print(f"[{kw['index']}/{kw['count']}] {kw['file']}", flush=True)
    elif kw.get("event") in ("error", "done"):
        print(kw.get("message", kw["event"]), flush=True)


def download(as_json=False, retries=4):
    todo = missing()
    total = sum(m[3] for m in todo)
    base = 0
    t0 = time.time()
    for idx, (rel, url, sha, size, note) in enumerate(todo, 1):
        dst = os.path.join(MODELS_DIR, rel)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        part = dst + ".part"
        _emit(as_json, event="file", file=rel, note=note, index=idx, count=len(todo), size=size)
        for attempt in range(retries):
            try:
                have = os.path.getsize(part) if os.path.exists(part) else 0
                if have > size:
                    os.remove(part)
                    have = 0
                headers = {"Range": f"bytes={have}-"} if have else {}
                with requests.get(url, stream=True, timeout=60, headers=headers,
                                  allow_redirects=True) as r:
                    if have and r.status_code != 206:  # máy chủ không hỗ trợ tải tiếp -> tải lại từ đầu
                        have = 0
                    r.raise_for_status()
                    last = 0
                    with open(part, "ab" if have else "wb") as f:
                        for chunk in r.iter_content(1 << 20):
                            f.write(chunk)
                            have += len(chunk)
                            now = time.time()
                            if now - last > 0.4:
                                last = now
                                done = base + have
                                spd = done / max(now - t0, 1e-3)
                                _emit(as_json, event="progress", file=rel, done=done, total=total,
                                      speed=int(spd), eta=int((total - done) / spd) if spd > 0 else None)
                if os.path.getsize(part) != size:
                    raise IOError(f"kích thước sai ({os.path.getsize(part)} ≠ {size})")
                _emit(as_json, event="verify", file=rel)
                got = sha256(part)
                if got != sha:
                    os.remove(part)
                    raise IOError(f"checksum không khớp ({got[:12]}…) — file nguồn đã thay đổi hoặc tải bị lỗi")
                os.replace(part, dst)
                _ok(rel, sha, size)
                break
            except Exception as e:
                if attempt == retries - 1:
                    _emit(as_json, event="error", file=rel, message=f"Không tải được {rel}: {e}")
                    return False
                _emit(as_json, event="retry", file=rel, message=str(e), attempt=attempt + 1)
                time.sleep(2 * (attempt + 1))
        base += size
    _emit(as_json, event="done", message="Đã đủ model.")
    return True


def import_from(folder):
    """Tìm file trùng checksum trong thư mục cho trước (đệ quy) và chép vào MODELS_DIR."""
    want = {(size, sha): rel for rel, url, sha, size, note in missing()}
    if not want:
        print("Đã đủ model, không cần nhập.")
        return 0
    sizes = {s for s, _ in want}
    n = 0
    for root, _, files in os.walk(folder):
        for fn in files:
            p = os.path.join(root, fn)
            try:
                sz = os.path.getsize(p)
            except OSError:
                continue
            if sz not in sizes:
                continue
            h = sha256(p)
            rel = want.pop((sz, h), None)
            if rel:
                dst = os.path.join(MODELS_DIR, rel)
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                shutil.copy2(p, dst)
                n += 1
                print("  nhập:", rel)
    print(f"Đã nhập {n} file. Còn thiếu {len(missing())}.")
    return n


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--status", action="store_true")
    ap.add_argument("--download", action="store_true")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--import-from")
    a = ap.parse_args()
    if a.import_from:
        import_from(a.import_from)
    if a.download:
        sys.exit(0 if download(a.json) else 1)
    if a.status or not (a.download or a.import_from):
        st = status()
        if a.json:
            print(json.dumps({"dir": MODELS_DIR, "models": st, "ready": all(s["ok"] for s in st)}, ensure_ascii=False))
        else:
            print("Thư mục model:", MODELS_DIR)
            for s in st:
                print(("  ✓ " if s["ok"] else "  ✗ ") + s["file"])
