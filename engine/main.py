import os, io, re, uuid, threading, zipfile, traceback
import cv2, numpy as np
from PIL import Image
from fastapi import FastAPI, UploadFile, File, HTTPException, Body
from fastapi.responses import Response, FileResponse
from fastapi.staticfiles import StaticFiles

import project as P
import lettering
import translate as T
from config import WEB_DIR
from engine import Engine

APP_VERSION = os.environ.get("MF_VERSION", "dev")
app = FastAPI(title="MangaForge")
JOBS = {}


def _imread(p):
    return cv2.imdecode(np.fromfile(p, np.uint8), cv2.IMREAD_COLOR)


def _imwrite(p, img):
    ok, buf = cv2.imencode(os.path.splitext(p)[1] or ".png", img)
    buf.tofile(p)


def _page(data, i):
    if not 0 <= i < len(data["pages"]):
        raise HTTPException(404, "Không có trang này")
    return data["pages"][i]


def _stem(pg):
    return os.path.splitext(pg["file"])[0]


def _lett(data):
    return {k: v for k, v in data["lettering"].items() if v not in ("", None)}


# ---------------- projects
@app.get("/api/projects")
def projects():
    return P.list_projects()


@app.post("/api/projects")
def new_project(body: dict = Body(...)):
    return P.create(body["name"])


@app.get("/api/projects/{name}")
def get_project(name: str):
    return P.load(name)


@app.delete("/api/projects/{name}")
def del_project(name: str):
    P.delete(name)
    return {"ok": True}


@app.post("/api/projects/{name}/pages")
async def upload(name: str, files: list[UploadFile] = File(...)):
    items = [(f.filename, await f.read()) for f in files]
    return P.add_pages(name, items)


@app.put("/api/projects/{name}/meta")
def meta(name: str, body: dict = Body(...)):
    d = P.load(name)
    for k in ("lang", "glossary", "settings", "lettering"):
        if k in body:
            d[k] = body[k]
    P.save(name, d)
    return {"ok": True}


# ---------------- pipeline (chạy nền, có tiến độ)
def _run_job(job, name, idxs, do_translate, do_clean):
    eng = Engine.get()
    try:
        d = P.load(name)
        history = []
        for n, i in enumerate(idxs):
            pg = d["pages"][i]
            job["msg"] = f"Trang {i + 1}/{len(d['pages'])}: nhận diện + OCR"
            img = _imread(P.path(name, "pages", pg["file"]))
            if pg["status"] == "new" or not pg["blocks"]:
                blocks, mask = eng.analyze(img, d["lang"])
                _imwrite(P.path(name, "work", _stem(pg) + "_mask.png"), mask)
                pg["blocks"] = blocks
            if do_clean:
                job["msg"] = f"Trang {i + 1}: xoá chữ (LaMa)"
                mask = _imread(P.path(name, "work", _stem(pg) + "_mask.png"))
                mask = cv2.cvtColor(mask, cv2.COLOR_BGR2GRAY) if mask is not None else np.zeros(img.shape[:2], np.uint8)
                clean, mask, patched = eng.auto_clean(img, mask, pg["blocks"])
                _imwrite(P.path(name, "work", _stem(pg) + "_mask.png"), mask)
                _imwrite(P.path(name, "work", _stem(pg) + "_clean.png"), clean)
                pg["patched"] = patched
            if do_translate:
                job["msg"] = f"Trang {i + 1}: dịch theo ngữ cảnh"
                history += T.translate_page(pg["blocks"], d["lang"], history, d["glossary"], d["settings"])
            pg["status"] = "done"
            pg["rev"] += 1
            P.save(name, d)
            job["progress"] = (n + 1) / len(idxs)
        job["state"] = "done"
        job["msg"] = "Hoàn tất"
    except Exception as e:
        traceback.print_exc()
        job["state"], job["msg"] = "error", str(e)


