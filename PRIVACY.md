# Quyền riêng tư / Privacy policy

MangaForge chạy trên máy của bạn. **Dự án không thu thập, không gửi về và không lưu bất kỳ dữ liệu nào của bạn**:
không có tài khoản, không có thống kê sử dụng, không có telemetry.

Ứng dụng chỉ kết nối Internet trong các trường hợp sau:

| Khi nào | Kết nối tới | Gửi đi |
|---|---|---|
| Lần chạy đầu / khi cập nhật engine | `github.com` (Python qua uv), `pypi.org`, `download.pytorch.org` | Yêu cầu tải gói cài đặt |
| Lần chạy đầu | `github.com`, `huggingface.co` | Yêu cầu tải model AI |
| Lần đầu OCR tiếng Hàn/Trung/Anh | máy chủ model của EasyOCR (GitHub) | Yêu cầu tải model |
| Khi bạn bấm dịch | Dịch vụ **bạn chọn**: Google Translate, Anthropic (Claude), Google (Gemini), OpenAI, hoặc máy chủ cục bộ (LM Studio/Ollama) | Nội dung chữ cần dịch, glossary và ghi chú bạn nhập; API key của bạn |

Khi dùng dịch vụ dịch, nội dung gửi đi tuân theo chính sách của nhà cung cấp đó. API key chỉ được lưu trong file
project trên máy bạn (`Documents\MangaForge\projects\<tên>\project.json`).
Ảnh truyện **không** được gửi đi đâu — nhận diện, OCR và xoá chữ đều chạy trên máy.
