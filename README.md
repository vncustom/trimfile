# Trim file – version 1.1 by Ly Han

Phần mềm Windows để **cắt** và **ghép (join)** nhiều file video hàng loạt, dùng ffmpeg. Viết bằng Python + Tkinter, không cần cài thư viện nào thêm.

## Tính năng

- Thêm nhiều file (hoặc cả thư mục) vào danh sách; mỗi file có **Mark In / Mark Out** riêng.
- **Xem trước** ngay trong app (có tiếng khi Play), kéo timeline hoặc gõ timecode để chọn đoạn cần cắt.
- Timecode dạng `HH:MM:SS:FF` (1 giây = 25 frame). Nhập **In + Out** thì **Duration** tự tính; nhập **In + Duration** thì **Out** tự điền.
- Bấm **START** để cắt tuần tự từ trên xuống dưới, có tiến độ từng file và tiến độ tổng, có nút Dừng.
- **Join files**: chọn nhiều file (mỗi file đã có In/Out), ghép các đoạn thành 1 file theo thứ tự trong danh sách.
- Thông số file thành phẩm chọn bằng dropdown, mục nào cũng có **Match Source** (giữ như file gốc):
  - Video: codec, size, bitrate (hoặc CRF), frame rate, tốc độ encode (preset), pixel format
  - Audio: codec, bitrate, sample rate, channels
  - Container: mp4, mkv, mov, avi, wmv, webm, ts
  - Tuỳ chọn **cắt chính xác từng frame**
- **Đặt tên file ra** cho từng file (ô *Tên file ra*, có cột hiển thị trong danh sách) và cho file Join.
- **Cắt copy theo keyframe**: ở chế độ cắt nhanh, app báo điểm bắt đầu thực tế của file ra và có nút đưa Mark In về keyframe trước / sau.
- **Profile**: lưu bộ thông số thành profile để dùng lại (`profiles.json`). Profile mặc định khi mở app là *Match Source - cắt chính xác frame*.
- Encoder phần cứng (NVENC / Intel QSV / AMD AMF) tự hiện trong danh sách nếu máy chạy được.

## Cài đặt