@app.post("/api/projects/{name}/process")
def process(name: str, body: dict = Body(default={})):
    d = P.load(name)
    idxs = body.get("pages") or list(range(len(d["pages"])))
    jid = uuid.uuid4().hex[:8]
    JOBS[jid] = {"state": "running", "progress": 0.0, "msg": "Bắt đầu"}
    threading.Thread(target=_run_job, daemon=True,
                     args=(JOBS[jid], name, idxs, body.get("translate", True), body.get("clean", True))).start()
    return {"job": jid}


@app.get("/api/jobs/{jid}")
def job(jid: str):
    return JOBS.get(jid) or {"state": "unknown"}


@app.post("/api/projects/{name}/pages/{i}/translate")
def retranslate(name: str, i: int):
    """Dịch lại một trang, dùng 12 câu của các trang trước làm ngữ cảnh."""
    d = P.load(name)
    hist = []
    for pg in d["pages"][max(0, i - 2):i]:
        hist += [{"src": b["original"], "dst": b["translated"]} for b in pg["blocks"] if b.get("original")]
    T.translate_page(_page(d, i)["blocks"], d["lang"], hist, d["glossary"], d["settings"])
    d["pages"][i]["rev"] += 1
    P.save(name, d)
    return d["pages"][i]


# ---------------- chỉnh sửa
@app.put("/api/projects/{name}/pages/{i}/blocks")
def put_blocks(name: str, i: int, blocks: list = Body(...)):
    d = P.load(name)
    pg = _page(d, i)
    pg["blocks"] = blocks
    pg["rev"] += 1
    P.save(name, d)
    return {"rev": pg["rev"]}


@app.post("/api/projects/{name}/pages/{i}/reclean")
def reclean(name: str, i: int, body: dict = Body(...)):
    """Vẽ thêm vùng cần xoá (rects: [[x1,y1,x2,y2]]) rồi inpaint lại từ ảnh gốc."""
    d = P.load(name)
    pg = _page(d, i)
    img = _imread(P.path(name, "pages", pg["file"]))
    mp = P.path(name, "work", _stem(pg) + "_mask.png")
    mask = cv2.cvtColor(_imread(mp), cv2.COLOR_BGR2GRAY) if os.path.exists(mp) else np.zeros(img.shape[:2], np.uint8)
    for x1, y1, x2, y2 in body.get("rects", []):
        cv2.rectangle(mask, (int(x1), int(y1)), (int(x2), int(y2)), 255, -1)
    for stroke in body.get("strokes", []):  # cọ: {points:[[x,y],...], r}
        pts = np.array(stroke["points"], np.int32).reshape(-1, 1, 2)
        cv2.polylines(mask, [pts], False, 255, int(stroke.get("r", 12)) * 2)
    clean, mask, patched = Engine.get().auto_clean(img, mask, pg["blocks"]) if body.get("auto", True)         else (Engine.get().inpaint(img, mask), mask, 0)
    _imwrite(mp, mask)
    _imwrite(P.path(name, "work", _stem(pg) + "_clean.png"), clean)
    pg["patched"] = patched
    pg["rev"] += 1
    P.save(name, d)
    return {"rev": pg["rev"]}


# ---------------- ảnh
def _final(name, d, pg, skip=()) -> Image.Image:
    return lettering.render(_base(name, pg), pg["blocks"], _lett(d), skip=skip)


_arr_cache = {}


def _base_arr(name, pg):
    """Ảnh nền (đã xoá chữ) dạng numpy, cache theo mtime để tính bố cục xem trước thật nhanh."""
    cp = P.path(name, "work", _stem(pg) + "_clean.png")
    p = cp if os.path.exists(cp) else P.path(name, "pages", pg["file"])
    key = (p, os.path.getmtime(p), tuple(tuple(b["box"]) for b in pg["blocks"] if b.get("keep")))
    if key not in _arr_cache:
        _arr_cache.clear()
        _arr_cache[key] = _base_np(name, pg)
    return _arr_cache[key]


