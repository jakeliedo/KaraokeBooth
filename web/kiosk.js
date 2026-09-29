/**
 * Kiosk UI — màn cảm ứng ELO. Dùng cùng WebSocket API với app.js.
 * Không dùng framework: vanilla JS thuần, dễ debug khi mất mạng nội bộ.
 */

const API = `${location.protocol}//${location.host}`;
const WS_URL = `${location.protocol === 'https:' ? 'wss' : 'ws'}://${location.host}/api/ws`;

// ─── state ──────────────────────────────────────────────────────────────────

let state = { player: {}, queue: [], seq: -1 };
let ws = null;
let searchTimer = null;
let pendingSong = null;  // song đang chờ nhập tên ca sĩ

// ─── helpers ────────────────────────────────────────────────────────────────

const $ = id => document.getElementById(id);

function fmtTime(sec) {
  if (!sec || sec < 0) return '0:00';
  const m = Math.floor(sec / 60);
  const s = Math.floor(sec % 60);
  return `${m}:${s.toString().padStart(2, '0')}`;
}

function escHtml(s) {
  const d = document.createElement('div');
  d.textContent = s ?? '';
  return d.innerHTML;
}

function setStatus(text, cls = '') {
  const el = $('status');
  el.textContent = text;
  el.className = `chip ${cls}`;
}

