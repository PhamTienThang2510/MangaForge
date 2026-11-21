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

Khi dùng dịch vụ dịch, nội dung gửi đi tuân theo chính sách của nhà cung cấp đó.

**API key** của bạn được mã hoá bằng Windows DPAPI (chỉ tài khoản Windows của bạn trên máy này giải mã được) và lưu ở
`%LOCALAPPDATA%\MangaForge\secrets.dat` — **không** nằm trong file project (nên không bị đồng bộ lên OneDrive hay lộ khi
bạn chia sẻ project), không ghi vào log, và giao diện chỉ hiển thị dạng che `••••abcd`.

Server nội bộ của app chỉ nghe trên `127.0.0.1` (máy khác không truy cập được) và từ chối mọi yêu cầu không đến từ chính
giao diện MangaForge (chống DNS rebinding / CSRF từ trang web lạ).
Ảnh truyện **không** được gửi đi đâu — nhận diện, OCR và xoá chữ đều chạy trên máy.
