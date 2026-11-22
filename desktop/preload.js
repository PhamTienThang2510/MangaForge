// Cầu nối an toàn giữa màn hình cài đặt (setup.html) và tiến trình chính.
const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('mf', {
  on: (ch, fn) => {
    if (!['setup:step', 'setup:log', 'setup:progress', 'setup:error', 'setup:info', 'setup:choose'].includes(ch)) return;
    ipcRenderer.on(ch, (_e, d) => fn(d));
  },
  retry: () => ipcRenderer.invoke('setup:retry'),
  openLogs: () => ipcRenderer.invoke('setup:logs'),
  meta: () => ipcRenderer.invoke('setup:meta'),
  // chọn nơi lưu dữ liệu ở lần chạy đầu
  space: dir => ipcRenderer.invoke('setup:space', dir),
  pick: () => ipcRenderer.invoke('setup:pick'),
  confirm: dir => ipcRenderer.invoke('setup:confirm', dir),
  rechoose: () => ipcRenderer.invoke('setup:rechoose'),
});
