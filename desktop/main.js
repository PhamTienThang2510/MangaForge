// MangaForge desktop — vỏ Electron.
// Lần chạy đầu: tự cài engine Python (qua uv) + tải model AI từ nguồn gốc, có màn hình tiến độ.
// Các lần sau: khởi động engine và mở giao diện.
const { app, BrowserWindow, ipcMain, shell, Menu } = require('electron');
const { spawn, execFile } = require('child_process');
const crypto = require('crypto');
const http = require('http');
const net = require('net');
const path = require('path');
const fs = require('fs');

const VERSION = app.getVersion();
// Vị trí mã nguồn engine/web/fonts: trong bản cài -> resources/, khi phát triển -> thư mục repo
const SRC = app.isPackaged ? process.resourcesPath : path.resolve(__dirname, '..');
const ENGINE_SRC = path.join(SRC, 'engine');
const HOME = process.env.MF_HOME || path.join(process.env.LOCALAPPDATA || app.getPath('appData'), 'MangaForge');
const VENV = path.join(HOME, 'engine');
const PY = path.join(VENV, 'Scripts', 'python.exe');
const MARKER = path.join(VENV, '.mangaforge-ready.json');
const LOG_DIR = path.join(HOME, 'logs');
const TORCH = { version: '2.6.0', vision: '0.21.0', cuda: 'cu124' };

fs.mkdirSync(LOG_DIR, { recursive: true });
const LOG = path.join(LOG_DIR, 'desktop.log');
const log = m => { try { fs.appendFileSync(LOG, `${new Date().toISOString()} ${m}\n`); } catch (e) {} };
process.on('uncaughtException', e => log('uncaught ' + (e && e.stack)));

let win = null, server = null, port = 0, setupBusy = false;

function uvPath() {
  const cands = [path.join(SRC, 'bin', 'uv.exe'), path.join(__dirname, 'bin', 'uv.exe')];
  for (const c of cands) if (fs.existsSync(c)) return c;
  return 'uv'; // khi phát triển: dùng uv trong PATH
}
function uvEnv() {
  return { ...process.env, UV_PYTHON_INSTALL_DIR: path.join(HOME, 'python'), UV_CACHE_DIR: path.join(HOME, 'cache'),
    UV_PYTHON_PREFERENCE: 'only-managed', UV_NO_CONFIG: '1', PYTHONIOENCODING: 'utf-8' };
}
const engineEnv = extra => ({ ...process.env, MF_HOME: HOME, PYTHONIOENCODING: 'utf-8', ...extra });
const send = (ch, d) => { if (win && !win.isDestroyed()) win.webContents.send(ch, d); };
const step = (id, state, text) => { send('setup:step', { id, state, text }); log(`[step] ${id} ${state} ${text || ''}`); };
const line = t => { send('setup:log', t); log('  ' + t); };

function run(cmd, args, opts = {}) {
  return new Promise((resolve, reject) => {
    log(`$ ${cmd} ${args.join(' ')}`);
    const p = spawn(cmd, args, { windowsHide: true, env: opts.env || uvEnv(), cwd: opts.cwd });
    const onData = d => String(d).split(/\r?\n|\r/).filter(Boolean).forEach(t => (opts.onLine || line)(t));
    p.stdout.on('data', onData); p.stderr.on('data', onData);
    p.on('error', reject);
    p.on('exit', c => c === 0 ? resolve() : reject(new Error(`${path.basename(cmd)} thoát với mã ${c}`)));
  });
}

function hasNvidia() {
  if (process.env.MF_TORCH) return Promise.resolve(process.env.MF_TORCH !== 'cpu');
  return new Promise(res => execFile('nvidia-smi', ['-L'], { windowsHide: true, timeout: 8000 },
    (err, out) => res(!err && /GPU/i.test(String(out)))));
}

function reqHash() {
  const r = fs.readFileSync(path.join(ENGINE_SRC, 'requirements.txt'));
  return crypto.createHash('sha256').update(r).update(JSON.stringify(TORCH)).digest('hex').slice(0, 16);
}
function engineReady() {
  try { const m = JSON.parse(fs.readFileSync(MARKER, 'utf8')); return fs.existsSync(PY) && m.req === reqHash() ? m : null; }
  catch (e) { return null; }
}
function modelsReady() {
  return new Promise(res => execFile(PY, ['modelstore.py', '--status', '--json'],
    { cwd: ENGINE_SRC, windowsHide: true, env: engineEnv(), timeout: 300000 },
    (err, out) => { try { res(JSON.parse(String(out).trim().split('\n').pop()).ready); } catch (e) { res(false); } }));
}

// ---------- cài engine (lần đầu, hoặc khi bản mới đổi danh sách thư viện)
async function installEngine() {
  const gpu = await hasNvidia();
  const flavor = gpu ? TORCH.cuda : 'cpu';
  send('setup:info', { gpu, size: gpu ? 'khoảng 3–4 GB' : 'khoảng 1–1,5 GB' });
  const uv = uvPath();
  step('python', 'run', 'Đang chuẩn bị Python 3.12…');
  await run(uv, ['venv', VENV, '--python', '3.12', '--allow-existing']);
  step('python', 'ok');
  step('torch', 'run', gpu ? 'Đang tải PyTorch bản GPU (NVIDIA CUDA) — bước lâu nhất, khoảng 2,5 GB…' : 'Đang tải PyTorch bản CPU…');
  await run(uv, ['pip', 'install', '--python', PY, `torch==${TORCH.version}`, `torchvision==${TORCH.vision}`,
    '--index-url', `https://download.pytorch.org/whl/${flavor}`]);
  step('torch', 'ok');
  step('libs', 'run', 'Đang cài thư viện OCR, xử lý ảnh, xuất file…');
  await run(uv, ['pip', 'install', '--python', PY, '-r', path.join(ENGINE_SRC, 'requirements.txt')]);
  step('libs', 'ok');
  fs.writeFileSync(MARKER, JSON.stringify({ req: reqHash(), flavor, version: VERSION, at: new Date().toISOString() }));
}

