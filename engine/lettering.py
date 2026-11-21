"""Chèn chữ thông minh: wrap cân bằng, vừa hình elip bóng thoại, tự chọn màu theo nền, preset theo loại ô."""
import os, math
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from config import FONTS_DIR, USER_FONTS_DIR

DEFAULT_FONT = "BeVietnamPro-Bold"
PRESETS = {  # kiểu mặc định theo loại ô; style riêng của từng ô ghi đè lên
    "speech":    {"stroke_width": 0, "line_spacing": 0.12, "ellipse": True,  "fill": 0.90},
    "thought":   {"stroke_width": 0, "line_spacing": 0.12, "ellipse": True,  "fill": 0.82},
    "shout":     {"stroke_width": 0, "line_spacing": 0.08, "ellipse": True,  "fill": 0.80, "upper": True},
    "narration": {"stroke_width": 0, "line_spacing": 0.15, "ellipse": False, "fill": 0.94},
    "free":      {"stroke_width": 3, "line_spacing": 0.10, "ellipse": False, "fill": 1.0},
    "sfx":       {"stroke_width": 4, "line_spacing": 0.05, "ellipse": False, "fill": 1.0, "min_size": 22, "upper": True},
}


def _chord_fn(poly, bbox):
    """Từ đa giác bong bóng -> hàm trả bề rộng chữ tối đa (đối xứng quanh tâm) cho dải dọc [y0,y1] (toạ độ tương đối bbox)."""
    import cv2
    x1, y1, x2, y2 = bbox
    W, H = x2 - x1, y2 - y1
    m = np.zeros((H, W), np.uint8)
    cv2.fillPoly(m, [(np.array(poly) - [x1, y1]).astype(np.int32)], 1)
    cx = W // 2
    half = np.zeros(H)
    for r in range(H):
        row = m[r]
        if not row[cx]:
            continue
        l = cx
        while l > 0 and row[l - 1]:
            l -= 1
        rr = cx
        while rr < W - 1 and row[rr + 1]:
            rr += 1
        half[r] = min(cx - l, rr - cx)

    def chord(ya, yb):
        a, b = max(0, int(ya)), min(H, int(yb) + 1)
        if b <= a:
            return 0.0
        return float(half[a:b].min()) * 2
    return chord
_cache = {}


FONT_EXT = (".ttf", ".otf", ".ttc")


def list_fonts():
    """Tên font -> đường dẫn. Gồm font có sẵn + font người dùng thêm (font người dùng được ưu tiên nếu trùng tên)."""
    out = {}
    for d in (FONTS_DIR, USER_FONTS_DIR):
        if os.path.isdir(d):
            for f in sorted(os.listdir(d)):
                if f.lower().endswith(FONT_EXT):
                    out[os.path.splitext(f)[0]] = os.path.join(d, f)
    return dict(sorted(out.items(), key=lambda kv: kv[0].lower()))


VI_CHARS = "ăâđêôơưạảấầẩẫậắằẳẵặẹẻẽếềểễệỉịọỏốồổỗộớờởỡợụủứừửữựỳỵỷỹĂÂĐÊÔƠƯẠẢẤẦẨẪẬẮẰẲẴẶẸẺẼẾỀỂỄỆỊỌỎỐỒỔỖỘỚỜỞỠỢỤỦỨỪỬỮỰỲỴỶỸ"
_vi_cache = {}


def font_vi_missing(path):
    """Các ký tự tiếng Việt font KHÔNG có (so với glyph 'không có' .notdef). Rỗng = hỗ trợ đầy đủ."""
    key = (path, os.path.getmtime(path))
    if key in _vi_cache:
        return _vi_cache[key]
    try:
        f = ImageFont.truetype(path, 32)
        nd = f.getmask("\uE000")  # vùng riêng -> gần như chắc chắn dùng glyph .notdef
        nd_sig = (nd.size, bytes(nd))
        miss = []
        for ch in VI_CHARS:
            m = f.getmask(ch)
            if m.size == (0, 0) or (m.size, bytes(m)) == nd_sig:
                miss.append(ch)
    except Exception:
        miss = list(VI_CHARS)
    _vi_cache[key] = "".join(miss)
    return _vi_cache[key]


def font_info():
    out = []
    for name, path in list_fonts().items():
        miss = font_vi_missing(path)
        out.append({"name": name, "user": os.path.dirname(os.path.abspath(path)) == os.path.abspath(USER_FONTS_DIR),
                    "vi": not miss, "missing": miss[:12], "file": os.path.basename(path)})
    return out


def _font(path, size):
    k = (path, size)
    if k not in _cache:
        _cache[k] = ImageFont.truetype(path, size)
    return _cache[k]


