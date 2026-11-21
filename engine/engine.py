"""AI engine: phát hiện chữ -> OCR -> xoá chữ (LaMa). Model nạp lười (lazy)."""
import os, threading
import cv2, numpy as np, torch
from PIL import Image
from config import MODELS_DIR
import bubble


def _reading_order(blocks, W, H, rtl=True):
    """Sắp xếp thứ tự đọc: gom theo hàng (trên->dưới), trong hàng phải->trái (manga) hoặc trái->phải."""
    if not blocks:
        return blocks
    items = sorted(blocks, key=lambda b: (b["box"][1] + b["box"][3]) / 2)
    rows, cur = [], [items[0]]
    for b in items[1:]:
        cy = (b["box"][1] + b["box"][3]) / 2
        ref = np.mean([(c["box"][1] + c["box"][3]) / 2 for c in cur])
        h = np.mean([c["box"][3] - c["box"][1] for c in cur])
        if abs(cy - ref) < max(h * 0.6, H * 0.04):
            cur.append(b)
        else:
            rows.append(cur); cur = [b]
    rows.append(cur)
    out = []
    for r in rows:
        r.sort(key=lambda b: -(b["box"][0] + b["box"][2]) if rtl else (b["box"][0] + b["box"][2]))
        out += r
    return out


def _classify(box, W, H, text):
    """Phân loại sơ bộ: sfx / narration / speech. Người dùng sửa được trong editor."""
    x1, y1, x2, y2 = box
    w, h = x2 - x1, y2 - y1
    area = w * h / float(W * H)
    if area > 0.035 and len(text) <= 6:
        return "sfx"
    if (w / max(h, 1)) > 2.6 and len(text) > 8:
        return "narration"
    return "speech"