function downloadModels() {
  return new Promise((resolve, reject) => {
    step('models', 'run', 'Đang tải model AI từ nguồn gốc (khoảng 750 MB)…');
    const p = spawn(PY, ['modelstore.py', '--download', '--json'], { cwd: ENGINE_SRC, windowsHide: true, env: engineEnv() });
    let err = '';
    const onData = d => String(d).split(/\r?\n/).filter(Boolean).forEach(t => {
      try {
        const e = JSON.parse(t);
        if (e.event === 'progress') send('setup:progress', e);
        else if (e.event === 'file') line(`Tải ${e.file} — ${e.note || ''}`);
        else if (e.event === 'verify') line(`Kiểm tra checksum ${e.file}`);
        else if (e.event === 'retry') line(`Thử lại ${e.file}: ${e.message}`);
        else if (e.event === 'error') { err = e.message; line('LỖI: ' + e.message); }
      } catch (x) { line(t); }
    });
    p.stdout.on('data', onData); p.stderr.on('data', onData);
    p.on('error', reject);
    p.on('exit', c => c === 0 ? (step('models', 'ok'), resolve()) : reject(new Error(err || 'Tải model thất bại')));
  });
}

// ---------- khởi động engine
function freePort(start) {
  return new Promise(res => {
    const s = net.createServer();
    s.once('error', () => res(freePort(start + 1)));
    s.listen(start, '127.0.0.1', () => s.close(() => res(start)));
  });
}
function ping() {
  return new Promise(res => http.get(`http://127.0.0.1:${port}/api/fonts`, r => { r.resume(); res(r.statusCode === 200); })
    .on('error', () => res(false)));
}
async function startEngine() {
  step('start', 'run', 'Đang khởi động engine AI…');
  port = await freePort(8765);
  const env = engineEnv({ MF_PORT: String(port), MF_NO_BROWSER: '1', MF_VERSION: VERSION,
    MF_WEB: path.join(SRC, 'web'), MF_FONTS: path.join(SRC, 'fonts') });
  const out = fs.openSync(path.join(LOG_DIR, 'engine.log'), 'a');
  server = spawn(PY, ['main.py'], { cwd: ENGINE_SRC, env, windowsHide: true, stdio: ['ignore', out, out] });
  server.on('exit', c => { log('engine exit ' + c); server = null; });
  for (let i = 0; i < 360; i++) {
    if (!server) throw new Error('Engine dừng đột ngột — xem logs\\engine.log');
    if (await ping()) { step('start', 'ok'); return; }
    await new Promise(r => setTimeout(r, 500));
  }
  throw new Error('Engine không phản hồi sau 3 phút — xem logs\\engine.log');
}

function showSetup() {
  if (!win.webContents.getURL().endsWith('setup.html')) win.loadFile(path.join(__dirname, 'setup.html'));
}

async function boot() {
  if (setupBusy) return;
  setupBusy = true;
  try {
    if (!engineReady()) await installEngine();
    else ['python', 'torch', 'libs'].forEach(s => step(s, 'ok'));
    if (!(await modelsReady())) await downloadModels();
    else step('models', 'ok');
    await startEngine();
    win.loadURL(`http://127.0.0.1:${port}/`);
  } catch (e) {
    log('boot failed ' + (e && e.stack));
    showSetup();
    send('setup:error', String((e && e.message) || e));
  } finally { setupBusy = false; }
}

ipcMain.handle('setup:retry', () => { boot(); });
ipcMain.handle('setup:logs', () => shell.openPath(LOG_DIR));
ipcMain.handle('setup:meta', () => ({ version: VERSION, home: HOME }));

function stopEngine() {
  if (server) { try { spawn('taskkill', ['/pid', String(server.pid), '/T', '/F'], { windowsHide: true }); } catch (e) {} server = null; }
}

if (!app.requestSingleInstanceLock()) app.quit();
else {
  app.on('second-instance', () => { if (win) { if (win.isMinimized()) win.restore(); win.focus(); } });
  app.whenReady().then(() => {
    Menu.setApplicationMenu(null);
    win = new BrowserWindow({ width: 1500, height: 920, minWidth: 1100, minHeight: 700, backgroundColor: '#0f1115',
      title: 'MangaForge', show: false, autoHideMenuBar: true,
      webPreferences: { preload: path.join(__dirname, 'preload.js'), contextIsolation: true, sandbox: true } });
    win.once('ready-to-show', () => win.show());
    win.webContents.setWindowOpenHandler(({ url }) => { shell.openExternal(url); return { action: 'deny' }; });
    // xuất file (ZIP/PDF/PSD/Excel) -> hộp thoại "Lưu thành" của Windows
    win.webContents.session.on('will-download', (e, item) => item.setSaveDialogOptions({ defaultPath: item.getFilename() }));
    win.loadFile(path.join(__dirname, 'setup.html'));
    win.webContents.once('did-finish-load', boot);
    log(`start v${VERSION} src=${SRC} home=${HOME}`);
  });
  app.on('before-quit', stopEngine);
  app.on('window-all-closed', () => { stopEngine(); app.quit(); });
}