1. Cài **Python 3.10 trở lên** cho Windows (bản từ python.org, có sẵn Tkinter).
2. Tải ffmpeg bản build cho Windows (ví dụ bản *full* của [gyan.dev](https://www.gyan.dev/ffmpeg/builds/)) và chép **`ffmpeg.exe`, `ffprobe.exe`, `ffplay.exe`** vào **cùng thư mục** với `trimfile.py`.
   Các file `.exe` không được đưa lên git (xem `.gitignore`).
3. Chạy bằng cách mở **`TrimFile.bat`** (hoặc `python trimfile.py`).

## Cách dùng nhanh

1. **Thêm file** (hoặc *Thêm thư mục*). Muốn lấy nhiều đoạn từ 1 file thì bấm *Nhân đôi*.
2. Bấm vào 1 file để xem trước, tìm điểm bắt đầu rồi bấm **I** (Mark In), tìm điểm kết thúc rồi bấm **O** (Mark Out). Hoặc gõ timecode vào ô In / Out / Duration. File không đặt In/Out sẽ được xử lý cả file. Lưu ý khi gõ: `1:07` là **1 giây 7 frame**; muốn 1 phút 7 giây gõ `1:07:00` (hoặc `67`).
3. Chọn **Profile** và chỉnh thông số nếu cần.
4. Chọn nơi lưu: cùng thư mục file gốc, hoặc một thư mục riêng. File ra có hậu tố `_cut` (trùng tên thì tự thêm `_2`, `_3`…, không ghi đè). Muốn tự đặt tên cho từng file: chọn file trong danh sách, gõ vào ô **Tên file ra** rồi Enter (không cần gõ đuôi; cột "Tên file ra" trong danh sách hiện tên sẽ dùng, nút **Tự động** trả về tên mặc định).
5. Bấm **START**.

Muốn ghép: chọn từ 2 file trở lên (Ctrl/Shift + click) rồi bấm **Join files**. Các đoạn nối theo thứ tự từ trên xuống (đổi thứ tự bằng ▲ Lên / ▼ Xuống). Hộp xác nhận có ô **Tên file ra** để đặt tên file join; để trống thì tên là tên file đầu + hậu tố `_join`.

Bấm nút **Hướng dẫn sử dụng** (hoặc phím **F1**) trong app để xem bản hướng dẫn ngắn.

### Cắt nhanh (copy) và keyframe

1. Chọn profile *Match Source - cắt nhanh (copy)*, đặt Mark In / Mark Out.
2. Xem dòng chữ dưới ô Mark In/Out: ⚠ màu cam cho biết file ra thực tế bắt đầu ở đâu và sớm hơn Mark In bao nhiêu giây; ✔ màu xanh nghĩa là Mark In đã đúng keyframe.
3. Muốn Mark In khớp điểm cắt, bấm **một** trong hai nút: **In → keyframe trước** (đúng chỗ sẽ cắt) hoặc **In → keyframe sau** (bỏ phần thừa phía trước).
4. Bấm **START**.

Cần đúng từng frame thì dùng profile *cắt chính xác frame* (hai nút trên bị tắt).

## Phím tắt

| Phím | Chức năng |
|---|---|
| `Space` | Play / Pause |
| `I` / `O` | Mark In / Mark Out |
| `←` / `→` | Lùi / tới 1 frame |
| `Shift` + `←` / `→` | ±1 giây |
| `Ctrl` + `←` / `→` | ±10 giây |
| `Home` / `End` | Nhảy tới In / Out |
| `Delete` | Xoá file đang chọn khỏi danh sách |
| `F1` | Hướng dẫn sử dụng |

## Lưu ý về tốc độ và độ chính xác

- Nếu **mọi thông số là Match Source và không tick "cắt chính xác"** (profile *Match Source - cắt nhanh (copy)*): ffmpeg chỉ copy stream, rất nhanh, nhưng điểm vào có thể lệch về **keyframe** gần nhất trước đó (file `.wmv` thường cách nhau khoảng 5 giây). Ở chế độ này app hiện điểm bắt đầu thực tế của file ra, và hai nút **In → keyframe trước / sau** đưa Mark In về đúng keyframe. Hai nút này chỉ bật khi cắt copy, không ảnh hưởng cách cắt chính xác frame.
- **Cắt chính xác frame** (hoặc đổi size / bitrate / fps / codec…): video được encode lại nên đúng từng frame nhưng chậm hơn. Với *Match Source*, app dùng encoder tương đương codec gốc và giữ bitrate gốc.
- **Join luôn encode lại video** để ghép chính xác; các mục *Match Source* lấy theo file đầu tiên. Đoạn khác tỉ lệ khung hình được căn giữa với viền đen, đoạn không có tiếng được chèn im lặng.
- Container `.wmv` chỉ nhận codec Windows Media (WMV1/WMV2 + WMA). Nếu nguồn là WMV3 mà phải encode lại thì kết quả là WMV2.
- Timecode `HH:MM:SS:FF` chỉ để hiển thị/nhập (25 frame/giây); ffmpeg vẫn cắt theo thời gian thực của file nên với video 29,97 fps frame hiển thị là làm tròn gần đúng.

## Các file trong thư mục

| File | Mô tả |
|---|---|
| `trimfile.py` | Chương trình chính |
| `TrimFile.bat` | Mở chương trình (không hiện cửa sổ console) |
| `build_exe.bat` | Đóng gói thành `.exe` để chạy trên máy Windows khác (kết quả trong `release\TrimFile\`) |
| `HUONG_DAN_BUILD_EXE.md` | Hướng dẫn đóng gói và mang sang máy khác |
| `profiles.json` | Các profile đã lưu (tự tạo lần đầu chạy) |
| `config.json` | Cài đặt nhớ lại: thư mục, hậu tố, âm lượng… (tự tạo, không đưa lên git) |
| `trimfile_error.log` | Nhật ký lỗi nếu chương trình gặp sự cố (tự tạo) |

## Tác giả

Ly Han – Trim file version 1.1

## Lịch sử phiên bản

**1.1**
- Đặt tên file ra cho từng file cắt và cho file Join.
- Cắt copy: hiện điểm bắt đầu thực tế, thêm nút *In → keyframe trước / sau*.
- Sửa cắt copy với nguồn `.wmv/.asf`: audio không còn chạy sớm hơn hình, độ dài file ra đúng.
- Hướng dẫn trong app và README bổ sung cách gõ timecode và cách cắt copy.

**1.0**
- Bản đầu: cắt hàng loạt, Mark In/Out có xem trước và tiếng, timecode `HH:MM:SS:FF`, Duration, profile, container `.wmv`, Join files, nút hướng dẫn.