class Engine:
    _inst = None

    def __init__(self):
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        self.detector = self.ocr_ja = self.ocr_easy = self.lama = None
        self.lock = threading.Lock()

    @classmethod
    def get(cls):
        if cls._inst is None:
            cls._inst = Engine()
        return cls._inst

    # ---- loaders
    def _detector(self):
        if self.detector is None:
            from inference import TextDetector
            p = os.path.join(MODELS_DIR, "text_segmentation", "comictextdetector.pt.onnx")
            self.detector = TextDetector(p, input_size=1024, device=self.device)
        return self.detector

    def _ocr(self, lang):
        if lang == "ja":
            if self.ocr_ja is None:
                from manga_ocr import MangaOcr
                self.ocr_ja = MangaOcr(pretrained_model_name_or_path=os.path.join(MODELS_DIR, "manga_ocr"))
            return self.ocr_ja
        if self.ocr_easy is None or self.ocr_easy[0] != lang:
            import easyocr
            code = {"zh": ["ch_sim", "en"], "ko": ["ko", "en"]}.get(lang, ["en"])
            self.ocr_easy = (lang, easyocr.Reader(code, gpu=self.device == "cuda",
                                                    model_storage_directory=os.path.join(MODELS_DIR, "easyocr"),
                                                    download_enabled=True))  # EasyOCR tự tải model của nó (Apache-2.0) khi cần
        return self.ocr_easy[1]

    def _lama(self):
        if self.lama is None:
            p = os.path.join(MODELS_DIR, "inpaint", "anime-manga-big-lama.pt")
            self.lama = torch.jit.load(p, map_location=self.device).eval()
        return self.lama

    # ---- stages
    def analyze(self, img_bgr, lang="ja"):
        """Trả về (blocks, mask_gray). blocks: [{id, box, type, original, translated, style}]"""
        H, W = img_bgr.shape[:2]
        with self.lock:
            _, mask, blk_list = self._detector()(img_bgr)
            ocr = self._ocr(lang)
            rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)
            blocks = []
            for blk in blk_list:
                x1, y1, x2, y2 = [int(v) for v in blk.xyxy]
                x1, y1, x2, y2 = max(0, x1), max(0, y1), min(W, x2), min(H, y2)
                if x2 - x1 < 4 or y2 - y1 < 4:
                    continue
                crop = rgb[y1:y2, x1:x2]
                try:
                    if lang == "ja":
                        text = ocr(Image.fromarray(crop))
                    else:
                        text = " ".join(r[1] for r in ocr.readtext(crop))
                except Exception:
                    text = ""
                text = text.strip()
                info = bubble.analyze(img_bgr, [x1, y1, x2, y2], text)
                blocks.append({"box": [x1, y1, x2, y2], "type": info["kind"], "bubble": info["poly"],
                               "original": text, "translated": "", "style": {}})
        blocks = _reading_order(blocks, W, H, rtl=(lang in ("ja", "zh")))
        for i, b in enumerate(blocks):
            b["id"] = i + 1
        return blocks, mask

    def inpaint(self, img_bgr, mask_gray, dilate=6, pad=-1, close=5):
        """dilate: nới mask để phủ cả viền chữ; close: lấp lỗ trong nét chữ; pad=-1: tự lấy bối cảnh rộng quanh vùng xoá
        (LaMa cần thấy đủ hoạ tiết xung quanh mới dựng lại được screentone)."""
        H, W = img_bgr.shape[:2]
        m = (mask_gray > 10).astype(np.uint8) * 255
        if close:
            m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (close, close)))
        if dilate:
            m = cv2.dilate(m, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (dilate * 2 + 1,) * 2))
        if not m.any():
            return img_bgr.copy()
        # Chỉ inpaint vùng quanh mask để nhanh & giữ nguyên độ phân giải gốc
        out = img_bgr.copy()
        n, lab, stats, _ = cv2.connectedComponentsWithStats(cv2.dilate(m, np.ones((41, 41), np.uint8)))
        with self.lock:
            lama = self._lama()
            for i in range(1, n):
                x, y, w, h = stats[i, :4]
                p = pad if pad >= 0 else int(min(160, max(32, 0.35 * max(w, h))))  # pad<0: tự tính theo cỡ vùng
                x0, y0, x1, y1 = max(0, x - p), max(0, y - p), min(W, x + w + p), min(H, y + h + p)
                crop, cm = img_bgr[y0:y1, x0:x1], m[y0:y1, x0:x1]
                if not cm.any():
                    continue
                ch, cw = crop.shape[:2]
                ph, pw = (ch + 7) // 8 * 8, (cw + 7) // 8 * 8
                rgb = cv2.cvtColor(crop, cv2.COLOR_BGR2RGB)
                rgb = cv2.copyMakeBorder(rgb, 0, ph - ch, 0, pw - cw, cv2.BORDER_REFLECT)
                cmp_ = cv2.copyMakeBorder(cm, 0, ph - ch, 0, pw - cw, cv2.BORDER_CONSTANT, value=0)
                ti = torch.from_numpy(rgb).permute(2, 0, 1)[None].float().to(self.device) / 255
                tm = (torch.from_numpy(cmp_)[None, None].float().to(self.device) > 10).float()
                with torch.no_grad():
                    r = lama(ti, tm)[0].permute(1, 2, 0).cpu().numpy().clip(0, 1)
                r = cv2.cvtColor((r * 255).astype(np.uint8)[:ch, :cw], cv2.COLOR_RGB2BGR)
                keep = cm[..., None] > 0
                out[y0:y1, x0:x1] = np.where(keep, r, out[y0:y1, x0:x1])
        return out

    def auto_clean(self, img_bgr, mask_gray, blocks, max_pass=2):
        """Xoá chữ rồi TỰ KIỂM TRA: chạy lại detector trên ảnh đã xoá, vùng nào còn sót chữ thì thêm vào mask và xoá lại.
        Chỉ nhận vùng sót nằm gần các ô chữ gốc để tránh nhầm với hoạ tiết tranh.
        Trả về (ảnh sạch, mask mới, số vùng đã vá thêm)."""
        H, W = img_bgr.shape[:2]
        mask = (mask_gray > 10).astype(np.uint8) * 255
        near = np.zeros((H, W), np.uint8)
        for b in blocks:
            x1, y1, x2, y2 = b["box"]
            mx, my = int((x2 - x1) * 0.35) + 10, int((y2 - y1) * 0.35) + 10
            near[max(0, y1 - my):y2 + my, max(0, x1 - mx):x2 + mx] = 255
        base, flat = self._flat_fill(img_bgr, mask, blocks)
        clean = self.inpaint(base, cv2.bitwise_and(mask, cv2.bitwise_not(flat)))
        clean[flat > 0] = base[flat > 0]
        patched = 0
        for _ in range(max_pass):
            with self.lock:
                raw, ref, _ = self._detector()(clean)
            m2 = np.maximum((raw > 110).astype(np.uint8), (ref > 10).astype(np.uint8)) * 255
            m2 = cv2.bitwise_and(m2, near)
            m2 = cv2.morphologyEx(m2, cv2.MORPH_OPEN, np.ones((2, 2), np.uint8))
            n, lab, stats, _ = cv2.connectedComponentsWithStats(m2)
            add = np.zeros_like(m2)
            for i in range(1, n):
                if stats[i, cv2.CC_STAT_AREA] >= 12:  # bỏ nhiễu li ti
                    add[lab == i] = 255
                    patched += 1
            if not add.any():
                break
            mask = cv2.bitwise_or(mask, cv2.dilate(add, np.ones((5, 5), np.uint8)))
            base, flat = self._flat_fill(img_bgr, mask, blocks)
            clean = self.inpaint(base, cv2.bitwise_and(mask, cv2.bitwise_not(flat)))
            clean[flat > 0] = base[flat > 0]
        return clean, mask, patched

    def _flat_fill(self, img_bgr, mask, blocks):
        """Trong bong bóng nền phẳng (trắng/đen): tô thẳng màu nền lên chữ -> giữ nguyên viền bong bóng, sạch tuyệt đối.
        Phần mask còn lại (chữ nằm trên tranh / chạm viền) vẫn do LaMa xử lý vì mask không bị đổi."""
        out = img_bgr.copy()
        H, W = mask.shape
        flat = np.zeros((H, W), np.uint8)
        gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
        for b in blocks:
            poly = b.get("bubble")
            if not poly or b.get("type") not in ("speech", "thought", "shout", "narration"):
                continue
            pm = np.zeros((H, W), np.uint8)
            cv2.fillPoly(pm, [np.array(poly, np.int32)], 255)
            inner = cv2.erode(pm, np.ones((9, 9), np.uint8))
            md = cv2.dilate(mask, np.ones((5, 5), np.uint8))
            bgpix = (inner > 0) & (md == 0)
            if bgpix.sum() < 50:
                continue
            vals = gray[bgpix]
            if np.std(vals) > 14:  # nền không phẳng (toàn tone/hoạ tiết) -> để LaMa lo
                continue
            col = np.median(img_bgr[bgpix], axis=0)
            region = (inner > 0) & (mask > 10)
            out[region] = col.astype(np.uint8)
            flat[region] = 255
        return out, flat
