# KaraokeBooth

Hệ thống karaoke chuyên nghiệp chạy trên Linux cho một máy công nghiệp cố định.

Máy chạy hai màn hình: một màn cảm ứng làm bàn điều khiển và một TV chiếu video
karaoke. Khách chọn bài bằng điện thoại qua WiFi nội bộ do chính máy phát ra.
Tiếng ra mixer Yamaha MG10XU rồi tới amply và loa.

## Phần cứng đích

| Thành phần | Model | Ghi chú |
|---|---|---|
| Mainboard | AEWIN MB-8390 | công nghiệp, Intel |
| Ổ boot | CFast 2.0 16GB | chừa ~1.5GB chưa cấp phát cho wear-leveling |
| Ổ dữ liệu | SSD SATA | `/data` — thư viện, DB, log, cache |
| Màn hình | 2 (cảm ứng + TV) | một GPU, hai output |
| Âm thanh | Yamaha MG10XU (USB) | xem `docs/WIRING.md` |
| Mạng | Ethernet + WiFi AP | Ethernet ra router quán, WiFi phát cho khách |

## Kiến trúc

```
Màn cảm ứng (PySide6/QML) ─┐
                            ├─► karaoke-core (FastAPI + WebSocket) ─► mpv (JSON IPC) ─► TV
Điện thoại (PWA qua WiFi) ─┘              │
                                          └─► PipeWire filter-chain ─► USB ─► MG10XU ─► amply
```

`karaoke-core` là **nguồn sự thật duy nhất**. Màn cảm ứng và điện thoại đều chỉ là
client của cùng một REST API và cùng một luồng WebSocket — không có state nào sống
riêng trong UI. Thêm client mới không phải sửa core.

## Trạng thái

Dự án đang ở **Giai đoạn 0 — kiểm chứng phần cứng**. Xem [docs/PLAN.md](docs/PLAN.md)
để biết toàn bộ lộ trình, và [docs/VERIFY.md](docs/VERIFY.md) cho bảng kiểm chứng
phải chạy trên máy thật trước khi viết tiếp.

| Giai đoạn | Nội dung | Trạng thái |
|---|---|---|
| 0 | Kiểm chứng phần cứng, dựng VM phát triển | đang làm |
| 1 | YouTube + 2 màn hình + app điện thoại | chưa |
| 2 | Thư viện offline + mixer phần mềm | chưa |
| 3 | MIDI/Arirang (.mid, .kar) | chưa |
| 4 | Đóng gói image ra CFast, vận hành | chưa |

## Phát triển

Phát triển trong máy ảo QEMU chạy Debian 13, sau đó ghi image ra thẻ CFast.

```bash
# Trên máy phát triển (Linux hoặc VM)
python3 -m venv .venv && . .venv/bin/activate
pip install -e "core[dev]"
karaoke-core                      # http://127.0.0.1:8080

# Kiểm chứng phần cứng — chạy trên máy thật
sudo ./tools/verify-hardware.sh
```

Core chạy được cả khi **không có thiết bị âm thanh và không có mpv** — nó báo lỗi
trên UI và tự kết nối lại khi thiết bị xuất hiện. Nếu nó crash khi thiếu card thì
không test được gì trong VM, nên đây là ràng buộc bắt buộc.

## Cấu trúc

```
core/karaoke_core/   service Python: library, sources, queue, playback, audio, api
ui/                  app màn hình cảm ứng (PySide6 + QML)
web/                 PWA cho điện thoại (Vite + Svelte)
deploy/              provision.sh, systemd units, cấu hình Xorg/PipeWire/hostapd
tools/               verify-hardware.sh và các script chẩn đoán
docs/                PLAN.md, WIRING.md, VERIFY.md, TROUBLESHOOT.md
```

## Giấy phép

Chưa chọn. Dự án dùng mpv (GPL) và librubberband (GPL) qua **tiến trình riêng**,
không link thư viện — xem `docs/PLAN.md` mục rủi ro giấy phép trước khi phân phối.
