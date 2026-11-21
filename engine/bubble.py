"""Nhận diện loại bong bóng thoại bằng phân tích hình học (không cần model nặng).

Với mỗi ô chữ: flood-fill vùng nền sáng (hoặc tối) bao quanh chữ -> lấy đường viền bong bóng -> phân loại:
  speech    bong bóng bầu dục/tròn thường
  thought   bong bóng suy nghĩ (viền lượn sóng kiểu đám mây)
  shout     bong bóng hét (viền gai nhọn)
  narration hộp dẫn truyện hình chữ nhật
  free      chữ nằm thẳng trên tranh, không có bong bóng
  sfx       chữ hiệu ứng lớn trên tranh
Trả thêm `poly` (đa giác bong bóng) để chèn chữ khít hình thật thay vì elip giả định.
"""
import cv2
import numpy as np

LABELS_VI = {"speech": "Thoại", "thought": "Suy nghĩ", "shout": "Hét", "narration": "Dẫn truyện",
             "free": "Chữ trên tranh", "sfx": "SFX"}


def _ring_stats(gray, box):
    x1, y1, x2, y2 = box
    patch = gray[y1:y2, x1:x2]
    if patch.size == 0:
        return 255, 0
    t, _ = cv2.threshold(patch, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    bg_mask = patch > t if np.mean(patch > t) >= 0.5 else patch <= t  # đa số pixel là nền
    bg = patch[bg_mask]
    return (float(np.median(bg)) if bg.size else 255.0), float(np.std(bg)) if bg.size else 0.0


def analyze(img_bgr, box, text="", text_mask=None):
    H, W = img_bgr.shape[:2]
    x1, y1, x2, y2 = [int(v) for v in box]
    bw, bh = x2 - x1, y2 - y1
    out = {"kind": "free", "poly": None}
    if bw < 6 or bh < 6:
        return out
    mx, my = int(bw * 2.2) + 40, int(bh * 0.9) + 40
    cx1, cy1, cx2, cy2 = max(0, x1 - mx), max(0, y1 - my), min(W, x2 + mx), min(H, y2 + my)
    crop = img_bgr[cy1:cy2, cx1:cx2]
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    lb = (x1 - cx1, y1 - cy1, x2 - cx1, y2 - cy1)
    bg_val, bg_std = _ring_stats(gray, lb)

    # vùng nền đồng nhất quanh chữ: pixel có độ sáng gần bg_val
    tol = 28
    same = (np.abs(gray.astype(np.int16) - bg_val) <= tol).astype(np.uint8) * 255
    same = cv2.morphologyEx(same, cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8))
    # chữ tách vùng -> nối lại bằng closing mạnh + lấp lỗ bên trong ô chữ
    pw, ph = int(bw * 0.25), int(bh * 0.25)
    same[lb[1] + ph:lb[3] - ph, lb[0] + pw:lb[2] - pw] = 255
    n, lab = cv2.connectedComponents(same)
    seed = lab[(lb[1] + lb[3]) // 2, (lb[0] + lb[2]) // 2]
    if seed == 0:
        return _no_bubble(out, bw, bh, W, H, text, "r1")
    region = (lab == seed).astype(np.uint8) * 255
    # lấp lỗ (chữ, chi tiết nhỏ) rồi mở nhẹ để cắt các "cầu" rò ra tranh
    cnts, _ = cv2.findContours(region, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    if not cnts:
        return _no_bubble(out, bw, bh, W, H, text, "r2")
    region = np.zeros_like(region)
    cv2.drawContours(region, [max(cnts, key=cv2.contourArea)], -1, 255, -1)
    k = min(45, max(9, int(bw * 0.35))) | 1
    region = cv2.morphologyEx(region, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k)))
    n, lab2 = cv2.connectedComponents(region)
    s2 = lab2[(lb[1] + lb[3]) // 2, (lb[0] + lb[2]) // 2]
    if s2 == 0:
        return _no_bubble(out, bw, bh, W, H, text, "r3")
    region = (lab2 == s2).astype(np.uint8) * 255
    cnts, _ = cv2.findContours(region, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    cnt = max(cnts, key=cv2.contourArea)
    area = cv2.contourArea(cnt)
    box_area = bw * bh
    bx, by, bbw, bbh = cv2.boundingRect(cnt)
    touches = bx <= 1 or by <= 1 or bx + bbw >= region.shape[1] - 1 or by + bbh >= region.shape[0] - 1
    # chạm biên crop hoặc quá to so với chữ -> nền tranh, không phải bong bóng
    print("DBG", area, box_area, touches, bx, by, bbw, bbh, region.shape) if __import__("os").environ.get("BDBG") else None
    if touches and (cx1 > 0 and cy1 > 0 and cx2 < W and cy2 < H) or area > box_area * 14 or area < box_area * 1.05:
        return _no_bubble(out, bw, bh, W, H, text, "r4")

    # Bong bóng thật: nền sáng/tối rõ rệt + có viền tương phản bao quanh. Nền tranh trung tính/không viền -> loại.
    if 95 < bg_val < 165 and bg_std < 60:
        return _no_bubble(out, bw, bh, W, H, text, "r5")
    fillm = np.zeros_like(region)
    cv2.drawContours(fillm, [cnt], -1, 255, -1)
    band = cv2.dilate(fillm, np.ones((9, 9), np.uint8)) & ~cv2.dilate(fillm, np.ones((3, 3), np.uint8))
    bvals = gray[band > 0]
    if bvals.size and np.mean(np.abs(bvals.astype(np.int16) - bg_val) > 45) < 0.45:
        return _no_bubble(out, bw, bh, W, H, text, "r6")

    hull = cv2.convexHull(cnt)
    solidity = area / max(cv2.contourArea(hull), 1)
    rect = area / max(bbw * bbh, 1)
    peri = cv2.arcLength(cnt, True)
    circ = 4 * np.pi * area / max(peri * peri, 1)

    kind = "speech"
    if circ < 0.3:  # viền răng cưa bất thường = vùng nền bị rò -> không tin hình dạng, coi là thoại thường, không dùng polygon
        out.update(kind="speech", poly=None, leak=True)
        return out
    if rect > 0.9 and solidity > 0.95:
        kind = "narration"
    elif solidity < 0.9:
        hidx = cv2.convexHull(cnt, returnPoints=False)
        depth_thr = 0.035 * np.sqrt(area)
        defects = []
        try:
            d = cv2.convexityDefects(cnt, hidx)
            if d is not None:
                defects = [v / 256.0 for v in d.reshape(-1, 4)[:, 3] if v / 256.0 > depth_thr]
        except cv2.error:
            pass
        nd = len(defects)
        if nd >= 5:
            approx = cv2.approxPolyDP(cnt, 0.012 * peri, True)
            # gai nhọn: ít đỉnh trên mỗi khuyết; mây: nhiều đỉnh (cung tròn)
            kind = "shout" if len(approx) / nd < 2.6 else "thought"
            out["dbg"] = (round(solidity, 2), nd, len(approx), round(circ, 2))
        elif nd >= 5 and circ < 0.55:
            kind = "shout"
            out["dbg"] = (round(solidity, 2), nd, round(circ, 2))
    elif circ < 0.62 and rect < 0.8:
        kind = "speech"

    eps = 0.008 * peri
    poly = cv2.approxPolyDP(cnt, eps, True).reshape(-1, 2) + np.array([cx1, cy1])
    out["sol"] = (round(solidity, 2), round(rect, 2), round(circ, 2))
    out.update(kind=kind, poly=poly.astype(int).tolist(), dark=bool(bg_val < 90))
    return out


def _no_bubble(out, bw, bh, W, H, text, why=''):
    out['why'] = why
    big = bw * bh / float(W * H) > 0.03
    out["kind"] = "sfx" if (big and len(text) <= 8) else "free"
    return out
