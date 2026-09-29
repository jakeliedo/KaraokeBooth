# Đấu nối âm thanh

## Giới hạn của Yamaha MG10XU cần biết trước

Cổng USB của MG10XU lấy tín hiệu từ **stereo bus** (bản trộn chính), **không tách
được từng kênh mic**. Hai hệ quả:

1. Cái vào máy tính là bản đã trộn sẵn cả mic lẫn nhạc, đã qua fader.
2. Nếu đưa tiếng đã xử lý từ máy trả về mixer, tín hiệu đó lại nằm trên stereo bus
   và quay vòng ra USB lần nữa → **vòng lặp phản hồi số, hú ngay lập tức**.

Nghĩa là chuỗi `mic → mixer → USB → DSP → USB → mixer → amply` **không chạy được**.

Phải chọn một trong hai mức dưới đây. Quyết định dựa trên kết quả đo ở
[VERIFY.md](VERIFY.md) mục 5.

---

## Mức A — Chỉ MG10XU (mặc định, không mua thêm gì)

```
Mic 1 ──► MG10XU ch1 (D-PRE, HPF, 1-knob comp, SPX reverb/echo)
Mic 2 ──► MG10XU ch2                                    │
                                                        ▼
PC ──USB──► MG10XU (USB IN, về stereo bus) ──► STEREO OUT ──► amply ──► loa
```

**Máy tính xử lý gì:** nhạc — EQ 4 băng, âm lượng, đổi tông, đổi tempo, limiter.
Chỉnh được từ màn cảm ứng và điện thoại.

**Máy tính KHÔNG xử lý gì:** mic. Reverb, echo, compressor của mic nằm hoàn toàn
trên MG10XU và chỉnh bằng núm vật lý.

**Không có chống hú bằng phần mềm.** Vòng hú là mic → loa → mic, hoàn toàn nằm
ngoài máy tính; phần mềm không chèn được notch vào đường đó. Máy chỉ có thể thu
bản trộn chính để **phát hiện và cảnh báo** trên màn hình, không dập được.

**Ưu điểm:** độ trễ mic bằng 0, không mua gì thêm, PC chết vẫn còn tiếng mic.

---

## Mức B — Thêm audio interface (đúng yêu cầu ban đầu)

```
Mic 1 ──► UMC204HD in1 ──┐
Mic 2 ──► UMC204HD in2 ──┴─USB─► PC: gate → comp → EQ → de-esser
                                     → notch chống hú → reverb → echo → limiter
                                                        │
                    UMC204HD line out ─────────────────┘
                              │
                              ▼
                    MG10XU ch5/6 (line in) ──► STEREO OUT ──► amply ──► loa
```

Máy **thu từ UMC204HD**, không thu từ MG10XU → không có vòng lặp. MG10XU lúc này
chỉ còn làm khối trộn analog cuối và đường bypass khẩn cấp.

**Phần cứng cần thêm:** Behringer UMC204HD (2 mic preamp, 2 in / 4 out, ~2.5–3tr)
hoặc UMC404HD (4 in / 4 out, ~4tr — cho phép tách bus mic và bus nhạc ra hai đường
amply riêng, chỉnh cân bằng bằng núm vật lý).

**Nếu MG10XU có cổng INSERT trên kênh mono:** có thể dùng cáp insert TRS→TS cắm
nửa chừng làm direct out, lấy tín hiệu mic sau preamp ra một soundcard USB rẻ hơn.
Phải kiểm tra mặt sau mixer — MG10XU có thể không có insert (MG12XU/MG16XU thì có).

**Độ trễ round-trip mục tiêu < 20ms.** Phải đo bằng cáp loopback vật lý và
`pw-jack jack_iodelay`, không được đoán.

---

## Quy tắc chung cho cả hai mức

- Cắm thiết bị USB audio **trực tiếp vào cổng trên board, không qua hub**.
- Cáp USB ngắn, có ferrite, **cố định bằng dây rút** — rớt cáp giữa buổi hát là
  sự cố hay gặp nhất.
- Tránh cắm chung root hub với WiFi. USB3 phát nhiễu băng 2.4GHz — thêm một lý do
  để WiFi AP chạy 5GHz.
- **Vô hiệu hóa hẳn node HDMI audio** bằng rule WirePlumber, để nhạc không bao giờ
  ra loa TV do chọn nhầm thiết bị.
- Ghim thiết bị theo `node.name`/serial USB, **không theo chỉ số card** — thứ tự
  card đổi sau mỗi lần reboot.

## Chống hú — 4 lớp (chỉ đầy đủ ở Mức B)

1. **Vật lý** — hiệu quả nhất và miễn phí: mic supercardioid, loa đặt trước mặt
   người hát và hướng ra xa mic, không treo loa sau lưng người hát.
2. **Ring-out lúc lắp đặt** — wizard trong app: tăng dần gain, phát hiện tần số
   ring đầu tiên, cắm notch Q=20 gain −8dB, lặp 6–8 lần, lưu vào preset phòng.
   Đây là kỹ thuật chuẩn ngành PA.
3. **Notch động lúc chạy** — nhánh phân tích FFT chạy ngoài đường audio, tìm đỉnh
   hẹp có biên độ tăng đơn điệu >300ms, gán notch tạm 20–30s rồi thả dần.
4. **Master limiter + nút PANIC** trên UI (mute toàn bộ mic tức thì).

Không hứa với khách hàng là "tự động chống hú hoàn hảo" — không có nút thần kỳ.
