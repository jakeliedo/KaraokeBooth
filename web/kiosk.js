/**
 * Kiosk UI — màn cảm ứng ELO. Dùng cùng WebSocket API với app.js.
 */

const API = `${location.protocol}//${location.host}`;
const WS_URL = `${location.protocol === 'https:' ? 'wss' : 'ws'}://${location.host}/api/ws`;

// ─── state ──────────────────────────────────────────────────────────────────

let state = { player: {}, queue: [], now_playing: null };
let ws = null;
let searchTimer = null;
let searchInFlight = false;
let pendingSong = null;

// volume/pitch local mirror — luôn sync từ server state
let _volume = 100;
let _pitch = 0;
let _previewTimer = null;

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
  el.className = `chip ${cls}`.trim();
}

function showToast(msg, isError = false) {
  let t = document.getElementById('toast');
  if (!t) {
    t = document.createElement('div');
    t.id = 'toast';
    document.body.appendChild(t);
  }
  t.textContent = msg;
  t.className = isError ? 'toast error' : 'toast';
  t.hidden = false;
  clearTimeout(t._timer);
  t._timer = setTimeout(() => { t.hidden = true; }, 3000);
}

async function api(method, path, body) {
  const r = await fetch(`${API}${path}`, {
    method,
    headers: body ? { 'Content-Type': 'application/json' } : {},
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!r.ok) throw new Error(`${method} ${path} → ${r.status}`);
  // 204 No Content: không có body
  if (r.status === 204 || r.headers.get('content-length') === '0') return null;
  const ct = r.headers.get('content-type') || '';
  return ct.includes('json') ? r.json() : null;
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
    try {
      const msg = JSON.parse(data);
      applyEvent(msg.event, msg.data);
    } catch (e) {
      // bỏ qua message lỗi, không làm crash handler
    }
  };
}

function applyEvent(event, data) {
  if (!data) return;

  if (event === 'snapshot') {
    state.player = data.player || {};
    // data.queue = { current: {...}|null, items: [...] }
    const q = data.queue || {};
    state.queue = Array.isArray(q) ? q : (q.items || []);
    state.now_playing = Array.isArray(q) ? null : (q.current ?? null);
    syncLocalState();
    renderNowPlaying();
    renderQueue();
    return;
  }

  // queue_changed: data = { current: {...}|null, items: [...] }
  if (event === 'queue_changed') {
    state.queue = data.items || [];
    state.now_playing = data.current ?? null;
    if (state.now_playing?.song && !state.player.song) {
      state.player.song = state.now_playing.song;
    }
    renderQueue();
    renderNowPlaying();
    return;
  }

  // player events: merge, không replace
  if (data.state !== undefined) {
    state.player = { ...state.player, ...data };
    syncLocalState();
    renderNowPlaying();
  }

  if (event === 'position_changed' && data.position !== undefined) {
    updateProgress(data.position, data.duration ?? state.player.duration ?? 0);
  }
}

// Sync _volume/_pitch từ server state sau mỗi snapshot/player event
function syncLocalState() {
  const p = state.player;
  if (p.volume !== undefined) _volume = Math.min(100, p.volume);
  if (p.pitch !== undefined) _pitch = p.pitch;
}

// ─── NOW PLAYING ─────────────────────────────────────────────────────────────

function renderNowPlaying() {
  const p = state.player || {};
  const song = p.song || state.now_playing?.song;
  const preview = $('np-preview');

  if (song) {
    $('np-title').textContent = song.title || '—';
    const singer = p.song?.singer || state.now_playing?.singer;
    $('np-singer').textContent = singer ? `🎤 ${singer}` : '';
    // thumbnail làm fallback khi chưa có preview từ mpv
    if (preview && !preview._live) {
      preview.src = song.thumbnail || '';
    }
  } else {
    $('np-title').textContent = 'Chưa có bài';
    $('np-singer').textContent = '';
    if (preview) { preview.src = ''; preview._live = false; }
  }

  const playing = p.state === 'playing';
  $('btn-toggle').textContent = playing ? '⏸' : '▶';

  if (playing) _startPreview();
  else _stopPreview();

  updateProgress(p.position || 0, p.duration || 0);
  $('vol-val').textContent = _volume;
  $('pitch-val').textContent = _pitch >= 0 ? `+${_pitch}` : String(_pitch);
}

