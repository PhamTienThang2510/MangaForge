// Tải uv.exe (trình cài Python của Astral, MIT/Apache-2.0) phiên bản cố định, kiểm tra SHA-256,
// đặt vào desktop/bin/uv.exe để đóng gói kèm bộ cài.   Dùng: node scripts/fetch_uv.js
const https = require('https');
const fs = require('fs');
const path = require('path');
const crypto = require('crypto');
const { execFileSync } = require('child_process');

const UV_VERSION = '0.11.32';
const ASSET = 'uv-x86_64-pc-windows-msvc.zip';
const BASE = `https://github.com/astral-sh/uv/releases/download/${UV_VERSION}/`;
const OUT_DIR = path.join(__dirname, '..', 'desktop', 'bin');

function get(url) {
  return new Promise((resolve, reject) => {
    https.get(url, { headers: { 'User-Agent': 'mangaforge-build' } }, r => {
      if (r.statusCode >= 300 && r.statusCode < 400 && r.headers.location) return resolve(get(r.headers.location));
      if (r.statusCode !== 200) return reject(new Error(`${url} -> HTTP ${r.statusCode}`));
      const chunks = []; r.on('data', c => chunks.push(c)); r.on('end', () => resolve(Buffer.concat(chunks)));
    }).on('error', reject);
  });
}

(async () => {
  const exe = path.join(OUT_DIR, 'uv.exe');
  const stamp = path.join(OUT_DIR, 'uv.version');
  if (fs.existsSync(exe) && fs.existsSync(stamp) && fs.readFileSync(stamp, 'utf8').trim() === UV_VERSION) {
    console.log(`uv ${UV_VERSION} đã có sẵn.`); return;
  }
  fs.mkdirSync(OUT_DIR, { recursive: true });
  console.log(`Tải uv ${UV_VERSION}…`);
  const [zip, shaFile] = await Promise.all([get(BASE + ASSET), get(BASE + ASSET + '.sha256')]);
  const want = shaFile.toString().trim().split(/\s+/)[0].toLowerCase();
  const got = crypto.createHash('sha256').update(zip).digest('hex');
  if (want !== got) throw new Error(`Checksum uv không khớp: ${got} ≠ ${want}`);
  const tmp = path.join(OUT_DIR, ASSET);
  fs.writeFileSync(tmp, zip);
  // giải nén: ưu tiên tar.exe của Windows (bản tar của Git hiểu nhầm "E:" là máy từ xa), dự phòng PowerShell
  const sysTar = path.join(process.env.SystemRoot || 'C:\\Windows', 'System32', 'tar.exe');
  if (fs.existsSync(sysTar)) execFileSync(sysTar, ['-xf', tmp, '-C', OUT_DIR]);
  else execFileSync('powershell', ['-NoProfile', '-Command', `Expand-Archive -LiteralPath '${tmp}' -DestinationPath '${OUT_DIR}' -Force`]);
  fs.rmSync(tmp);
  for (const f of fs.readdirSync(OUT_DIR)) if (!['uv.exe', 'uv.version'].includes(f)) fs.rmSync(path.join(OUT_DIR, f), { recursive: true, force: true });
  fs.writeFileSync(stamp, UV_VERSION);
  console.log('OK:', exe);
})().catch(e => { console.error(e.message); process.exit(1); });
