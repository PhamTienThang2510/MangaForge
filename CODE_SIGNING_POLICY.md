# Chính sách ký số / Code signing policy

Free code signing provided by [SignPath.io](https://about.signpath.io/), certificate by [SignPath Foundation](https://signpath.org/).

- Chỉ ký các bản build được tạo tự động bởi GitHub Actions từ mã nguồn công khai trong repo này
  (workflow [`.github/workflows/release.yml`](.github/workflows/release.yml)). Không ký file build trên máy cá nhân.
- Chỉ ký file của chính dự án (bộ cài `MangaForge-Setup-*.exe` và `MangaForge.exe`). Không ký file của bên thứ ba.

## Vai trò / Team roles

| Vai trò | Thành viên |
|---|---|
| Committers & reviewers | [@PhamTienThang2510](https://github.com/PhamTienThang2510) |
| Approvers (duyệt từng yêu cầu ký) | [@PhamTienThang2510](https://github.com/PhamTienThang2510) |

Mọi thành viên có quyền commit hoặc duyệt ký đều bật xác thực hai lớp (MFA) trên GitHub và SignPath.

## Quyền riêng tư

Xem [PRIVACY.md](PRIVACY.md).
