# Hướng dẫn đóng gói Trim file thành `.exe` để chạy trên máy Windows khác

Mục tiêu: có một thư mục (hoặc file zip) copy sang máy Windows bất kỳ là **chạy được ngay, không cần cài Python**.

## 1. Tóm tắt nhanh

1. Trên **máy dev** (máy có Python), mở thư mục dự án, bấm đúp **`build_exe.bat`**.
2. Đợi 1–2 phút. Kết quả nằm trong **`release\TrimFile\`**.
3. Copy cả thư mục `TrimFile` (hoặc chạy `build_exe.bat zip` để có `release\TrimFile.zip`) sang máy đích.
4. Trên máy đích, giải nén và bấm đúp **`TrimFile.exe`**.

## 2. Yêu cầu

### Máy build (máy dev)
| Cần | Ghi chú |
|---|---|
| Windows 10/11 64-bit | |
| Python 3.10 trở lên từ [python.org](https://www.python.org/downloads/) | Tick **Add python.exe to PATH**; giữ nguyên mục *tcl/tk and IDLE* (cần cho Tkinter) |
| Internet (lần đầu) | Để tải PyInstaller. Script tự tạo môi trường riêng `.venv-build`, không đụng vào Python hệ thống |
| `ffmpeg.exe`, `ffprobe.exe`, `ffplay.exe` | Đặt **cùng thư mục** với `trimfile.py` (bản build *full* của [gyan.dev](https://www.gyan.dev/ffmpeg/builds/)) |

### Máy đích (máy chạy app)
- Windows 10/11 64-bit. **Không cần cài Python, không cần cài ffmpeg riêng.**

## 3. Kết quả build

```
release\TrimFile\
├── TrimFile.exe        ← chương trình (đã gồm Python + Tkinter)
├── ffmpeg.exe          ← copy từ thư mục dự án
├── ffprobe.exe
├── ffplay.exe          ← dùng để nghe tiếng khi Play
├── profiles.json       ← các profile hiện có (nếu có)
└── README.md
```

Vì sao `ffmpeg.exe` để **ngoài** `TrimFile.exe` mà không nhét vào trong? Ba file ffmpeg nặng khoảng 580 MB; nhét vào bản một-file sẽ làm `TrimFile.exe` rất nặng và mỗi lần mở phải giải nén lại mất nhiều giây. App tự tìm ffmpeg **cùng thư mục với `TrimFile.exe`**, nên chỉ cần giữ chúng cạnh nhau.

## 4. Mang sang máy khác

1. Copy nguyên thư mục `TrimFile` (hoặc file zip) bằng USB / mạng nội bộ. Dung lượng khoảng 600 MB (zip nhỏ hơn).
2. Đặt ở thư mục **có quyền ghi**, ví dụ `D:\TrimFile` hoặc `C:\Users\<tên>\TrimFile`. **Không đặt trong `C:\Program Files`**, vì app cần ghi `profiles.json`, `config.json` cạnh `.exe`.
3. Bấm đúp `TrimFile.exe`. Có thể tạo shortcut ra Desktop.

Mỗi máy có `profiles.json` / `config.json` riêng nằm cạnh `.exe`. Muốn máy mới dùng sẵn các profile của bạn thì copy `profiles.json` đi cùng (script build đã tự copy).

### Lần chạy đầu: cảnh báo của Windows
`TrimFile.exe` chưa được ký số, nên Windows SmartScreen có thể hiện *"Windows protected your PC"*. Bấm **More info → Run anyway**. Nếu file tải qua mạng/zip, có thể phải chuột phải vào file zip → **Properties → tick Unblock** trước khi giải nén.

## 5. Tuỳ chọn trong `build_exe.bat`

Mở file bằng Notepad, chỉnh phần *Cau hinh* ở đầu:

| Muốn | Làm |
|---|---|
| Chạy nhanh hơn lúc mở, ít bị antivirus báo nhầm | Đổi `set "MODE=--onefile"` thành `set "MODE=--onedir"`. Kết quả là thư mục `TrimFile\` có `TrimFile.exe` và thư mục `_internal` đi kèm (phải copy cả hai) |
| Thêm icon cho `.exe` | Đặt file **`app.ico`** vào thư mục dự án, script tự dùng |
| Đổi tên file `.exe` | Sửa `APP_NAME` |
| Có file zip để chuyển | Chạy `build_exe.bat zip` |

Cập nhật phiên bản: sửa `APP_VERSION` ở đầu `trimfile.py` rồi build lại.

## 6. Build thủ công (nếu không dùng `.bat`)

```bash
py -3 -m venv .venv-build
.venv-build\Scripts\python -m pip install --upgrade pip pyinstaller
.venv-build\Scripts\python -m PyInstaller --noconfirm --clean --onefile --windowed --name TrimFile trimfile.py
```

File ra ở `dist\TrimFile.exe`. Sau đó tự copy `ffmpeg.exe`, `ffprobe.exe`, `ffplay.exe` cạnh nó.

## 7. Lỗi thường gặp

| Hiện tượng | Nguyên nhân / cách xử lý |
|---|---|
| `Khong tim thay Python` | Chưa cài Python hoặc chưa vào PATH. Cài lại và tick *Add to PATH*. Nếu gõ `python` ra cửa hàng Microsoft Store thì tắt *App execution aliases* trong Windows Settings |
| `Python nay khong co Tkinter` | Cài lại Python, giữ mục *tcl/tk and IDLE* |
| `Khong cai duoc PyInstaller` | Không có internet hoặc bị chặn proxy. Kiểm tra kết nối rồi chạy lại |
| Mở `TrimFile.exe` hiện *"Thiếu ffmpeg"* | `ffmpeg.exe` và `ffprobe.exe` không nằm cạnh `TrimFile.exe` |
| Mở app không thấy gì / tắt ngay | Xem file `trimfile_error.log` nằm cạnh `.exe` |
| Không có tiếng khi Play | Thiếu `ffplay.exe` cạnh `.exe`, hoặc ô **🔊 Tiếng** đang tắt |
| Antivirus xoá / chặn `TrimFile.exe` | Các file PyInstaller một-file hay bị báo nhầm. Thử chế độ `--onedir`, hoặc thêm thư mục vào danh sách ngoại lệ của antivirus |
| Không lưu được profile | App đang đặt ở thư mục không có quyền ghi (như `Program Files`). Chuyển sang `D:\TrimFile` |

## 8. Lưu ý giấy phép

Bản ffmpeg *full* của gyan.dev được biên dịch theo giấy phép **GPL** (có x264, x265…). Dùng nội bộ thì không sao; nếu định **phân phối** cho người khác, hãy xem điều kiện GPL của ffmpeg tại <https://ffmpeg.org/legal.html>.