class _Meas:
    """Đo bề rộng chữ có cache: mỗi từ chỉ đo 1 lần cho mỗi cỡ chữ (trước đây đo lại cả dòng hàng chục nghìn lần)."""
    def __init__(self, font):
        self.font = font
        self.cache = {}
        self.space = font.getlength(" ")

    def w(self, word):
        v = self.cache.get(word)
        if v is None:
            v = self.cache[word] = self.font.getlength(word)
        return v

    def line(self, words):
        return sum(self.w(x) for x in words) + self.space * (len(words) - 1)


def _greedy(words, m, max_w):
    lines, cur, cw = [], [], 0.0
    for w in words:
        ww = m.w(w)
        nw = ww if not cur else cw + m.space + ww
        if nw <= max_w or not cur:
            cur.append(w)
            cw = nw
        else:
            lines.append(cur)
            cur, cw = [w], ww
    if cur:
        lines.append(cur)
    return lines


def _balanced(words, m, max_w):
    """Greedy rồi thu hẹp bề rộng tới khi số dòng còn giữ nguyên -> các dòng đều nhau, đẹp hơn."""
    base = _greedy(words, m, max_w)
    n = len(base)
    if n <= 1:
        return base
    lo, hi = max(m.w(w) for w in words), max_w
    best = base
    for _ in range(8):
        mid = (lo + hi) / 2
        cand = _greedy(words, m, mid)
        if len(cand) <= n:
            best, hi = cand, mid
        else:
            lo = mid
    return best


def _try(words, path, size, W, H, preset, chord, strict):
    """Dàn chữ ở một cỡ; trả (fits, layout)."""
    font = _font(path, size)
    m = _Meas(font)
    asc, desc = font.getmetrics()
    lh = asc + desc
    gap = int(size * preset["line_spacing"])
    step = lh + gap
    fill = preset["fill"]
    lines = _balanced(words, m, W * fill)
    total_h = step * len(lines) - gap
    lay = (font, [" ".join(l) for l in lines], size, step, lh)
    if not strict:
        return True, lay
    if total_h > H * fill or max(m.line(l) for l in lines) > W * fill:
        return False, lay
    if preset["ellipse"]:
        top = -total_h / 2
        for i, l in enumerate(lines):
            y0 = top + i * step
            if chord:
                avail = chord(H / 2 + y0, H / 2 + y0 + lh) * fill
            else:
                dy = max(abs(y0), abs(y0 + lh))
                avail = W * math.sqrt(max(0.0, 1 - (dy / (H / 2)) ** 2)) * fill
            if m.line(l) > avail:
                return False, lay
    return True, lay


def _layout(text, path, W, H, preset, size_override, min_size, max_size, chord=None):
    words = text.split()
    if not words:
        return None
    if size_override:
        return _try(words, path, size_override, W, H, preset, chord, False)[1]
    # tìm nhị phân cỡ chữ lớn nhất còn vừa (thay vì thử lần lượt từ 96 xuống)
    lo, hi, best = min_size, max(min_size, max_size), None
    while lo <= hi:
        mid = (lo + hi) // 2
        ok, lay = _try(words, path, mid, W, H, preset, chord, True)
        if ok:
            best, lo = lay, mid + 1
        else:
            hi = mid - 1
    return best or _try(words, path, min_size, W, H, preset, chord, False)[1]


def _wlen(font, s):
    return font.getlength(s)


def _auto_colors(img_np, box):
    x1, y1, x2, y2 = box
    patch = img_np[max(0, y1):y2, max(0, x1):x2]
    if patch.size == 0:
        return "#000000", "#FFFFFF", False
    g = patch[..., :3] @ np.array([0.299, 0.587, 0.114])
    lum = float(np.median(g))
    mixed = float(np.mean(g > 170)) > 0.15 and float(np.mean(g < 85)) > 0.15  # nền vừa trắng vừa đen
    busy = mixed or float(np.std(g)) > 38  # nền tranh / screentone, không phải nền phẳng của bong bóng
    if busy:
        # chữ đè lên tranh: kiểu manga quen thuộc = chữ trắng viền đen (trừ khi nền rất sáng)
        return ("#000000", "#FFFFFF", True) if lum > 200 else ("#FFFFFF", "#000000", True)
    return (("#000000", "#FFFFFF") if lum >= 120 else ("#FFFFFF", "#000000")) + (False,)


