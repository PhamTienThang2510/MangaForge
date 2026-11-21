<p align="center"><img src="desktop/icon.png" width="96" alt=""></p>

<h1 align="center">MangaForge</h1>
<p align="center"><b>Công cụ dịch truyện tranh mã nguồn mở cho người làm dịch</b><br>
Nhận diện chữ → OCR → xoá chữ → dịch theo ngữ cảnh cả chương → chèn chữ tiếng Việt → xuất PNG / PDF / PSD / Excel</p>

<p align="center">
<a href="../../releases/latest">⬇ Tải bản cài cho Windows</a> ·
<a href="#tính-năng">Tính năng</a> ·
<a href="#phát-triển">Phát triển</a> ·
<a href="THIRD_PARTY_NOTICES.md">Giấy phép bên thứ ba</a> ·
<a href="#-ủng-hộ-dự-án">☕ Ủng hộ</a>
</p>

---

## Tính năng

- **Quản lý theo chương**: mỗi chương là một project; xử lý cả chương ở nền, có tiến độ.
- **Nhận diện & OCR**: phát hiện ô chữ (comic-text-detector), OCR tiếng Nhật (manga-ocr), Hàn/Trung/Anh (EasyOCR), tự sắp thứ tự đọc.
- **Xoá chữ sạch**: LaMa tinh chỉnh cho manga; bong bóng nền phẳng được tô thẳng màu nền nên giữ nguyên viền; **tự dò lại chữ còn sót và xoá thêm**; cọ xoá tay.
- **Nhận diện loại bong bóng**: thoại, suy nghĩ, hét, dẫn truyện, chữ trên tranh, SFX — chữ dịch được dàn khít theo hình bong bóng thật.
- **Dịch theo ngữ cảnh cả chương**: gửi cả trang + các câu trang trước + glossary (tên riêng, xưng hô) + văn phong cho Claude / Gemini / OpenAI / LM Studio / Ollama.
- **Editor trực quan**: so sánh trước/sau bằng thanh kéo; kéo/đổi cỡ ô, chữ cập nhật ngay; nhấp đúp để sửa chữ; nhập số chính xác cho khung, cỡ chữ, giãn dòng, màu, viền; hoàn tác/làm lại.
- **Giữ nguyên chữ gốc** cho ô không cần dịch (logo, tiêu đề, SFX…).
- **Thư viện font**: 18 font Google (OFL) viết được tiếng Việt; thêm font riêng, tự kiểm tra font có đủ dấu tiếng Việt.
- **Xuất**: PNG (ZIP), PDF, PSD 3 lớp (gốc / nền sạch / chữ), Excel lời thoại.
- **Tab Tình trạng**: chỉ rõ ô OCR trống, ô chưa dịch, ô chữ tràn khung.

## Cài đặt (người dùng)

1. Tải `MangaForge-Setup-x.y.z.exe` ở trang [Releases](../../releases/latest) và chạy.
2. Lần mở đầu tiên app tự cài engine AI (cần Internet, **một lần**):
   - Máy có card **NVIDIA** → bản tăng tốc GPU (khoảng 3–4 GB).
   - Máy không có → bản CPU (khoảng 1–1,5 GB, chạy chậm hơn).
   - Model AI (~750 MB) được tải **trực tiếp từ nguồn gốc** (GitHub / Hugging Face) và kiểm tra SHA-256.
3. Dịch bằng AI: vào tab **Dịch**, chọn Claude / Gemini / OpenAI và nhập API key **của bạn** (key chỉ lưu trong máy bạn).

Dữ liệu: project và font tự thêm ở `Documents\MangaForge`; engine + model ở `%LOCALAPPDATA%\MangaForge` (xoá thư mục này để cài lại engine).

## Phát triển

