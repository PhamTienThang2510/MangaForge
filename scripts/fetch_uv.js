// Tải uv (Astral, MIT/Apache-2.0) phiên bản cố định và kiểm tra SHA-256 trước khi đóng gói.
const https = require('https');
const fs = require('fs');
const os = require('os');
const path = require('path');
const crypto = require('crypto');
const { execFileSync } = require('child_process');

const UV_VERSION = '0.11.32';
const LINUX = process.argv[2] === '--linux';
const ASSET = LINUX ? 'uv-x86_64-unknown-linux-gnu.tar.gz' : 'uv-x86_64-pc-windows-msvc.zip';
const BASE = `https://github.com/astral-sh/uv/releases/download/${UV_VERSION}/`;
const BIN_DIR = path.join(__dirname, '..', 'desktop', 'bin');
const OUT_DIR = LINUX ? path.join(BIN_DIR, 'linux') : BIN_DIR;

function get(url) {
  return new Promise((resolve, reject) => {
    https.get(url, { headers: { 'User-Agent': 'mangaforge-build' } }, r => {
      if (r.statusCode >= 300 && r.statusCode < 400 && r.headers.location) return resolve(get(r.headers.location));
      if (r.statusCode !== 200) return reject(new Error(`${url} -> HTTP ${r.statusCode}`));
      const chunks = [];
      r.on('error', reject);
      r.on('data', c => chunks.push(c));
      r.on('end', () => resolve(Buffer.concat(chunks)));
    }).on('error', reject);
  });
}

(async () => {
  const name = LINUX ? 'uv' : 'uv.exe';
  const exe = path.join(OUT_DIR, name);
  const stamp = path.join(OUT_DIR, 'uv.version');
  if (fs.existsSync(exe) && fs.existsSync(stamp) && fs.readFileSync(stamp, 'utf8').trim() === UV_VERSION) {
    console.log(`uv ${UV_VERSION} đã có sẵn.`); return;
  }
  fs.mkdirSync(OUT_DIR, { recursive: true });
  console.log(`Tải uv ${UV_VERSION}…`);
  const [archive, shaFile] = await Promise.all([get(BASE + ASSET), get(BASE + ASSET + '.sha256')]);
  const want = shaFile.toString().trim().split(/\s+/)[0].toLowerCase();
  const got = crypto.createHash('sha256').update(archive).digest('hex');
  if (want !== got) throw new Error(`Checksum uv không khớp: ${got} ≠ ${want}`);
  const stage = fs.mkdtempSync(path.join(os.tmpdir(), 'mangaforge-uv-'));
  try {
    const tmp = path.join(stage, ASSET);
    fs.writeFileSync(tmp, archive);
    if (LINUX) {
      execFileSync('tar', ['-xzf', tmp, '-C', stage, '--strip-components=1', 'uv-x86_64-unknown-linux-gnu/uv'],
        { stdio: 'inherit' });
    } else {
      // tar.exe của Windows xử lý đường dẫn ổ đĩa đúng; dự phòng PowerShell.
      const sysTar = path.join(process.env.SystemRoot || 'C:\\Windows', 'System32', 'tar.exe');
      if (fs.existsSync(sysTar)) execFileSync(sysTar, ['-xf', tmp, '-C', stage], { stdio: 'inherit' });
      else execFileSync('powershell', ['-NoProfile', '-Command',
        'Expand-Archive -LiteralPath $env:MF_UV_ARCHIVE -DestinationPath $env:MF_UV_STAGE -Force'],
        { env: { ...process.env, MF_UV_ARCHIVE: tmp, MF_UV_STAGE: stage }, stdio: 'inherit' });
    }
    fs.copyFileSync(path.join(stage, name), exe);
    if (LINUX) fs.chmodSync(exe, 0o755);
  } finally {
    fs.rmSync(stage, { recursive: true, force: true });
  }
  fs.writeFileSync(stamp, UV_VERSION);
  console.log('OK:', exe);
})().catch(e => { console.error(e.message); process.exit(1); });
