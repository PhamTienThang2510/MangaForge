# Đưa MangaForge lên winget

Người dùng cài bằng `winget install MangaForge.MangaForge` — không bị SmartScreen chặn vì file không tải qua trình duyệt.

Sau mỗi bản phát hành (Release không còn ở trạng thái nháp):

```powershell
winget install wingetcreate
# lần đầu:
wingetcreate new https://github.com/PhamTienThang2510/MangaForge/releases/download/vX.Y.Z/MangaForge-Setup-X.Y.Z.exe
# các bản sau:
wingetcreate update MangaForge.MangaForge --version X.Y.Z --urls https://github.com/PhamTienThang2510/MangaForge/releases/download/vX.Y.Z/MangaForge-Setup-X.Y.Z.exe --submit
```

Khi `wingetcreate new` hỏi:

| Trường | Giá trị |
|---|---|
| PackageIdentifier | `MangaForge.MangaForge` |
| Publisher | `MangaForge contributors` |
| License | `GPL-3.0-or-later` |
| InstallerType | `nullsoft` (bộ cài NSIS) |
| Scope | `user` |
| ShortDescription | Công cụ dịch truyện tranh mã nguồn mở |

`wingetcreate` mở Pull Request vào kho https://github.com/microsoft/winget-pkgs; bot của Microsoft tự kiểm tra (quét virus, cài thử) rồi duyệt.