async function api(method, path, body) {
  const r = await fetch(`${API}${path}`, {
    method,
    headers: body ? { 'Content-Type': 'application/json' } : {},
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!r.ok) throw new Error(`${method} ${path} → ${r.status}`);
  return r.json();
}

// ─── WebSocket ───────────────────────────────────────────────────────────────

function connectWs() {
  ws = new WebSocket(WS_URL);

  ws.onopen = () => setStatus('Đã kết nối', 'ok');

  ws.onclose = () => {
    setStatus('Mất kết nối — đang thử lại…', 'warn');
    setTimeout(connectWs, 3000);
  };

  ws.onerror = () => ws.close();

  ws.onmessage = ({ data }) => {
    const msg = JSON.parse(data);
    applyEvent(msg.event, msg.data);
  };
}

function applyEvent(event, data) {
  if (!data) return;

  if (event === 'snapshot') {
    state = data;
    renderNowPlaying();
    renderQueue();
    return;
  }

  // player events
  if (data.state !== undefined) {
    state.player = data;
    renderNowPlaying();
  }

  // queue events
  if (data.queue !== undefined) {
    state.queue = data.queue;
    state.now_playing = data.now_playing;
    renderQueue();
  }

  if (event === 'position_changed' && data.position !== undefined) {
    updateProgress(data.position, data.duration);
  }
}

// ─── NOW PLAYING ─────────────────────────────────────────────────────────────

function renderNowPlaying() {
  const p = state.player || {};
  const song = p.song;

  if (song) {
    $('np-title').textContent = song.title || '—';
    $('np-singer').textContent = song.singer ? `🎤 ${song.singer}` : '';
    const art = $('np-art');
    if (song.thumbnail) {
      art.innerHTML = `<img src="${escHtml(song.thumbnail)}" alt="" onerror="this.style.display='none'">`;
    } else {
      art.innerHTML = defaultArtSvg();
    }
  } else {
    $('np-title').textContent = 'Chưa có bài';
    $('np-singer').textContent = '';
    $('np-art').innerHTML = defaultArtSvg();
  }

  // play/pause button
  const playing = p.state === 'playing';
  $('btn-toggle').textContent = playing ? '⏸' : '▶';

  updateProgress(p.position || 0, p.duration || 0);
  $('vol-val').textContent = p.volume ?? 100;
  $('pitch-val').textContent = (p.pitch ?? 0) >= 0 ? `+${p.pitch ?? 0}` : String(p.pitch);
}

function defaultArtSvg() {
  return `<svg viewBox="0 0 80 80" fill="none" xmlns="http://www.w3.org/2000/svg">
    <circle cx="40" cy="40" r="38" stroke="#333" stroke-width="2"/>
    <circle cx="40" cy="40" r="14" fill="#222"/>
    <path d="M34 31l18 9-18 9V31z" fill="#555"/>
  </svg>`;
}

function updateProgress(pos, dur) {
  $('np-pos').textContent = fmtTime(pos);
  $('np-dur').textContent = fmtTime(dur);
  const pct = dur > 0 ? Math.min(100, (pos / dur) * 100) : 0;
  $('progress-fill').style.width = `${pct}%`;
}

// ─── QUEUE ───────────────────────────────────────────────────────────────────

function renderQueue() {
  const list = $('queue-list');
  const empty = $('queue-empty');
  const countEl = $('queue-count');

  const queue = state.queue || [];
  const nowPlaying = state.now_playing;

  const total = (nowPlaying ? 1 : 0) + queue.length;
  countEl.textContent = total > 0 ? String(total) : '';
  countEl.className = `chip${total > 0 ? ' ok' : ''}`;

  list.innerHTML = '';
  empty.hidden = total > 0;

  if (nowPlaying) {
    list.appendChild(makeQueueItem(nowPlaying, 0, true));
  }
  queue.forEach((item, i) => {
    list.appendChild(makeQueueItem(item, i + 1, false));
  });
}

function makeQueueItem(item, pos, isNow) {
  const li = document.createElement('li');
  li.className = `qitem${isNow ? ' now' : ''}`;

  const thumb = item.song?.thumbnail
    ? `<img class="qthumb" src="${escHtml(item.song.thumbnail)}" alt="" onerror="this.style.display='none'">`
    : `<span class="qthumb-ph"></span>`;

  li.innerHTML = `
    <span class="qpos">${isNow ? '♫' : pos}</span>
    ${thumb}
    <span class="qbody">
      <span class="qtitle">${escHtml(item.song?.title || '—')}</span>
      ${item.singer ? `<span class="qsinger">🎤 ${escHtml(item.singer)}</span>` : ''}
    </span>
    ${!isNow ? `<button class="qdel" data-id="${escHtml(item.id)}" title="Xoá">✕</button>` : ''}
  `;

  if (!isNow) {
    li.querySelector('.qdel').addEventListener('click', e => {
      e.stopPropagation();
      api('DELETE', `/api/queue/${item.id}`).catch(console.error);
    });
  }

  return li;
}

// ─── SEARCH ──────────────────────────────────────────────────────────────────

function renderResults(results, note) {
  const list = $('results');
  const noteEl = $('search-note');
  noteEl.hidden = !note;
  noteEl.textContent = note || '';
  list.innerHTML = '';

  if (!results.length) {
    list.innerHTML = '<li class="item" style="cursor:default"><span class="body"><span class="title" style="color:var(--muted)">Không tìm thấy bài nào.</span></span></li>';
    return;
  }

  for (const song of results) {
    const li = document.createElement('li');
    li.className = 'item';

    const thumb = song.thumbnail
      ? `<img class="thumb" src="${escHtml(song.thumbnail)}" alt="" loading="lazy" onerror="this.style.display='none'">`
      : `<span class="thumb-ph">♪</span>`;

    li.innerHTML = `
      ${thumb}
      <span class="body">
        <span class="title">${escHtml(song.title)}</span>
        <span class="meta">${escHtml(song.channel || song.artist || '')}${song.duration ? ' · ' + fmtTime(song.duration) : ''}${song.source === 'local' ? ' · có sẵn' : ''}</span>
      </span>
      <button class="add-btn" title="Đặt bài">+</button>
    `;

    li.querySelector('.add-btn').addEventListener('click', e => {
      e.stopPropagation();
      openSingerDialog(song);
    });
    li.addEventListener('click', () => openSingerDialog(song));
    list.appendChild(li);
  }
}

async function doSearch(q) {
  if (!q.trim()) return;
  setStatus('Đang tìm…');
  try {
    const data = await api('GET', `/api/search?q=${encodeURIComponent(q)}`);
    renderResults(data.results || [], data.error);
    setStatus('Đã kết nối', 'ok');
  } catch {
    setStatus('Lỗi tìm kiếm', 'warn');
  }
}

// ─── SINGER DIALOG ───────────────────────────────────────────────────────────

function openSingerDialog(song) {
  pendingSong = song;
  $('singer-title').textContent = song.title;
  $('singer-input').value = '';
  $('singer-dialog').showModal();
  setTimeout(() => $('singer-input').focus(), 50);
}

async function enqueue(song, singer) {
  try {
    await api('POST', '/api/queue', {
      source: song.source,
      source_id: song.source_id,
      title: song.title,
      artist: song.artist || '',
      channel: song.channel || '',
      duration: song.duration || 0,
      thumbnail: song.thumbnail || '',
      singer,
      client_id: 'kiosk',
    });
  } catch (e) {
    console.error('enqueue error', e);
  }
}

// ─── CONTROLS ────────────────────────────────────────────────────────────────

let _volume = 100;
let _pitch = 0;

async function adjustVolume(delta) {
  _volume = Math.max(0, Math.min(130, _volume + delta));
  $('vol-val').textContent = _volume;
  await api('POST', '/api/mixer/volume', { volume: _volume }).catch(console.error);
}

async function adjustPitch(delta) {
  const p = state.player || {};
  const cap = p.capabilities;
  const lo = cap?.pitch_range?.[0] ?? -4;
  const hi = cap?.pitch_range?.[1] ?? 4;
  _pitch = Math.max(lo, Math.min(hi, _pitch + delta));
  $('pitch-val').textContent = _pitch >= 0 ? `+${_pitch}` : String(_pitch);
  await api('POST', '/api/mixer/pitch', { semitones: _pitch }).catch(console.error);
}

// ─── EVENT LISTENERS ─────────────────────────────────────────────────────────

$('search-form').addEventListener('submit', e => {
  e.preventDefault();
  clearTimeout(searchTimer);
  doSearch($('q').value);
});

$('q').addEventListener('input', () => {
  clearTimeout(searchTimer);
  const q = $('q').value.trim();
  if (q.length >= 2) {
    searchTimer = setTimeout(() => doSearch(q), 500);
  }
});

$('btn-toggle').addEventListener('click', () =>
  api('POST', '/api/player/toggle').catch(console.error));

$('btn-next').addEventListener('click', () =>
  api('POST', '/api/player/next').catch(console.error));

$('btn-replay').addEventListener('click', () =>
  api('POST', '/api/player/replay').catch(console.error));

$('vol-dn').addEventListener('click', () => adjustVolume(-5));
$('vol-up').addEventListener('click', () => adjustVolume(+5));
$('pitch-dn').addEventListener('click', () => adjustPitch(-1));
$('pitch-up').addEventListener('click', () => adjustPitch(+1));

$('singer-dialog').addEventListener('close', async () => {
  if ($('singer-dialog').returnValue === 'ok' && pendingSong) {
    await enqueue(pendingSong, $('singer-input').value.trim());
  }
  pendingSong = null;
});

// ─── INIT ────────────────────────────────────────────────────────────────────

connectWs();
