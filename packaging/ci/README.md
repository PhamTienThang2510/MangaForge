# Workflow build & phát hành

`release.yml` là workflow GitHub Actions build bộ cài Windows (và ký số qua SignPath nếu đã cấu hình).
Nó cần nằm ở `.github/workflows/release.yml` để chạy. Cách bật (chỉ cần làm một lần):

**Cách 1 — trên web GitHub:** Add file → Create new file → đặt tên `.github/workflows/release.yml`,
dán nội dung file này vào → Commit.

**Cách 2 — bằng git:** cần token có quyền `workflow`
(GitHub → Settings → Developer settings → Personal access tokens → tick `repo` + `workflow`), rồi:

```powershell
git mv packaging/ci/release.yml .github/workflows/release.yml
git commit -m "Bật workflow build & phát hành"
git push
```
