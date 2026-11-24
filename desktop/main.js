// MangaForge desktop — vỏ Electron.
// Lần chạy đầu: tự cài engine Python (qua uv) + tải model AI từ nguồn gốc, có màn hình tiến độ.
// Các lần sau: khởi động engine và mở giao diện.
const { app, BrowserWindow, ipcMain, shell, Menu, dialog } = require('electron');
const { spawn, execFile } = require('child_process');
const crypto = require('crypto');
const http = require('http');
const net = require('net');
const os = require('os');
const path = require('path');
const fs = require('fs');

const VERSION = app.getVersion();
// Vị trí mã nguồn engine/web/fonts: trong bản cài -> resources/, khi phát triển -> thư mục repo
const SRC = app.isPackaged ? process.resourcesPath : path.resolve(__dirname, '..');
const ENGINE_SRC = path.join(SRC, 'engine');
const IS_WINDOWS = process.platform === 'win32';
const TORCH = IS_WINDOWS
  ? { version: '2.6.0', vision: '0.21.0', cuda: 'cu124' }
  : { version: '2.7.1', vision: '0.22.1', cuda: 'cu128' };

// ---------- vị trí dữ liệu
// HOME: engine Python + model AI + log (vài GB).  DATA: project + font tự thêm.
// Người dùng chọn thư mục ở lần chạy đầu; lựa chọn lưu trong %APPDATA%\MangaForge\location.json.
// Bản ≤0.3.2 dùng %LOCALAPPDATA%\MangaForge + Documents\MangaForge: nếu đã cài ở đó thì giữ nguyên.
const xdgData = process.env.XDG_DATA_HOME;
const DEFAULT_HOME = path.join(IS_WINDOWS
  ? process.env.LOCALAPPDATA || app.getPath('appData')
  : xdgData && path.isAbsolute(xdgData) ? xdgData : path.join(os.homedir(), '.local', 'share'),
  'MangaForge');
const LOC_FILE = path.join(app.getPath('userData'), 'location.json');
// Các thư mục Windows Defender "Controlled folder access" bảo vệ mặc định -> python.exe bị chặn ghi
const PROTECTED = ['documents', 'desktop', 'pictures', 'videos', 'music'];
let HOME = null, DATA = null, VENV = null, PY = null, MARKER = null;
let forceChoose = false, needBytes = 0;

