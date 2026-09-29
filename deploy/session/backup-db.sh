#!/bin/sh
# Sao lưu DB thư viện. Chạy hàng ngày qua karaoke-backup.timer.
set -eu

DB=/data/db/karaoke.db
DIR=/data/db/backup
STAMP=$(date +%F)
OUT="$DIR/karaoke-$STAMP.db"

mkdir -p "$DIR"

# Dùng .backup (API backup online) chứ KHÔNG dùng cp: copy một file SQLite đang mở
# là cách chắc chắn nhất để có bản sao hỏng.
sqlite3 "$DB" ".backup '$OUT'"

# Bản sao chưa được kiểm tra là bản sao chưa tồn tại.
if [ "$(sqlite3 "$OUT" 'PRAGMA integrity_check')" != "ok" ]; then
    echo "backup HỎNG: $OUT" >&2
    rm -f "$OUT"
    exit 1
fi

# Giữ 7 bản ngày. Bản tuần/tháng do rsnapshot hoặc script riêng lo nếu cần.
ls -1t "$DIR"/karaoke-*.db 2>/dev/null | tail -n +8 | xargs -r rm -f

# Một bản trên CFast: SSD chết hẳn thì vẫn còn metadata thư viện (danh mục, lịch
# sử, cấu hình). Quét lại SSD mới là xong, chỉ mất file video.
mkdir -p /persist/backup
cp -f "$OUT" /persist/backup/karaoke-latest.db

echo "backup OK: $OUT"
