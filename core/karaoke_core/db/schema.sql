-- Schema của KaraokeBooth. Idempotent — chạy lại nhiều lần không sao.

CREATE TABLE IF NOT EXISTS schema_version (
    version    INTEGER PRIMARY KEY,
    applied_at REAL DEFAULT (unixepoch())
);
INSERT OR IGNORE INTO schema_version (version) VALUES (1);

-- Thư viện bài hát trên đĩa. Bài YouTube đã tải về cache cũng nằm ở đây.
CREATE TABLE IF NOT EXISTS songs (
    uid          TEXT PRIMARY KEY,          -- 'local:<hash>' hoặc 'youtube:<id>'
    source       TEXT NOT NULL,
    source_id    TEXT NOT NULL,
    title        TEXT NOT NULL,
    artist       TEXT DEFAULT '',
    channel      TEXT DEFAULT '',
    duration     INTEGER DEFAULT 0,
    path         TEXT,                      -- NULL = chưa có file trên đĩa
    thumbnail    TEXT DEFAULT '',
    song_code    TEXT,                      -- mã số 6 chữ số kiểu đầu karaoke
    content_hash TEXT,                      -- phát hiện file trùng
    format       TEXT DEFAULT 'video',      -- video | midi
    lyric_encoding     TEXT,                -- Giai đoạn 3: vni | tcvn3 | utf8 | ...
    encoding_confidence REAL,
    needs_review INTEGER DEFAULT 0,
    pinned       INTEGER DEFAULT 0,         -- 1 = không bao giờ dọn khỏi cache
    play_count   INTEGER DEFAULT 0,
    last_played  REAL,
    added_at     REAL DEFAULT (unixepoch())
);
CREATE INDEX IF NOT EXISTS idx_songs_code   ON songs(song_code);
CREATE INDEX IF NOT EXISTS idx_songs_played ON songs(last_played DESC);

-- Tìm kiếm toàn văn. Cột *_nd là bản đã bỏ dấu để gõ không dấu vẫn ra kết quả.
CREATE VIRTUAL TABLE IF NOT EXISTS songs_fts USING fts5(
    title, artist, title_nd, artist_nd,
    content='', tokenize='unicode61 remove_diacritics 2'
);

-- Cache metadata tìm kiếm YouTube, tránh gọi mạng lại khi gõ cùng từ khoá.
CREATE TABLE IF NOT EXISTS yt_cache (
    query      TEXT PRIMARY KEY,
    payload    TEXT NOT NULL,
    fetched_at REAL DEFAULT (unixepoch())
);

-- File không parse được (Giai đoạn 3). Không bao giờ để lỗi parse làm sập app.
CREATE TABLE IF NOT EXISTS quarantine (
    path     TEXT PRIMARY KEY,
    reason   TEXT,
    detail   TEXT,
    seen_at  REAL DEFAULT (unixepoch())
);

-- Nhật ký nghiệp vụ: trả lời "tối qua 9h có chuyện gì" mà không phải lội journald.
CREATE TABLE IF NOT EXISTS events (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    at       REAL DEFAULT (unixepoch()),
    kind     TEXT NOT NULL,   -- play | skip | preset | xrun | device_lost | error
    detail   TEXT
);
CREATE INDEX IF NOT EXISTS idx_events_at ON events(at DESC);

CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT
);