def layout_block(b, defaults, arr, fonts):
    """Tính bố cục chữ của 1 ô (dùng chung cho render ảnh và xem trước trực tiếp trên editor)."""
    text = (b.get("translated") or "").strip()
    if not text:
        return None
    st = {**(defaults or {}), **(b.get("style") or {})}
    preset = dict(PRESETS.get(b.get("type", "speech"), PRESETS["speech"]))
    if "stroke_width" in st:
        preset["stroke_width"] = st["stroke_width"]
    if "line_spacing" in st:
        preset["line_spacing"] = st["line_spacing"]
    fname = st.get("font") or DEFAULT_FONT
    path = fonts.get(fname) or fonts.get(DEFAULT_FONT) or (list(fonts.values()) or [None])[0]
    if not path:
        return None
    if path != fonts.get(fname):
        fname = next(k for k, v in fonts.items() if v == path)
    x1, y1, x2, y2 = [int(v) for v in b["box"]]
    chord = None
    poly = b.get("bubble")
    # Ô người dùng đã kéo/chỉnh tay (manual) -> khung ô là chuẩn, bỏ qua hình bong bóng tự nhận diện
    if (poly and len(poly) >= 3 and not b.get("manual") and st.get("use_bubble", True)
            and b.get("type") in ("speech", "thought", "shout", "narration")):
        p = np.array(poly)
        px1, py1, px2, py2 = int(p[:, 0].min()), int(p[:, 1].min()), int(p[:, 0].max()), int(p[:, 1].max())
        ix = max(0, min(x2, px2) - max(x1, px1)) * max(0, min(y2, py2) - max(y1, py1))
        box_area = max(1, (x2 - x1) * (y2 - y1))
        # bong bóng hợp lệ: chứa >=70% ô chữ, không to quá 5 lần ô chữ, và tâm gần tâm ô chữ
        # (polygon "rò" sang vùng trắng bên cạnh sẽ bị lệch tâm -> bỏ, dùng khung ô)
        off_x = abs((x1 + x2) / 2 - (px1 + px2) / 2) / max(1, px2 - px1)
        off_y = abs((y1 + y2) / 2 - (py1 + py2) / 2) / max(1, py2 - py1)
        if ix >= 0.7 * box_area and (px2 - px1) * (py2 - py1) <= 5 * box_area and off_x < 0.2 and off_y < 0.2:
            x1, y1, x2, y2 = px1, py1, px2, py2
            chord = _chord_fn(poly, (x1, y1, x2, y2))
    W, H = max(8, x2 - x1), max(8, y2 - y1)
    if st.get("upper", preset.get("upper", False)):
        text = text.upper()
    lay = _layout(text, path, W, H, preset, int(st.get("size") or 0),
                  preset.get("min_size", 10), int(max(14, min(96, H))), chord)
    if not lay:
        return None
    font, lines, size, step, lh = lay
    total = step * len(lines) - (step - lh)
    overflow = total > H * 1.02 or max(_wlen(font, l) for l in lines) > W * 1.02
    col, strk = st.get("color"), st.get("stroke_color")
    sw = int(preset["stroke_width"])
    if not col or not strk:
        ac, asc_, mixed = _auto_colors(arr, tuple(int(v) for v in b["box"]) if chord else (x1, y1, x2, y2))
        col, strk = col or ac, strk or asc_
        if mixed and not st.get("color") and "stroke_width" not in st:
            sw = max(sw, max(2, size // 8))  # nền tranh/lẫn lộn -> luôn có viền để đọc được
    align = st.get("align", "center")
    cx, cy = x1 + W / 2, y1 + H / 2
    tx = {"left": x1 + W * 0.05, "right": x2 - W * 0.05}.get(align, cx)
    return {"id": b.get("id"), "font": fname, "size": size, "lines": lines, "step": step, "lh": lh,
            "x": tx, "y": cy - total / 2, "align": align, "color": col, "stroke": strk,
            "sw": sw, "region": [x1, y1, x2, y2], "overflow": overflow,
            "_font": font}


def render(base: Image.Image, blocks, defaults=None, report=None, text_only=False, skip=()):
    """text_only=True: ảnh RGBA trong suốt chỉ có chữ (layer PSD). skip: id các ô không vẽ (đang chỉnh trực tiếp).
    report: list nhận bố cục từng ô (có cờ overflow)."""
    arr = np.array(base.convert("RGB"))
    img = Image.new("RGBA", base.size, (0, 0, 0, 0)) if text_only else base.convert("RGB").copy()
    draw = ImageDraw.Draw(img)
    fonts = list_fonts()
    for b in blocks:
        if b.get("hidden") or b.get("keep"):
            continue
        L = layout_block(b, defaults, arr, fonts)
        if not L:
            continue
        if report is not None:
            report.append({k: v for k, v in L.items() if k != "_font"})
        if b.get("id") in skip:
            continue
        anchor = {"left": "lt", "right": "rt"}.get(L["align"], "mt")
        y = L["y"]
        for ln in L["lines"]:
            draw.text((L["x"], y), ln, font=L["_font"], fill=L["color"], stroke_width=L["sw"],
                      stroke_fill=L["stroke"], anchor=anchor)
            y += L["step"]
    return img