@app.post("/api/projects/{name}/pages/{i}/layout")
def live_layout(name: str, i: int, blocks: list = Body(...)):
    """Bố cục chữ cho các ô đang chỉnh (chưa lưu) -> editor vẽ chữ trực tiếp, khớp với ảnh xuất ra."""
    d = P.load(name)
    pg = _page(d, i)
    arr, fonts, out = _base_arr(name, pg), lettering.list_fonts(), []
    for b in blocks:
        if b.get("keep") or b.get("hidden"):
            continue
        L = lettering.layout_block(b, _lett(d), arr, fonts)
        if L:
            L.pop("_font")
            out.append(L)
    return out


@app.get("/api/fontfile/{fname}")
def fontfile(fname: str):
    p = lettering.list_fonts().get(fname)
    if not p:
        raise HTTPException(404, "Không có font")
    return FileResponse(p, headers={"Cache-Control": "max-age=86400"})


@app.get("/api/projects/{name}/pages/{i}/image")
def image(name: str, i: int, kind: str = "final", skip: str = ""):
    d = P.load(name)
    pg = _page(d, i)
    if kind == "orig":
        return FileResponse(P.path(name, "pages", pg["file"]))
    if kind == "clean":
        cp = P.path(name, "work", _stem(pg) + "_clean.png")
        if not any(b.get("keep") for b in pg["blocks"]):
            return FileResponse(cp if os.path.exists(cp) else P.path(name, "pages", pg["file"]))
        buf = io.BytesIO()
        _base(name, pg).save(buf, "PNG", compress_level=1)
        return Response(buf.getvalue(), media_type="image/png")
    buf = io.BytesIO()
    sk = {int(x) for x in skip.split(",") if x.strip().isdigit()}
    _final(name, d, pg, sk).save(buf, "PNG", compress_level=1)
    return Response(buf.getvalue(), media_type="image/png")


@app.get("/api/projects/{name}/pages/{i}/report")
def report(name: str, i: int):
    """Tình trạng trang: các vấn đề còn tồn đọng để UI hiển thị rõ."""
    d = P.load(name)
    pg = _page(d, i)
    over = []
    lettering.render(_base(name, pg), pg["blocks"], _lett(d), report=over)
    bl = pg["blocks"]
    return {"blocks": len(bl),
            "empty_ocr": [b["id"] for b in bl if not b.get("keep") and not (b.get("original") or "").strip()],
            "untranslated": [b["id"] for b in bl if not b.get("keep") and (b.get("original") or "").strip() and not (b.get("translated") or "").strip()],
            "kept": [b["id"] for b in bl if b.get("keep")],
            "overflow": [o["id"] for o in over if o["overflow"]],
            "patched": pg.get("patched", 0),
            "cleaned": os.path.exists(P.path(name, "work", _stem(pg) + "_clean.png")),
            "types": {t: sum(1 for b in bl if b.get("type") == t) for t in {b.get("type") for b in bl}}}


KEEP_PAD = 14  # >= độ nới mask khi xoá chữ, để trả lại trọn cả viền chữ gốc


def _keep_mask(blocks, H, W):
    """Vùng cần trả lại ảnh gốc: các ô 'giữ nguyên' (nới rộng), trừ phần thuộc các ô khác vẫn được xoá/dịch."""
    keep = [b for b in blocks if b.get("keep")]
    if not keep:
        return None
    m = np.zeros((H, W), np.uint8)
    for b in keep:
        x1, y1, x2, y2 = [int(v) for v in b["box"]]
        m[max(0, y1 - KEEP_PAD):y2 + KEEP_PAD, max(0, x1 - KEEP_PAD):x2 + KEEP_PAD] = 1
    for b in blocks:
        if not b.get("keep"):
            x1, y1, x2, y2 = [int(v) for v in b["box"]]
            m[max(0, y1 - 4):y2 + 4, max(0, x1 - 4):x2 + 4] = 0
    return m.astype(bool)


def _base_np(name, pg):
    """Ảnh nền đã xoá chữ (numpy RGB), với các ô 'giữ nguyên' được trả lại đúng ảnh gốc."""
    cp = P.path(name, "work", _stem(pg) + "_clean.png")
    op = P.path(name, "pages", pg["file"])
    arr = np.array(Image.open(cp if os.path.exists(cp) else op).convert("RGB"))
    km = _keep_mask(pg["blocks"], *arr.shape[:2])
    if km is not None and os.path.exists(cp):
        orig = np.array(Image.open(op).convert("RGB"))
        if orig.shape == arr.shape:
            arr[km] = orig[km]
    return arr


