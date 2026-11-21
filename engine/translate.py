"""Dịch theo ngữ cảnh: gửi cả trang (+ lịch sử trang trước) + glossary + văn phong cho LLM, nhận JSON về."""
import json, re, requests

LANG_NAME = {"ja": "tiếng Nhật", "ko": "tiếng Hàn", "zh": "tiếng Trung", "en": "tiếng Anh"}


_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"


def _get_json(url, params):
    """Gọi bằng urllib (không dùng requests): Google chặn 'dấu vân tay' của thư viện requests bằng lỗi 429."""
    import urllib.parse
    import urllib.request
    req = urllib.request.Request(url + "?" + urllib.parse.urlencode(params, doseq=True), headers={"User-Agent": _UA})
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read().decode("utf8"))


def _free_gtx(texts, sl):
    d = _get_json("https://translate.googleapis.com/translate_a/single",
                  {"client": "gtx", "sl": sl, "tl": "vi", "dt": "t", "q": "\n@@\n".join(t.replace("\n", " ") for t in texts)})
    parts = [p.strip() for p in "".join(x[0] for x in d[0] if x and x[0]).split("@@")]
    if len(parts) != len(texts):
        raise ValueError("số câu trả về không khớp")
    return parts


def _free_dict(texts, sl):
    d = _get_json("https://clients5.google.com/translate_a/t",
                  [("client", "dict-chrome-ex"), ("sl", sl), ("tl", "vi")] + [("q", t) for t in texts])
    out = [x if isinstance(x, str) else (x[0] if x else "") for x in d]
    if len(out) != len(texts):
        raise ValueError("số câu trả về không khớp")
    return [o.strip() for o in out]


def _free_translate(texts, sl, tries=3):
    """Dịch miễn phí qua Google, có 2 đường dự phòng. Trả (danh sách bản dịch | None, thông báo lỗi)."""
    import time
    errs = []
    for k in range(tries):
        for name, fn in (("Google", _free_gtx), ("Google (dự phòng)", _free_dict)):
            try:
                return fn(texts, sl), None
            except Exception as e:
                errs.append(f"{name}: {e}")
                print("dịch miễn phí lỗi:", name, e)
        time.sleep(1.5 * (k + 1))
    return None, errs[-1] if errs else "không rõ lỗi"


def _prompt(lang, items, history, glossary, style, notes):
    gl = "\n".join(f"- {g['src']} => {g['dst']}" + (f" ({g['note']})" if g.get("note") else "")
                   for g in glossary) or "(trống)"
    hist = "\n".join(f"[{h['src']}] -> [{h['dst']}]" for h in history[-12:]) or "(đây là trang đầu)"
    return f"""Bạn là dịch giả truyện tranh chuyên nghiệp, dịch {LANG_NAME.get(lang, lang)} sang tiếng Việt.
Văn phong: {style or 'tự nhiên, đúng giọng nhân vật'}.
Ghi chú truyện: {notes or '(không)'}
QUY TẮC: giữ nhất quán tên riêng và cách xưng hô theo GLOSSARY; câu ngắn gọn vừa bóng thoại; ô loại sfx dịch thành từ tượng thanh tiếng Việt ngắn; không giải thích.
GLOSSARY:
{gl}
NGỮ CẢNH CÁC TRANG TRƯỚC (gốc -> dịch):
{hist}
CÁC Ô THOẠI TRANG HIỆN TẠI (đúng thứ tự đọc):
{json.dumps(items, ensure_ascii=False)}
Trả về DUY NHẤT một mảng JSON: [{{"id":<id>,"vi":"<bản dịch>"}}, ...] đủ mọi id."""


def _parse(txt):
    m = re.search(r"\[.*\]", txt, re.S)
    return {int(o["id"]): str(o["vi"]).strip() for o in json.loads(m.group(0))}