Yêu cầu: Windows 10/11, [uv](https://docs.astral.sh/uv/), Node.js 20+.

```powershell
# engine (Python 3.12)
uv venv .venv --python 3.12
uv pip install --python .venv torch==2.6.0 torchvision==0.21.0 --index-url https://download.pytorch.org/whl/cu124   # hoặc .../whl/cpu
uv pip install --python .venv -r engine/requirements.txt
.venv\Scripts\python engine\modelstore.py --download      # tải model từ nguồn gốc
.venv\Scripts\python engine\main.py                       # mở http://127.0.0.1:8765

# app desktop
cd desktop
npm ci
npm start            # chạy thử (tự cài engine vào %LOCALAPPDATA%\MangaForge nếu chưa có)
npm run dist         # tạo bộ cài ../dist/MangaForge-Setup-x.y.z.exe
```

Cấu trúc:

| Thư mục | Nội dung |
|---|---|
| `engine/` | Server FastAPI + pipeline AI (`engine.py`, `bubble.py`, `lettering.py`, `translate.py`, `modelstore.py`) |
| `engine/vendor/comic_text_detector/` | Mã comic-text-detector (GPL-3.0) dùng để dò chữ |
| `web/` | Giao diện (một file HTML, không cần build) |
| `desktop/` | Vỏ Electron + màn hình cài engine lần đầu |
| `fonts/` | Font OFL kèm giấy phép (`scripts/fetch_fonts.py` tải lại từ google/fonts) |
| `scripts/` | Công cụ build: tải font, tải uv, vẽ icon |

Phát hành: đẩy tag `vX.Y.Z` → GitHub Actions build bộ cài, (ký số qua SignPath nếu đã cấu hình) và tạo Release. Xem [`.github/workflows/release.yml`](.github/workflows/release.yml).

## ☕ Ủng hộ dự án

MangaForge miễn phí và mã nguồn mở. Nếu app giúp ích cho nhóm dịch của bạn, bạn có thể ủng hộ để dự án được duy trì
và phát triển tiếp — mọi khoản ủng hộ dù nhỏ đều rất quý. Cảm ơn bạn! 💙

<p align="center"><img src="web/donate.png" width="300" alt="Mã VietQR chuyển khoản ủng hộ MangaForge"></p>

| Ngân hàng | Chủ tài khoản | Số tài khoản |
|---|---|---|
| Vietcombank — CN Thái Bình | PHAM TIEN THANG | `1030004669` |

Quét mã bằng app ngân hàng bất kỳ (VietQR / Napas 247). Nội dung chuyển khoản gợi ý: `Ung ho MangaForge`.

Không ủng hộ tiền cũng không sao — ⭐ star repo, báo lỗi, góp ý hay chia sẻ app cho bạn bè cũng là ủng hộ rất lớn.

## Giấy phép

MangaForge phát hành theo **GNU GPL v3.0 hoặc mới hơn** — xem [LICENSE](LICENSE).
Thành phần bên thứ ba và giấy phép của chúng: [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
Chính sách ký số: [CODE_SIGNING_POLICY.md](CODE_SIGNING_POLICY.md) · Quyền riêng tư: [PRIVACY.md](PRIVACY.md).

MangaForge là công cụ hỗ trợ dịch. Hãy tôn trọng bản quyền của tác giả và nhà xuất bản khi dịch và chia sẻ truyện.

---

### English

MangaForge is an open-source (GPL-3.0) desktop tool for manga/comic scanlation teams: text detection, OCR (JA/KO/ZH/EN),
inpainting with automatic leftover-text cleanup, speech-bubble type detection, chapter-level context-aware translation via
LLMs (Claude, Gemini, OpenAI-compatible, local LM Studio/Ollama), a WYSIWYG lettering editor, and PNG/PDF/PSD/Excel export.
The Windows installer sets up its Python engine on first launch with `uv` and downloads the AI models from their original
sources with SHA-256 verification.

If MangaForge helps you, you can support development via the VietQR code above (Vietcombank, PHAM TIEN THANG, `1030004669`). ⭐ Stars and bug reports help too!