function setLocation(home, data) {
  HOME = home; DATA = data;
  VENV = path.join(HOME, 'engine');
  PY = path.join(VENV, ...(IS_WINDOWS ? ['Scripts', 'python.exe'] : ['bin', 'python']));
  MARKER = path.join(VENV, '.mangaforge-ready.json');
}
function saveLocation(home, data) {
  fs.mkdirSync(path.dirname(LOC_FILE), { recursive: true });
  fs.writeFileSync(LOC_FILE, JSON.stringify({ home, data, at: new Date().toISOString() }, null, 2));
  setLocation(home, data);
}
function loadLocation() {
  if (process.env.MF_HOME) { setLocation(process.env.MF_HOME, process.env.MF_DATA || null); return true; }
  try {
    const l = JSON.parse(fs.readFileSync(LOC_FILE, 'utf8'));
    if (l.home && l.data) { setLocation(l.home, l.data); return true; }
  } catch (e) {}
  if (IS_WINDOWS && !forceChoose && fs.existsSync(path.join(DEFAULT_HOME, 'engine', '.mangaforge-ready.json'))) {
    // cập nhật từ bản cũ: engine đã nằm ở vị trí cũ -> giữ nguyên, khỏi tải lại vài GB
    const docs = path.join(app.getPath('documents'), 'MangaForge');
    saveLocation(DEFAULT_HOME, fs.existsSync(path.join(docs, 'projects')) ? docs : DEFAULT_HOME);
    return true;
  }
  return false;
}
// chọn "F:\" -> dùng "F:\MangaForge" để không rải file ra gốc ổ
const normTarget = d => path.basename(d).toLowerCase() === 'mangaforge' ? path.resolve(d) : path.join(path.resolve(d), 'MangaForge');
function freeBytes(dir) {
  let p = path.resolve(dir);
  while (!fs.existsSync(p)) { const up = path.dirname(p); if (up === p) return null; p = up; }
  try { const s = fs.statfsSync(p); return s.bavail * s.bsize; } catch (e) { return null; }
}
const gb = b => (b / 1073741824).toFixed(1).replace('.', ',') + ' GB';
function checkTarget(dir) {
  for (const k of IS_WINDOWS ? PROTECTED : []) {
    let p; try { p = app.getPath(k); } catch (e) { continue; }
    const rel = path.relative(p, dir);
    if (!rel || (!rel.startsWith('..') && !path.isAbsolute(rel)))
      return `Không nên chọn thư mục nằm trong ${p}: Windows Defender (Controlled folder access) thường chặn ghi ở đó. Hãy chọn nơi khác, ví dụ D:\\MangaForge.`;
  }
  try {
    fs.mkdirSync(dir, { recursive: true });
    const probe = fs.mkdtempSync(path.join(dir, '.mf-write-test-'));
    fs.rmdirSync(probe);
  } catch (e) { return `Không ghi được vào ${dir} (${e.code || e.message}) — hãy chọn thư mục khác.`; }
  const free = freeBytes(dir);
  if (free != null && free < needBytes) return `Ổ này chỉ còn trống ${gb(free)}, cần khoảng ${gb(needBytes)}. Hãy chọn ổ khác.`;
  return null;
}

const logDir = () => path.join(HOME || app.getPath('userData'), 'logs');
const log = m => {
  try { const d = logDir(); fs.mkdirSync(d, { recursive: true }); fs.appendFileSync(path.join(d, 'desktop.log'), `${new Date().toISOString()} ${m}\n`); }
  catch (e) {}
};
process.on('uncaughtException', e => log('uncaught ' + (e && e.stack)));

let win = null, server = null, port = 0, setupBusy = false;
let recent = []; // các dòng output gần nhất của tiến trình con, để đoán nguyên nhân lỗi

function uvPath() {
  const name = IS_WINDOWS ? 'uv.exe' : 'uv';
  const devBin = IS_WINDOWS ? ['bin', name] : ['bin', 'linux', name];
  const cands = [path.join(SRC, 'bin', name), path.join(__dirname, ...devBin)];
  for (const c of cands) if (fs.existsSync(c)) return c;
  return 'uv'; // khi phát triển: dùng uv trong PATH
}
function uvEnv() {
  return { ...process.env, UV_PYTHON_INSTALL_DIR: path.join(HOME, 'python'), UV_CACHE_DIR: path.join(HOME, 'cache'),
    UV_PYTHON_PREFERENCE: 'only-managed', UV_NO_CONFIG: '1', PYTHONIOENCODING: 'utf-8' };
}
const engineEnv = extra => ({ ...process.env, MF_HOME: HOME, ...(DATA ? { MF_DATA: DATA } : {}), PYTHONIOENCODING: 'utf-8', ...extra });
const send = (ch, d) => { if (win && !win.isDestroyed()) win.webContents.send(ch, d); };
const step = (id, state, text) => { send('setup:step', { id, state, text }); log(`[step] ${id} ${state} ${text || ''}`); };
const line = t => { send('setup:log', t); log('  ' + t); recent.push(t); if (recent.length > 80) recent.shift(); };

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
  if (!IS_WINDOWS) return Promise.resolve(process.env.MF_TORCH === 'cuda');
  if (process.env.MF_TORCH) return Promise.resolve(process.env.MF_TORCH !== 'cpu');
  return new Promise(res => execFile('nvidia-smi', ['-L'], { windowsHide: true, timeout: 8000 },
    (err, out) => res(!err && /GPU/i.test(String(out)))));
}