def _base(name, pg):
    return Image.fromarray(_base_np(name, pg))


@app.get("/api/projects-info")
def projects_info():
    out = []
    for n in P.list_projects():
        d = P.load(n)
        pgs = d["pages"]
        out.append({"name": n, "pages": len(pgs), "done": sum(1 for p in pgs if p["status"] == "done"),
                    "blocks": sum(len(p["blocks"]) for p in pgs),
                    "translated": sum(1 for p in pgs for b in p["blocks"] if b.get("translated")),
                    "lang": d["lang"], "mtime": os.path.getmtime(P.path(n, "project.json")),
                    "thumb": bool(pgs)})
    return sorted(out, key=lambda x: -x["mtime"])


@app.get("/api/projects/{name}/export/{fmt}")
def export_fmt(name: str, fmt: str):
    d = P.load(name)
    pages = d["pages"]
    safe = P.safe(name)
    buf = io.BytesIO()
    if fmt == "zip":
        return export(name)
    if fmt == "pdf":
        import img2pdf
        blobs = []
        for pg in pages:
            b = io.BytesIO()
            _final(name, d, pg).save(b, "JPEG", quality=93)
            blobs.append(b.getvalue())
        return Response(img2pdf.convert(blobs), media_type="application/pdf",
                        headers={"Content-Disposition": f'attachment; filename="{safe}.pdf"'})
    if fmt == "xlsx":
        from openpyxl import Workbook
        from openpyxl.styles import Font, Alignment, PatternFill
        wb = Workbook()
        ws = wb.active
        ws.title = "Lời thoại"
        ws.append(["Trang", "#", "Loại", "Bản gốc", "Bản dịch", "X1", "Y1", "X2", "Y2", "Trạng thái"])
        for n, pg in enumerate(pages, 1):
            for b in pg["blocks"]:
                ws.append([n, b["id"], b.get("type", ""), b.get("original", ""), "" if b.get("keep") else b.get("translated", ""),
                           *b["box"], "Giữ nguyên" if b.get("keep") else ("Ẩn" if b.get("hidden") else "")])
        for c in ws[1]:
            c.font = Font(bold=True, color="FFFFFF")
            c.fill = PatternFill("solid", fgColor="2F5BEA")
        for col, w in zip("ABCDEFGHI", (7, 5, 12, 46, 46, 7, 7, 7, 7)):
            ws.column_dimensions[col].width = w
        for row in ws.iter_rows(min_row=2):
            for c in row[3:5]:
                c.alignment = Alignment(wrap_text=True, vertical="top")
        ws.freeze_panes = "A2"
        ws.auto_filter.ref = ws.dimensions
        g = wb.create_sheet("Glossary")
        g.append(["Gốc", "Dịch", "Ghi chú"])
        for x in d["glossary"]:
            g.append([x.get("src", ""), x.get("dst", ""), x.get("note", "")])
        wb.save(buf)
        return Response(buf.getvalue(), media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        headers={"Content-Disposition": f'attachment; filename="{safe}.xlsx"'})
    if fmt == "psd":
        from psd_tools import PSDImage
        from psd_tools.api.layers import PixelLayer
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
            for n, pg in enumerate(pages, 1):
                orig = Image.open(P.path(name, "pages", pg["file"])).convert("RGBA")
                clean = _base(name, pg).convert("RGBA")
                text = lettering.render(clean.convert("RGB"), pg["blocks"], _lett(d), text_only=True)
                psd = PSDImage.new("RGB", orig.size)
                for lname, im in (("1_Original", orig), ("2_Clean", clean), ("3_Text", text)):
                    PixelLayer.frompil(im, psd, lname, 0, 0)
                pb = io.BytesIO()
                psd.save(pb)
                z.writestr(f"{n:03d}.psd", pb.getvalue())
        return Response(buf.getvalue(), media_type="application/zip",
                        headers={"Content-Disposition": f'attachment; filename="{safe}_psd.zip"'})
    raise HTTPException(404, "Định dạng không hỗ trợ")


