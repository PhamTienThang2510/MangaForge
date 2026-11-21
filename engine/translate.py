"""Dịch theo ngữ cảnh: gửi cả trang (+ lịch sử trang trước) + glossary + văn phong cho LLM, nhận JSON về."""
import json, re, requests

LANG_NAME = {"ja": "tiếng Nhật", "ko": "tiếng Hàn", "zh": "tiếng Trung", "en": "tiếng Anh"}


def _gtx_once(text, sl):
    r = requests.get("https://translate.googleapis.com/translate_a/single",
                     params={"client": "gtx", "sl": sl, "tl": "vi", "dt": "t", "q": text},
                     headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36"},
                     timeout=12)
    r.raise_for_status()
    return "".join(s[0] for s in r.json()[0] if s and s[0])


def _gtx_batch(texts, sl, tries=4):
    """Dịch cả trang trong 1 request (ngăn cách bằng dòng trống); thử lại khi bị 429. Thất bại -> trả None, KHÔNG chép lại bản gốc."""
    import time
    joined = "\n@@\n".join(t.replace("\n", " ") for t in texts)
    for k in range(tries):
        try:
            parts = [p.strip() for p in _gtx_once(joined, sl).split("@@")]
            if len(parts) == len(texts):
                return parts
            return [_gtx_once(t, sl).strip() for t in texts]
        except Exception as e:
            print("gtx lỗi:", e)
            time.sleep(2 * (k + 1))
    return None


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
                          params={"key": key},
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


def translate_page(blocks, lang, history, glossary, settings):
    """Điền block['translated'] tại chỗ (bỏ qua ô đã khoá). Trả về list {src,dst} làm ngữ cảnh trang sau."""
    todo = [b for b in blocks if b.get("original") and not b.get("keep")]
    if not todo:
        return []
    provider, key = settings.get("provider", "gtx"), settings.get("api_key", "")
    result = {}
    if provider != "gtx" and (key or provider == "openai"):
        items = [{"id": b["id"], "type": b.get("type", "speech"), "text": b["original"]} for b in todo]
        try:
            result = _parse(_call_llm(provider, key, settings.get("model"),
                                      _prompt(lang, items, history, glossary,
                                              settings.get("style"), settings.get("notes"))))
        except Exception as e:
            print("LLM lỗi, dùng Google Translate:", e)
    if not result:
        gt = _gtx_batch([b["original"] for b in todo], lang) if True else None
        if gt:
            result = {b["id"]: t for b, t in zip(todo, gt)}
        else:
            print("Không dịch được trang này (dịch vụ từ chối). Để trống để người dùng thấy rõ.")
    pairs = []
    for b in todo:
        if not b.get("locked") and result.get(b["id"]):
            b["translated"] = result[b["id"]]
        pairs.append({"src": b["original"], "dst": b.get("translated", "")})
    return pairs