function _fetchPreview() {
  const img = $('np-preview');
  if (!img) return;
  const url = `/api/player/preview?t=${Date.now()}`;
  const tmp = new Image();
  tmp.onload = () => { img.src = url; img._live = true; };
  tmp.onerror = () => { img._live = false; };
  tmp.src = url;
}

function _startPreview() {
  if (_previewTimer) return;
  _fetchPreview();
  _previewTimer = setInterval(_fetchPreview, 3000);
}

function _stopPreview() {
  clearInterval(_previewTimer);
  _previewTimer = null;
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

  if (nowPlaying) list.appendChild(makeQueueItem(nowPlaying, 0, true));
  queue.forEach((item, i) => list.appendChild(makeQueueItem(item, i + 1, false)));
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
    ${!isNow ? `<button class="qdel" title="Xoá">✕</button>` : ''}
  `;

  if (!isNow) {
    li.querySelector('.qdel').addEventListener('click', e => {
      e.stopPropagation();
      api('DELETE', `/api/queue/${item.id}`).catch(() =>
        showToast('Không xoá được bài', true));
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
    list.innerHTML = '<li class="item no-result">Không tìm thấy bài nào.</li>';
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
        <span class="meta">${escHtml(song.channel || song.artist || '')}${song.duration ? ' · ' + fmtTime(song.duration) : ''}${song.source === 'local' ? ' · <b>có sẵn</b>' : ''}</span>
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
  if (!q.trim() || searchInFlight) return;
  searchInFlight = true;
  setStatus('Đang tìm…');
  try {
    const data = await api('GET', `/api/search?q=${encodeURIComponent(q)}`);
    renderResults(data.results || [], data.error);
    setStatus('Đã kết nối', 'ok');
  } catch {
    setStatus('Lỗi tìm kiếm', 'warn');
  } finally {
    searchInFlight = false;
  }
}

// ─── SINGER DIALOG ───────────────────────────────────────────────────────────

function openSingerDialog(song) {
  pendingSong = song;
  $('singer-title').textContent = song.title;
  $('singer-input').value = '';
  $('singer-dialog').showModal();
  requestAnimationFrame(() => {
    $('singer-input').focus();
    vkbShow($('singer-input'));
  });
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
    showToast(`Đã đặt: ${song.title}`);
  } catch {
    showToast('Đặt bài thất bại — thử lại', true);
  }
}

// ─── CONTROLS ────────────────────────────────────────────────────────────────

async function adjustVolume(delta) {
  _volume = Math.max(0, Math.min(100, _volume + delta));
  $('vol-val').textContent = _volume;
  api('POST', '/api/mixer/volume', { volume: _volume }).catch(console.error);
}

async function adjustPitch(delta) {
  const cap = state.player?.capabilities;
  const lo = cap?.pitch_range?.[0] ?? -4;
  const hi = cap?.pitch_range?.[1] ?? 4;
  _pitch = Math.max(lo, Math.min(hi, _pitch + delta));
  $('pitch-val').textContent = _pitch >= 0 ? `+${_pitch}` : String(_pitch);
  api('POST', '/api/mixer/pitch', { semitones: _pitch }).catch(console.error);
}

// ─── VIRTUAL KEYBOARD ────────────────────────────────────────────────────────

const VKB_ROWS = [
  ['1','2','3','4','5','6','7','8','9','0','✕'],
  ['Q','W','E','R','T','Y','U','I','O','P','⌫'],
  ['A','S','D','F','G','H','J','K','L'],
  ['Z','X','C','V','B','N','M',' ','↵'],
];

let kbTarget = null;

function _buildVkb() {
  const kb = document.createElement('div');
  kb.id = 'vkb';
  // prevent buttons from stealing focus away from the active input
  kb.addEventListener('pointerdown', e => e.preventDefault());

  for (const row of VKB_ROWS) {
    const rowEl = document.createElement('div');
    rowEl.className = 'vkb-row';
    for (const key of row) {
      const btn = document.createElement('button');
      btn.type = 'button';
      btn.className = 'vkb-key';
      if (key === '⌫')  { btn.classList.add('vkb-bs');    btn.textContent = '⌫'; }
      else if (key===' '){ btn.classList.add('vkb-space'); btn.textContent = 'Dấu cách'; }
      else if (key==='↵'){ btn.classList.add('vkb-enter'); btn.textContent = '↵'; }
      else if (key==='✕'){ btn.classList.add('vkb-close'); btn.textContent = '✕'; }
      else btn.textContent = key;
      btn.addEventListener('click', () => vkbKey(key));
      rowEl.appendChild(btn);
    }
    kb.appendChild(rowEl);
  }
  document.body.appendChild(kb);
  return kb;
}

function vkbKey(key) {
  if (key === '✕') { vkbHide(); return; }
  if (!kbTarget) return;

  if (key === '⌫') {
    const s = kbTarget.selectionStart ?? kbTarget.value.length;
    const e = kbTarget.selectionEnd   ?? s;
    const v = kbTarget.value;
    if (s !== e) {
      kbTarget.value = v.slice(0, s) + v.slice(e);
      kbTarget.setSelectionRange(s, s);
    } else if (s > 0) {
      kbTarget.value = v.slice(0, s - 1) + v.slice(s);
      kbTarget.setSelectionRange(s - 1, s - 1);
    }
    kbTarget.dispatchEvent(new Event('input', { bubbles: true }));
    return;
  }

  if (key === '↵') {
    if (kbTarget.id === 'q') {
      clearTimeout(searchTimer);
      doSearch(kbTarget.value);
    } else if (kbTarget.id === 'singer-input') {
      $('singer-dialog').close('ok');
    }
    vkbHide();
    return;
  }

  const ch = key === ' ' ? ' ' : key;
  const s = kbTarget.selectionStart ?? kbTarget.value.length;
  const e = kbTarget.selectionEnd   ?? s;
  kbTarget.value = kbTarget.value.slice(0, s) + ch + kbTarget.value.slice(e);
  kbTarget.setSelectionRange(s + 1, s + 1);
  kbTarget.dispatchEvent(new Event('input', { bubbles: true }));
}

function vkbShow(el) {
  kbTarget = el;
  (document.getElementById('vkb') || _buildVkb()).classList.add('visible');
  document.body.classList.add('kb-open');
}

function vkbHide() {
  kbTarget = null;
  document.getElementById('vkb')?.classList.remove('visible');
  document.body.classList.remove('kb-open');
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
  if (q.length >= 2) searchTimer = setTimeout(() => doSearch(q), 500);
});

$('q').addEventListener('focus', () => vkbShow($('q')));
$('q').addEventListener('blur', () => {
  // Delay so keyboard button clicks can fire before we hide
  setTimeout(() => {
    if (document.activeElement !== $('q') &&
        document.activeElement !== $('singer-input')) {
      vkbHide();
    }
  }, 80);
});

$('singer-input').addEventListener('focus', () => vkbShow($('singer-input')));
$('singer-input').addEventListener('blur', () => {
  setTimeout(() => {
    if (document.activeElement !== $('singer-input') &&
        kbTarget === $('singer-input')) {
      vkbHide();
    }
  }, 80);
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

// Enter trong singer input → submit OK (không phải cancel)
$('singer-input').addEventListener('keydown', e => {
  if (e.key === 'Enter') {
    e.preventDefault();
    $('singer-dialog').close('ok');
  }
});

$('singer-dialog').addEventListener('close', async () => {
  vkbHide();
  if ($('singer-dialog').returnValue === 'ok' && pendingSong) {
    await enqueue(pendingSong, $('singer-input').value.trim());
  }
  pendingSong = null;
});

// Backdrop click đóng dialog
$('singer-dialog').addEventListener('click', e => {
  if (e.target === $('singer-dialog')) $('singer-dialog').close('cancel');
});

// ─── INIT ────────────────────────────────────────────────────────────────────

connectWs();
