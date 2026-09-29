/**
 * App chọn bài cho điện thoại.
 *
 * Không có bước build — đây là ES module chạy thẳng. Khi app lớn hơn thì chuyển
 * sang Vite + Svelte, nhưng ở quy mô hiện tại thì một file tĩnh phục vụ được ngay
 * trong máy ảo mà không cần toolchain là đáng giá hơn.
 *
 * State đến từ WebSocket của core. App này KHÔNG giữ state riêng: mỗi message
 * mang `seq` tăng dần; thấy nhảy cóc là gọi /api/state lấy lại toàn bộ thay vì
 * cố ghép từ các delta.
 */

const API = '';
const clientId = getClientId();

let lastSeq = 0;
let ws = null;
let reconnectDelay = 500;
let pending = null; // bài đang chờ nhập tên người hát

const el = (id) => document.getElementById(id);

function getClientId() {
  let id = localStorage.getItem('karaoke-client-id');
  if (!id) {
    id = 'p-' + Math.random().toString(36).slice(2, 10);
    localStorage.setItem('karaoke-client-id', id);
  }
  return id;
}

function setStatus(text, kind = '') {
  const node = el('status');
  node.textContent = text;
  node.className = 'status ' + kind;
}

function fmtTime(seconds) {
  if (!seconds) return '';
  const s = Math.round(seconds);
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`;
}

// ------------------------------------------------------------------ WebSocket

function connect() {
  const proto = location.protocol === 'https:' ? 'wss:' : 'ws:';
  ws = new WebSocket(`${proto}//${location.host}/api/ws`);

  ws.onopen = () => {
    reconnectDelay = 500;
    setStatus('Đã kết nối', 'ok');
  };

  ws.onmessage = (event) => {
    const msg = JSON.parse(event.data);
    if (msg.event === 'snapshot') {
      lastSeq = msg.seq;
      render(msg.data);
      return;
    }
    // Mất gói -> lấy lại toàn bộ state, đừng đoán
    if (lastSeq && msg.seq > lastSeq + 1) {
      refreshState();
    }
    lastSeq = msg.seq;
    if (msg.event === 'queue_changed') renderQueue(msg.data);
    else if (msg.event === 'error') setStatus(msg.data.message || 'Có lỗi', 'warn');
    else if (msg.data && msg.data.song !== undefined) renderNowPlaying(msg.data);
  };

  ws.onclose = () => {
    setStatus('Mất kết nối, đang thử lại…', 'warn');
    setTimeout(connect, reconnectDelay);
    reconnectDelay = Math.min(reconnectDelay * 2, 10000);
  };
}

async function refreshState() {
  const state = await fetch(`${API}/api/state`).then((r) => r.json());
  render(state);
}

// ------------------------------------------------------------------ render

function render(state) {
  renderQueue(state.queue);
  renderNowPlaying(state.player);
}

function renderNowPlaying(player) {
  const node = el('now-playing');
  if (!player || !player.song) {
    node.hidden = true;
    return;
  }
  node.hidden = false;
  node.innerHTML = `
    <div class="now-label">Đang hát</div>
    <div class="now-title">${escapeHtml(player.song.title)}</div>
    <div class="now-meta">${fmtTime(player.position)} / ${fmtTime(player.duration)}</div>`;
}

function renderQueue(queue) {
  if (!queue) return;
  const list = el('queue');
  const items = queue.items || [];
  el('queue-count').textContent = items.length ? `(${items.length})` : '';
  el('queue-empty').hidden = items.length > 0 || !!queue.current;
  if (queue.current) renderNowPlaying({ song: queue.current.song, position: 0, duration: 0 });

  list.innerHTML = '';
  items.forEach((item, index) => {
    const li = document.createElement('li');
    li.className = 'item';
    const mine = item.added_by === clientId;
    li.innerHTML = `
      <span class="pos">${index + 1}</span>
      <span class="body">
        <span class="title">${escapeHtml(item.song.title)}</span>
        <span class="meta">${escapeHtml(item.singer || item.song.channel || '')}
          ${item.ready ? '' : '· đang tải'}</span>
      </span>`;
    if (mine) {
      const btn = document.createElement('button');
      btn.className = 'ghost';
      btn.textContent = 'Xoá';
      btn.onclick = () => removeItem(item.id);
      li.appendChild(btn);
    }
    list.appendChild(li);
  });
}