function reqHash() {
  const r = fs.readFileSync(path.join(ENGINE_SRC, 'requirements.txt'));
  return crypto.createHash('sha256').update(r).update(JSON.stringify(TORCH)).digest('hex').slice(0, 16);
}
function engineReady() {
  try {
    const m = JSON.parse(fs.readFileSync(MARKER, 'utf8'));
    return fs.existsSync(PY) && m.req === reqHash()
      && (IS_WINDOWS || m.flavor === (process.env.MF_TORCH === 'cuda' ? TORCH.cuda : 'cpu'));
  }
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
  if (!IS_WINDOWS) fs.rmSync(MARKER, { force: true });
  try { await run(uv, ['venv', VENV, '--python', '3.12', '--allow-existing']); }
  catch (e) {
    if (!IS_WINDOWS && e.code === 'ENOENT') throw new Error('Không tìm thấy uv. Hãy cài uv và thêm vào PATH, hoặc dùng gói .deb');
    throw e;
  }
  step('python', 'ok');
  step('torch', 'run', gpu ? 'Đang tải PyTorch bản GPU (NVIDIA CUDA) — bước lâu nhất, khoảng 2,5 GB…' : 'Đang tải PyTorch bản CPU…');
  await run(uv, ['pip', 'install', '--python', PY, `torch==${TORCH.version}`, `torchvision==${TORCH.vision}`,
    '--index-url', `https://download.pytorch.org/whl/${flavor}`,
    ...(IS_WINDOWS ? [] : ['--reinstall-package', 'torch', '--reinstall-package', 'torchvision'])]);
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
  return new Promise((res, reject) => {
    const s = net.createServer();
    s.once('error', e => e.code === 'EADDRINUSE' ? res(freePort(start + 1)) : reject(e));
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
  const out = fs.openSync(path.join(logDir(), 'engine.log'), 'a');
  try { server = spawn(PY, ['main.py'], { cwd: ENGINE_SRC, env, windowsHide: true, stdio: ['ignore', out, out] }); }
  finally { fs.closeSync(out); }
  const child = server;
  const clearServer = () => { if (server === child) server = null; };
  let spawnError;
  child.once('error', e => { spawnError = e; clearServer(); });
  child.once('exit', c => { log('engine exit ' + c); clearServer(); });
  for (let i = 0; i < 360; i++) {
    if (server !== child) throw spawnError || new Error(`Engine dừng đột ngột — xem ${path.join(logDir(), 'engine.log')}`);
    if (await ping()) { step('start', 'ok'); return; }
    await new Promise(r => setTimeout(r, 500));
  }
  stopEngine();
  throw new Error(`Engine không phản hồi sau 3 phút — xem ${path.join(logDir(), 'engine.log')}`);
}

function showSetup() {
  if (!win.webContents.getURL().endsWith('setup.html')) win.loadFile(path.join(__dirname, 'setup.html'));
}

// lỗi do không ghi được thư mục (Controlled folder access, thiếu quyền) -> báo rõ thay vì "lỗi mạng"
function writeBlocked(msg) {
  return /MF_WRITE_BLOCKED|PermissionError|\[WinError 5\]|Access is denied|EPERM|EACCES/i.test(msg + '\n' + recent.join('\n'));
}

async function boot() {
  if (setupBusy) return;
  setupBusy = true;
  recent = [];
  try {
    if (!HOME && !loadLocation()) {
      // lần chạy đầu: cho người dùng chọn nơi lưu (engine + model + project)
      const gpu = await hasNvidia();
      needBytes = (gpu ? 6.5 : 3) * 1073741824;
      log(`choose location (default ${DEFAULT_HOME}, need ${gb(needBytes)})`);
      send('setup:choose', { dir: DEFAULT_HOME, free: freeBytes(DEFAULT_HOME), need: needBytes, gpu, windows: IS_WINDOWS });
      return;
    }
    log(`location home=${HOME} data=${DATA || '(mặc định)'}`);
    if (!engineReady()) await installEngine();
    else ['python', 'torch', 'libs'].forEach(s => step(s, 'ok'));
    if (!(await modelsReady())) await downloadModels();
    else step('models', 'ok');
    await startEngine();
    win.loadURL(`http://127.0.0.1:${port}/`);
  } catch (e) {
    log('boot failed ' + (e && e.stack));
    showSetup();
    const msg = String((e && e.message) || e);
    const blocked = e?.syscall !== 'listen' && writeBlocked(msg);
    let message = `${msg} — kiểm tra kết nối mạng / dung lượng ổ đĩa rồi bấm “Thử lại”.`;
    if (blocked && IS_WINDOWS) {
      message = `Windows không cho MangaForge ghi vào ${DATA || HOME}. Thường do Windows Security → "Controlled folder access" chặn python.exe. ` +
        `Hãy bấm “Chọn thư mục khác”, hoặc cho phép python.exe trong Windows Security rồi bấm “Thử lại”.`;
    } else if (blocked) {
      message = `Không ghi được vào ${DATA || HOME}. Hãy kiểm tra quyền ghi hoặc chọn thư mục khác.`;
    }
    send('setup:error', { blocked, message });
  } finally { setupBusy = false; }
}

ipcMain.handle('setup:retry', () => { boot(); });
ipcMain.handle('setup:logs', () => { const d = logDir(); fs.mkdirSync(d, { recursive: true }); return shell.openPath(d); });
ipcMain.handle('setup:meta', () => ({ version: VERSION, home: HOME }));
ipcMain.handle('setup:space', (_e, dir) => (typeof dir === 'string' ? { dir, free: freeBytes(dir), need: needBytes } : null));
ipcMain.handle('setup:pick', async () => {
  const r = await dialog.showOpenDialog(win, { title: 'Chọn nơi lưu dữ liệu MangaForge', properties: ['openDirectory', 'createDirectory'] });
  return r.canceled || !r.filePaths[0] ? null : normTarget(r.filePaths[0]);
});
ipcMain.handle('setup:confirm', (_e, dir) => {
  if (HOME || setupBusy) return 'Đã chọn thư mục rồi.';
  if (typeof dir !== 'string' || !path.isAbsolute(dir)) return 'Đường dẫn không hợp lệ.';
  dir = path.resolve(dir);
  const err = checkTarget(dir);
  if (err) return err;
  saveLocation(dir, dir);
  forceChoose = false;
  boot();
  return null;
});
// chọn lại thư mục (chỉ khi đang ở màn hình lỗi, trước khi engine chạy)
ipcMain.handle('setup:rechoose', () => {
  if (setupBusy || server || process.env.MF_HOME) return;
  try { fs.unlinkSync(LOC_FILE); } catch (e) {}
  HOME = DATA = VENV = PY = MARKER = null;
  forceChoose = true;
  boot();
});

function stopEngine() {
  const child = server;
  server = null;
  if (!child?.pid) return;
  if (IS_WINDOWS) {
    spawn('taskkill', ['/pid', String(child.pid), '/T', '/F'], { windowsHide: true })
      .once('error', e => { log(`taskkill: ${e.message}`); child.kill(); });
  } else {
    child.kill('SIGTERM');
  }
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
    // xuất file (ZIP/PDF/PSD/Excel) -> hộp thoại "Lưu thành"
    win.webContents.session.on('will-download', (e, item) => item.setSaveDialogOptions({ defaultPath: item.getFilename() }));
    win.loadFile(path.join(__dirname, 'setup.html'));
    win.webContents.once('did-finish-load', boot);
    loadLocation();
    log(`start v${VERSION} src=${SRC} home=${HOME || '(chưa chọn)'}`);
  });
  app.on('before-quit', stopEngine);
  app.on('window-all-closed', () => { stopEngine(); app.quit(); });
}