def _call_llm(provider, key, model, prompt):
    if provider == "anthropic":
        r = requests.post("https://api.anthropic.com/v1/messages",
                          headers={"x-api-key": key, "anthropic-version": "2023-06-01",
                                   "content-type": "application/json"},
                          json={"model": model or "claude-sonnet-5-5", "max_tokens": 4096, "temperature": 0.3,
                                "messages": [{"role": "user", "content": prompt}]}, timeout=120)
        r.raise_for_status()
        return r.json()["content"][0]["text"]
    if provider == "gemini":
        m = model or "gemini-2.0-flash"
        r = requests.post(f"https://generativelanguage.googleapis.com/v1beta/models/{m}:generateContent",
                          headers={"x-goog-api-key": key},  # key ở header, không nằm trong URL (tránh lộ key qua log/lỗi)
                          json={"contents": [{"parts": [{"text": prompt}]}],
                                "generationConfig": {"temperature": 0.3}}, timeout=120)
        r.raise_for_status()
        return r.json()["candidates"][0]["content"]["parts"][0]["text"]
    if provider == "openai":  # tương thích LM Studio / Ollama / OpenAI: model = "base_url|ten_model"
        base, _, mdl = (model or "").partition("|")
        r = requests.post((base or "https://api.openai.com/v1") + "/chat/completions",
                          headers={"Authorization": f"Bearer {key}"},
                          json={"model": mdl or "gpt-4o-mini", "temperature": 0.3,
                                "messages": [{"role": "user", "content": prompt}]}, timeout=180)
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"]
    raise ValueError(provider)


def _friendly(e):
    """Diễn giải lỗi của dịch vụ dịch thành câu dễ hiểu cho người dùng."""
    t = re.sub(r"\s*for url: \S+", "", str(e))  # không bao giờ in URL (có thể chứa key)
    t = re.sub(r"(key|token)=[^&\s]+", r"\1=***", t, flags=re.I)
    code = getattr(getattr(e, "response", None), "status_code", None)
    if code == 400 or t.startswith("400"):
        return "yêu cầu bị từ chối (400) — thường do API key sai hoặc sai tên model"
    if code in (401, 403) or "401" in t or "403" in t:
        return "API key không hợp lệ hoặc chưa được cấp quyền"
    if code == 429 or "429" in t:
        return "dịch vụ báo vượt giới hạn (429) — chờ một lát rồi thử lại"
    if code == 404 or "404" in t:
        return "sai tên model"
    if "timed out" in t.lower() or "timeout" in t.lower():
        return "hết thời gian chờ (mạng chậm?)"
    return t[:160]


def translate_page(blocks, lang, history, glossary, settings, report=None):
    """Điền block['translated'] tại chỗ (bỏ qua ô đã khoá/giữ nguyên). Trả về list {src,dst} làm ngữ cảnh trang sau.
    report (list): nhận các cảnh báo để giao diện hiển thị rõ khi không dịch được."""
    todo = [b for b in blocks if b.get("original") and not b.get("keep")]
    if not todo:
        return []
    warn = report if report is not None else []
    provider, key = settings.get("provider", "gtx"), settings.get("api_key", "")
    result = {}
    if provider != "gtx":
        if not key and provider != "openai":
            warn.append(f"Chưa nhập API key cho {provider} — tạm dùng Google Translate miễn phí")
        else:
            items = [{"id": b["id"], "type": b.get("type", "speech"), "text": b["original"]} for b in todo]
            try:
                result = _parse(_call_llm(provider, key, settings.get("model"),
                                          _prompt(lang, items, history, glossary,
                                                  settings.get("style"), settings.get("notes"))))
            except Exception as e:
                print("LLM lỗi, dùng Google Translate:", _friendly(e))
                warn.append(f"{provider} lỗi: {_friendly(e)} — tạm dùng Google Translate miễn phí")
    if not result:
        gt, err = _free_translate([b["original"] for b in todo], lang)
        if gt:
            result = {b["id"]: t for b, t in zip(todo, gt)}
        else:
            warn.append(f"Không dịch được: Google Translate miễn phí từ chối ({_friendly(err)}). "
                        "Thử lại sau ít phút, hoặc dùng Gemini (có gói miễn phí) / Claude trong tab Dịch.")
    pairs = []
    for b in todo:
        if not b.get("locked") and result.get(b["id"]):
            b["translated"] = result[b["id"]]
        pairs.append({"src": b["original"], "dst": b.get("translated", "")})
    return pairs