@app.get("/api/notices")
def notices():
    from config import REPO_DIR
    from fastapi.responses import PlainTextResponse
    p = os.path.join(REPO_DIR, "THIRD_PARTY_NOTICES.md")
    return PlainTextResponse(open(p, encoding="utf8").read() if os.path.exists(p) else "")


@app.get("/api/system")
def system_info():
    import modelstore, torch
    from config import DATA_DIR, MODELS_DIR
    return {"version": APP_VERSION, "models_ready": modelstore.all_ready(), "models_dir": MODELS_DIR, "data_dir": DATA_DIR,
            "device": "cuda" if torch.cuda.is_available() else "cpu",
            "gpu": torch.cuda.get_device_name(0) if torch.cuda.is_available() else None}


@app.get("/api/fonts")
def fonts():
    return list(lettering.list_fonts().keys())


@app.get("/api/fonts/info")
def fonts_info():
    return lettering.font_info()


@app.post("/api/fonts")
async def add_fonts(files: list[UploadFile] = File(...)):
    """Thêm font (.ttf/.otf/.ttc) vào thư mục font người dùng. Kiểm tra file mở được thật và có hỗ trợ tiếng Việt."""
    from config import USER_FONTS_DIR
    from PIL import ImageFont
    added, errors = [], []
    for f in files:
        base = os.path.basename(f.filename or "")
        stem, ext = os.path.splitext(base)
        if ext.lower() not in lettering.FONT_EXT:
            errors.append(f"{base}: chỉ nhận .ttf, .otf, .ttc")
            continue
        blob = await f.read()
        if len(blob) > 40 * 1024 * 1024:
            errors.append(f"{base}: file quá lớn (>40MB)")
            continue
        stem = re.sub(r"[^\w\- ]", "_", stem, flags=re.U).strip() or "font"
        dst = os.path.join(USER_FONTS_DIR, stem + ext.lower())
        tmp = dst + ".tmp"
        with open(tmp, "wb") as fh:
            fh.write(blob)
        try:
            ImageFont.truetype(tmp, 24).getbbox("Thử chữ")
        except Exception as e:
            os.remove(tmp)
            errors.append(f"{base}: không đọc được font ({e})")
            continue
        os.replace(tmp, dst)
        miss = lettering.font_vi_missing(dst)
        added.append({"name": stem, "vi": not miss, "missing": miss[:12]})
    return {"added": added, "errors": errors}


@app.delete("/api/fonts/{fname}")
def del_font(fname: str):
    from config import USER_FONTS_DIR
    p = lettering.list_fonts().get(fname)
    if not p or os.path.dirname(os.path.abspath(p)) != os.path.abspath(USER_FONTS_DIR):
        raise HTTPException(400, "Chỉ xoá được font bạn tự thêm")
    os.remove(p)
    lettering._cache.clear()
    return {"ok": True}


@app.get("/api/projects/{name}/export")
def export(name: str):
    d = P.load(name)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for n, pg in enumerate(d["pages"], 1):
            b = io.BytesIO()
            _final(name, d, pg).save(b, "PNG")
            z.writestr(f"{n:03d}.png", b.getvalue())
    return Response(buf.getvalue(), media_type="application/zip",
                    headers={"Content-Disposition": f'attachment; filename="{P.safe(name)}.zip"'})


app.mount("/", StaticFiles(directory=WEB_DIR, html=True), name="web")

if __name__ == "__main__":
    import uvicorn, webbrowser
    port = int(os.environ.get("MF_PORT", "8765"))
    if not os.environ.get("MF_NO_BROWSER"):
        threading.Timer(1.5, lambda: webbrowser.open(f"http://127.0.0.1:{port}")).start()
    uvicorn.run(app, host="127.0.0.1", port=port)