function renderResults(results, note) {
  const list = el('results');
  const noteNode = el('search-note');
  noteNode.hidden = !note;
  noteNode.textContent = note || '';

  list.innerHTML = '';
  if (!results.length) {
    list.innerHTML = '<li class="note">Không tìm thấy bài nào.</li>';
    return;
  }
  for (const song of results) {
    const li = document.createElement('li');
    li.className = 'item tappable';
    li.innerHTML = `
      ${song.thumbnail ? `<img class="thumb" src="${song.thumbnail}" alt="" loading="lazy" onerror="this.style.display='none'">` : '<span class="thumb-ph"></span>'}
      <span class="body">
        <span class="title">${escapeHtml(song.title)}</span>
        <span class="meta">${escapeHtml(song.channel || song.artist || '')}
          ${song.duration ? '· ' + fmtTime(song.duration) : ''}
          ${song.source === 'local' ? '· có sẵn' : ''}</span>
      </span>
      <span class="chev">+</span>`;
    li.onclick = () => askSinger(song);
    list.appendChild(li);
  }
}

function escapeHtml(text) {
  const div = document.createElement('div');
  div.textContent = text ?? '';
  return div.innerHTML;
}

// ------------------------------------------------------------------ hành động

el('search-form').onsubmit = async (event) => {
  event.preventDefault();
  const q = el('q').value.trim();
  if (!q) return;
  setStatus('Đang tìm…');
  try {
    const data = await fetch(`${API}/api/search?q=${encodeURIComponent(q)}`).then((r) => r.json());
    renderResults(data.results || [], data.error);
    setStatus('Đã kết nối', 'ok');
  } catch {
    setStatus('Không tìm được, kiểm tra kết nối', 'warn');
  }
};

function askSinger(song) {
  pending = song;
  el('singer-title').textContent = song.title;
  el('singer').value = localStorage.getItem('karaoke-singer') || '';
  el('singer-dialog').showModal();
}

el('singer-dialog').addEventListener('close', async (event) => {
  const dialog = event.target;
  if (dialog.returnValue !== 'ok' || !pending) {
    pending = null;
    return;
  }
  const singer = el('singer').value.trim();
  localStorage.setItem('karaoke-singer', singer);
  const song = pending;
  pending = null;

  const res = await fetch(`${API}/api/queue`, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({
      source: song.source,
      source_id: song.source_id,
      title: song.title,
      artist: song.artist || '',
      channel: song.channel || '',
      duration: song.duration || 0,
      thumbnail: song.thumbnail || '',
      singer,
      client_id: clientId,
    }),
  });
  setStatus(res.ok ? 'Đã đặt bài' : 'Đặt bài không được', res.ok ? 'ok' : 'warn');
  switchView('queue');
});

async function removeItem(id) {
  await fetch(`${API}/api/queue/${id}?client_id=${encodeURIComponent(clientId)}`, {
    method: 'DELETE',
  });
}

function switchView(name) {
  for (const tab of document.querySelectorAll('.tab')) {
    tab.classList.toggle('active', tab.dataset.view === name);
  }
  for (const view of document.querySelectorAll('.view')) {
    view.classList.toggle('active', view.id === `view-${name}`);
  }
}

for (const tab of document.querySelectorAll('.tab')) {
  tab.onclick = () => switchView(tab.dataset.view);
}

if ('serviceWorker' in navigator) {
  navigator.serviceWorker.register('sw.js').catch(() => {});
}

refreshState().catch(() => {});
connect();
