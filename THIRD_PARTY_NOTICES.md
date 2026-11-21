# Thành phần bên thứ ba / Third-party notices

MangaForge được phát hành theo GNU GPL v3.0 hoặc mới hơn. Các thành phần dưới đây thuộc về tác giả của chúng và
dùng theo giấy phép tương ứng (tất cả đều tương thích với GPL-3.0). Hãy xem trang gốc để biết toàn văn giấy phép.

## Mã nguồn đi kèm

| Thành phần | Tác giả / nguồn | Giấy phép | Ghi chú |
|---|---|---|---|
| comic-text-detector | dmMaze — https://github.com/dmMaze/comic-text-detector | GPL-3.0 | Chép nguyên vào `engine/vendor/comic_text_detector/` (bỏ phần huấn luyện), kèm LICENSE gốc |

## Model AI (KHÔNG đóng gói — app tải trực tiếp từ nguồn gốc khi chạy lần đầu)

| Model | Nguồn tải | Giấy phép |
|---|---|---|
| comictextdetector.pt.onnx (dò chữ) | https://github.com/zyddnys/manga-image-translator/releases/tag/beta-0.3 — model của comic-text-detector | GPL-3.0 |
| anime-manga-big-lama.pt (xoá chữ) | https://github.com/Sanster/models/releases/tag/AnimeMangaInpainting — bản TorchScript của dreMaz/AnimeMangaInpainting (https://huggingface.co/dreMaz/AnimeMangaInpainting), tinh chỉnh từ LaMa (https://github.com/advimman/lama) | MIT (AnimeMangaInpainting); LaMa gốc: Apache-2.0 |
| manga-ocr-base (OCR tiếng Nhật) | https://huggingface.co/kha-white/manga-ocr-base | Apache-2.0 |
| EasyOCR (OCR Hàn/Trung/Anh, tự tải khi cần) | https://github.com/JaidedAI/EasyOCR | Apache-2.0 |

Checksum SHA-256 của từng file nằm trong `engine/modelstore.py`.

## Font đi kèm (`fonts/`)

Tất cả lấy từ kho chính thức https://github.com/google/fonts, giấy phép **SIL Open Font License 1.1**; bản giấy phép
của từng họ font ở `fonts/licenses/`. Be Vietnam Pro, Bangers, Patrick Hand, Pangolin, Mansalva, Fuzzy Bubbles,
Dela Gothic One, Bungee, Vina Sans, Black Ops One, Sigmar One, Cherry Bomb One, Playpen Sans, Shantell Sans, Baloo 2.
Playpen Sans, Shantell Sans, Baloo 2 là bản tĩnh dựng từ font variable gốc bằng fontTools (OFL cho phép).

## Thư viện chạy kèm (được cài khi chạy lần đầu)

| Thư viện | Giấy phép |
|---|---|
| Python (bản dựng python-build-standalone qua uv) | PSF License |
| PyTorch, torchvision | BSD-3-Clause |
| FastAPI | MIT |
| Uvicorn | BSD-3-Clause |
| python-multipart | Apache-2.0 |
| requests | Apache-2.0 |
| NumPy | BSD-3-Clause |
| OpenCV (opencv-python-headless) | Apache-2.0 (gói), MIT (đóng gói) |
| Pillow | MIT-CMU (HPND) |
| Shapely | BSD-3-Clause |
| pyclipper | MIT |
| tqdm | MPL-2.0 / MIT |
| manga-ocr | Apache-2.0 |
| Hugging Face Transformers | Apache-2.0 |
| fugashi | MIT |
| unidic-lite | MIT (gói); từ điển UniDic: BSD-3-Clause / LGPL / GPL (chọn một) |
| EasyOCR | Apache-2.0 |
| openpyxl | MIT |
| psd-tools | MIT |
| img2pdf | LGPL-3.0-or-later |

## Ứng dụng desktop

| Thành phần | Giấy phép |
|---|---|
| Electron | MIT |
| uv (Astral) — đóng gói kèm để cài Python | MIT / Apache-2.0 |
| electron-builder (chỉ dùng khi build) | MIT |
