#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
TrimFile - Cắt video hàng loạt bằng ffmpeg.

- Thêm nhiều file, mỗi file đặt Mark In / Mark Out riêng (xem trước ngay trong app).
- Bấm Start: cắt tuần tự từ trên xuống dưới.
- Thông số file thành phẩm chọn bằng dropdown, mỗi mục đều có "Match Source".
  Nếu mọi thứ là Match Source -> ffmpeg chỉ copy stream (cực nhanh, không encode lại).
- Thông số lưu thành Profile (profiles.json cạnh file này).

Chỉ dùng thư viện chuẩn của Python (Tkinter). ffmpeg/ffprobe/ffplay lấy từ cùng thư mục.
"""
import ctypes
import json
import os
import queue
import re
import shutil
import subprocess
import sys
import threading
import time
import traceback
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk

APP_DIR = os.path.dirname(os.path.abspath(sys.executable if getattr(sys, "frozen", False) else __file__))
PROFILES_PATH = os.path.join(APP_DIR, "profiles.json")
CONFIG_PATH = os.path.join(APP_DIR, "config.json")
ERROR_LOG = os.path.join(APP_DIR, "trimfile_error.log")
NO_WINDOW = 0x08000000 if os.name == "nt" else 0


def find_tool(name):
    local = os.path.join(APP_DIR, name + (".exe" if os.name == "nt" else ""))
    if os.path.isfile(local):
        return local
    return shutil.which(name)


FFMPEG = find_tool("ffmpeg")
FFPROBE = find_tool("ffprobe")
FFPLAY = find_tool("ffplay")

# ----------------------------------------------------------------------------
# Tuỳ chọn cho các dropdown
# ----------------------------------------------------------------------------
MATCH = "Match Source"
NO_AUDIO = "Không có audio"
DEFAULT_PRESET = "Mặc định"

# (label, encoder, là hardware?)
VIDEO_CODECS = [
    ("H.264 (x264)", "libx264", False),
    ("H.265 / HEVC (x265)", "libx265", False),
    ("VP9", "libvpx-vp9", False),
    ("AV1 (SVT-AV1)", "libsvtav1", False),
    ("MPEG-4", "mpeg4", False),
    ("WMV2 (Windows Media Video)", "wmv2", False),
    ("WMV1", "wmv1", False),
    ("ProRes", "prores_ks", False),
    ("H.264 - NVIDIA NVENC", "h264_nvenc", True),
    ("H.265 - NVIDIA NVENC", "hevc_nvenc", True),
    ("AV1 - NVIDIA NVENC", "av1_nvenc", True),
    ("H.264 - Intel QSV", "h264_qsv", True),
    ("H.265 - Intel QSV", "hevc_qsv", True),
    ("H.264 - AMD AMF", "h264_amf", True),
    ("H.265 - AMD AMF", "hevc_amf", True),
]
ENC_BY_LABEL = {l: e for l, e, _ in VIDEO_CODECS}

SIZES = [MATCH, "3840x2160 (4K)", "2560x1440 (2K)", "1920x1080 (Full HD)", "1280x720 (HD)",
         "960x540", "854x480 (480p)", "640x360 (360p)", "426x240 (240p)"]
BITRATES = [MATCH, "CRF 18 (chất lượng cao)", "CRF 23 (cân bằng)", "CRF 28 (nhỏ gọn)",
            "1 Mbps", "2 Mbps", "3 Mbps", "4 Mbps", "6 Mbps", "8 Mbps", "10 Mbps",
            "15 Mbps", "20 Mbps", "30 Mbps", "50 Mbps"]
FPS_LIST = [MATCH, "23.976", "24", "25", "29.97", "30", "50", "59.94", "60"]
PRESET_NAMES = ["ultrafast", "superfast", "veryfast", "faster", "fast", "medium", "slow", "slower", "veryslow"]
PRESETS = [DEFAULT_PRESET] + PRESET_NAMES
PIXFMTS = [MATCH, "yuv420p (8-bit)", "yuv420p10le (10-bit)", "yuv422p (4:2:2)",
           "yuv422p10le (4:2:2 10-bit)", "yuv444p (4:4:4)"]

AUDIO_CODECS = [
    (MATCH, None), ("AAC", "aac"), ("MP3", "libmp3lame"), ("Opus", "libopus"), ("AC3", "ac3"),
    ("Vorbis", "libvorbis"), ("WMA (Windows Media Audio)", "wmav2"), ("FLAC", "flac"), ("PCM 16-bit", "pcm_s16le"), (NO_AUDIO, "none"),
]
ACODEC_BY_LABEL = dict(AUDIO_CODECS)
ABITRATES = [MATCH, "64k", "96k", "128k", "160k", "192k", "256k", "320k"]
SAMPLE_RATES = [MATCH, "22050", "32000", "44100", "48000"]
CHANNELS = [MATCH, "Mono (1)", "Stereo (2)", "5.1 (6)"]
CONTAINERS = [MATCH, "mp4", "mkv", "mov", "avi", "wmv", "webm", "ts"]
KNOWN_CONT = {"mp4", "m4v", "mov", "mkv", "avi", "wmv", "webm", "ts"}

SETTING_KEYS = ["vcodec", "size", "bitrate", "fps", "preset", "pixfmt",
                "acodec", "abitrate", "asr", "ach", "container", "accurate"]
DEFAULT_SETTINGS = {
    "vcodec": MATCH, "size": MATCH, "bitrate": MATCH, "fps": MATCH, "preset": DEFAULT_PRESET,
    "pixfmt": MATCH, "acodec": MATCH, "abitrate": MATCH, "asr": MATCH, "ach": MATCH,
    "container": MATCH, "accurate": False,
}


def _prof(**kw):
    d = dict(DEFAULT_SETTINGS)
    d.update(kw)
    return d


BUILTIN_PROFILES = {
    "Match Source - cắt nhanh (copy)": _prof(),
    "Match Source - cắt chính xác frame": _prof(accurate=True),
    "H.264 1080p 8 Mbps (MP4)": _prof(vcodec="H.264 (x264)", size="1920x1080 (Full HD)", bitrate="8 Mbps",
                                      preset="medium", pixfmt="yuv420p (8-bit)",
                                      acodec="AAC", abitrate="192k", container="mp4"),
    "H.264 720p 4 Mbps (MP4)": _prof(vcodec="H.264 (x264)", size="1280x720 (HD)", bitrate="4 Mbps",
                                     preset="medium", pixfmt="yuv420p (8-bit)",
                                     acodec="AAC", abitrate="128k", container="mp4"),
    "Nhỏ gọn H.264 480p CRF 28": _prof(vcodec="H.264 (x264)", size="854x480 (480p)", bitrate="CRF 28 (nhỏ gọn)",
                                       preset="veryfast", pixfmt="yuv420p (8-bit)",
                                       acodec="AAC", abitrate="96k", container="mp4"),
}

# Quan hệ codec <-> container
CONTAINER_V = {
    "mp4": {"h264", "hevc", "vp9", "av1", "mpeg4", "mpeg2video"},
    "m4v": {"h264", "hevc", "mpeg4"},
    "mov": {"h264", "hevc", "av1", "prores", "mpeg4", "mpeg2video", "mjpeg"},
    "mkv": None,
    "avi": {"h264", "mpeg4", "mpeg2video", "mjpeg"},
    "webm": {"vp8", "vp9", "av1"},
    "wmv": {"wmv1", "wmv2", "wmv3", "vc1", "msmpeg4v3"},
    "ts": {"h264", "hevc", "mpeg2video", "av1"},
}
CONTAINER_A = {
    "mp4": {"aac", "mp3", "ac3", "eac3", "alac", "opus", "flac"},
    "m4v": {"aac", "mp3", "ac3", "eac3"},
    "mov": {"aac", "mp3", "ac3", "alac", "pcm_s16le", "pcm_s24le", "pcm_s16be", "flac"},
    "mkv": None,
    "avi": {"mp3", "ac3", "pcm_s16le", "mp2"},
    "webm": {"opus", "vorbis"},
    "wmv": {"wmav1", "wmav2", "wmapro", "wmavoice", "mp3"},
    "ts": {"aac", "mp3", "ac3", "eac3", "mp2", "opus"},
}
EQUIV_V = {"h264": "libx264", "hevc": "libx265", "vp9": "libvpx-vp9", "vp8": "libvpx", "av1": "libsvtav1",
           "mpeg4": "mpeg4", "mpeg2video": "mpeg2video", "prores": "prores_ks",
           "wmv1": "wmv1", "wmv2": "wmv2", "wmv3": "wmv2", "vc1": "wmv2", "msmpeg4v3": "msmpeg4v3"}
EQUIV_A = {"aac": "aac", "mp3": "libmp3lame", "opus": "libopus", "ac3": "ac3", "eac3": "eac3",
           "vorbis": "libvorbis", "flac": "flac", "mp2": "mp2", "pcm_s16le": "pcm_s16le",
           "wmav1": "wmav1", "wmav2": "wmav2", "wmapro": "wmav2", "wmavoice": "wmav2"}
ENC_FAMILY_A = {"aac": "aac", "libmp3lame": "mp3", "libopus": "opus", "ac3": "ac3", "libvorbis": "vorbis",
                "flac": "flac", "pcm_s16le": "pcm_s16le", "mp2": "mp2", "eac3": "eac3"}

VIDEO_EXTS = (".mp4", ".mov", ".mkv", ".avi", ".webm", ".ts", ".mts", ".m2ts", ".mpg", ".mpeg",
              ".wmv", ".flv", ".m4v", ".mxf", ".3gp", ".vob", ".mpv")


# ----------------------------------------------------------------------------
# Hàm tiện ích
# ----------------------------------------------------------------------------
TC_FPS = 25  # timecode dạng HH:MM:SS:FF, 1 giây = 25 frame


def fmt_tc(t):
    """giây -> HH:MM:SS:FF (FF = 00..24)."""
    if t is None:
        return ""
    sec, ff = divmod(int(round(max(0.0, t) * TC_FPS)), TC_FPS)
    h, rem = divmod(sec, 3600)
    m, sec = divmod(rem, 60)
    return f"{h:02d}:{m:02d}:{sec:02d}:{ff:02d}"


def parse_tc(text):
    """'HH:MM:SS:FF' (có thể gõ ngắn, tính từ phải sang: FF, SS, MM, HH) -> giây.
    Không có dấu ':' thì hiểu là số giây ('90' hoặc '12.5'). Sai định dạng -> None."""
    text = (text or "").strip().replace(";", ":").replace(",", ".")
    if not text:
        return None
    try:
        if ":" not in text:
            v = float(text)
            return v if v >= 0 else None
        parts = [float(p) for p in text.split(":")]
    except ValueError:
        return None
    if len(parts) > 4 or any(p < 0 for p in parts):
        return None
    return sum(v * m for v, m in zip(reversed(parts), (1 / TC_FPS, 1, 60, 3600)))


def parse_rate(text):
    try:
        if not text or text in ("0/0", "N/A"):
            return None
        if "/" in text:
            a, b = text.split("/")
            return float(a) / float(b) if float(b) else None
        return float(text)
    except ValueError:
        return None


def parse_size(label):
    m = re.search(r"(\d+)\s*[x×]\s*(\d+)", label or "")
    return (int(m.group(1)), int(m.group(2))) if m else None


def parse_fps(label):
    try:
        v = float(label)
    except (TypeError, ValueError):
        return None
    if v <= 0:
        return None
    for n in (24, 30, 60):
        if abs(v - n * 1000 / 1001) < 0.01:
            return f"{n * 1000}/1001"
    return repr(v).rstrip("0").rstrip(".") if "." in repr(v) else str(int(v))


def parse_bitrate(label):
    """-> ('match',) | ('crf', n) | ('bps', int) | None nếu sai."""
    label = (label or "").strip()
    if label == MATCH:
        return ("match",)
    m = re.match(r"(?i)^crf\s*(\d+)", label)
    if m:
        return ("crf", int(m.group(1)))
    m = re.match(r"(?i)^(\d+(?:[.,]\d+)?)\s*(k|kbps|m|mbps)?\s*$", label)
    if not m:
        return None
    val = float(m.group(1).replace(",", "."))
    unit = (m.group(2) or "k").lower()
    return ("bps", int(val * (1_000_000 if unit.startswith("m") else 1000)))


def fmt_bps(bps):
    if not bps:
        return "?"
    return f"{bps / 1e6:.1f} Mbps" if bps >= 1e6 else f"{bps / 1e3:.0f} kbps"


def enc_family(enc):
    table = {"libx264": "h264", "libx265": "hevc", "libvpx-vp9": "vp9", "libvpx": "vp8",
             "libsvtav1": "av1", "mpeg4": "mpeg4", "prores_ks": "prores", "mpeg2video": "mpeg2video"}
    if enc in table:
        return table[enc]
    for fam in ("h264", "hevc", "av1"):
        if enc.startswith(fam):
            return fam
    return enc


def ext_of(path):
    return os.path.splitext(path)[1].lower().lstrip(".")


def resolve_container(S, src_path):
    c = S["container"]
    if c != MATCH:
        return c
    e = ext_of(src_path)
    return e if e in KNOWN_CONT else "mkv"


def run_quiet(cmd, **kw):
    return subprocess.run(cmd, stdin=subprocess.DEVNULL, creationflags=NO_WINDOW, **kw)


def probe_file(path):
    """Đọc thông tin file bằng ffprobe -> dict. Ném Exception nếu lỗi."""
    r = run_quiet([FFPROBE, "-v", "error", "-print_format", "json", "-show_format", "-show_streams", path],
                  capture_output=True, timeout=120)
    if r.returncode != 0:
        raise RuntimeError(r.stderr.decode("utf-8", "replace").strip() or "ffprobe lỗi")
    data = json.loads(r.stdout.decode("utf-8", "replace"))
    fmt = data.get("format", {})
    dur = float(fmt.get("duration") or 0)
    v = a = None
    for s in data.get("streams", []):
        kind = s.get("codec_type")
        if kind == "video" and v is None and not s.get("disposition", {}).get("attached_pic"):
            w, h = int(s.get("width") or 0), int(s.get("height") or 0)
            rot = 0
            for sd in s.get("side_data_list") or []:
                if "rotation" in sd:
                    rot = int(float(sd["rotation"]))
            if not rot:
                try:
                    rot = int(s.get("tags", {}).get("rotate", 0) or 0)
                except ValueError:
                    rot = 0
            if abs(rot) % 180 == 90:
                w, h = h, w
            v = {"codec": s.get("codec_name"), "w": w, "h": h,
                 "fps": parse_rate(s.get("avg_frame_rate")) or parse_rate(s.get("r_frame_rate")),
                 "br": int(s["bit_rate"]) if s.get("bit_rate") else None, "pix": s.get("pix_fmt")}
            if not dur and s.get("duration"):
                dur = float(s["duration"])
        elif kind == "audio" and a is None:
            a = {"codec": s.get("codec_name"), "sr": int(s.get("sample_rate") or 0),
                 "ch": s.get("channels"), "br": int(s["bit_rate"]) if s.get("bit_rate") else None}
    fbr = int(fmt["bit_rate"]) if fmt.get("bit_rate") else None
    if v and not v["br"] and fbr:
        v["br"] = max(fbr - ((a or {}).get("br") or 0), 0) or None
    if not v and not a:
        raise RuntimeError("Không tìm thấy luồng video/audio")
    if dur <= 0:
        raise RuntimeError("Không xác định được thời lượng")
    return {"duration": dur, "v": v, "a": a}


def describe_info(info):
    parts = []
    v, a = info.get("v"), info.get("a")
    if v:
        fps = f"{v['fps']:.3f}".rstrip("0").rstrip(".") if v["fps"] else "?"
        parts.append(f"{v['codec']} {v['w']}x{v['h']} {fps}fps {fmt_bps(v['br'])}")
    if a:
        ch = {1: "mono", 2: "stereo"}.get(a["ch"], f"{a['ch']}ch")
        parts.append(f"{a['codec']} {a['sr']}Hz {ch} {fmt_bps(a['br'])}")
    return "   |   ".join(parts)


# ----------------------------------------------------------------------------
# Dựng lệnh ffmpeg
# ----------------------------------------------------------------------------
def preset_args(enc, label):
    if label == DEFAULT_PRESET or label not in PRESET_NAMES:
        return []
    i = PRESET_NAMES.index(label)
    if enc in ("libx264", "libx265"):
        return ["-preset", label]
    if enc.endswith("_nvenc"):
        return ["-preset", ["p1", "p1", "p2", "p3", "p3", "p4", "p5", "p6", "p7"][i]]
    if enc.endswith("_qsv"):
        return ["-preset", "veryfast" if i < 2 else label]
    if enc.endswith("_amf"):
        return ["-quality", "speed" if i <= 3 else "balanced" if i <= 5 else "quality"]
    if enc == "libsvtav1":
        return ["-preset", str([12, 11, 10, 9, 8, 6, 5, 4, 2][i])]
    if enc == "libvpx-vp9":
        return ["-deadline", "good", "-cpu-used", str([5, 5, 4, 3, 2, 2, 1, 1, 0][i])]
    return []


def quality_args(enc, spec, src_bps):
    """spec: kết quả parse_bitrate. src_bps: bitrate gốc (cho Match Source)."""
    if enc == "prores_ks":
        return []
    if spec[0] == "match":
        spec = ("bps", src_bps) if src_bps else ("crf", 23)
    if spec[0] == "bps":
        return ["-b:v", str(spec[1])]
    q = spec[1]
    if enc in ("libx264", "libx265", "libsvtav1"):
        return ["-crf", str(q)]
    if enc in ("libvpx-vp9", "libvpx"):
        return ["-crf", str(q), "-b:v", "0"]
    if enc.endswith("_nvenc"):
        return ["-rc", "vbr", "-cq", str(q), "-b:v", "0"]
    if enc.endswith("_qsv"):
        return ["-global_quality", str(q)]
    if enc.endswith("_amf"):
        return ["-rc", "cqp", "-qp_i", str(q), "-qp_p", str(q), "-qp_b", str(q)]
    return ["-q:v", str(max(2, min(31, q // 3)))]


def validate_settings(S):
    """Kiểm tra các giá trị gõ tay. Trả về chuỗi lỗi hoặc None."""
    if S["size"] != MATCH and not parse_size(S["size"]):
        return f"Video size '{S['size']}' không hợp lệ. Dùng dạng 1920x1080."
    if S["fps"] != MATCH and not parse_fps(S["fps"]):
        return f"Frame rate '{S['fps']}' không hợp lệ."
    if parse_bitrate(S["bitrate"]) is None:
        return f"Bitrate '{S['bitrate']}' không hợp lệ. Ví dụ: 8 Mbps, 5000k, CRF 23."
    if S["abitrate"] != MATCH and not re.match(r"(?i)^\d+\s*k?(bps)?$", S["abitrate"].strip()):
        return f"Audio bitrate '{S['abitrate']}' không hợp lệ. Ví dụ: 192k."
    if S["asr"] != MATCH and not S["asr"].strip().isdigit():
        return f"Sample rate '{S['asr']}' không hợp lệ."
    cont = S["container"] if S["container"] != MATCH else None
    enc = ENC_BY_LABEL.get(S["vcodec"])
    if enc and cont and CONTAINER_V.get(cont) is not None and enc_family(enc) not in CONTAINER_V[cont]:
        return f"Video codec '{S['vcodec']}' không dùng được với container .{cont}."
    aenc = ACODEC_BY_LABEL.get(S["acodec"])
    if aenc and aenc != "none" and cont and CONTAINER_A.get(cont) is not None \
            and ENC_FAMILY_A.get(aenc, aenc) not in CONTAINER_A[cont]:
        return f"Audio codec '{S['acodec']}' không dùng được với container .{cont}."
    return None


def describe_plan(S):
    """Mô tả ngắn gọn chế độ xử lý (hiển thị dưới bảng thông số)."""
    reenc = (S["vcodec"] != MATCH or S["size"] != MATCH or S["fps"] != MATCH or S["bitrate"] != MATCH
             or S["pixfmt"] != MATCH or S["accurate"])
    areenc = S["acodec"] not in (MATCH, NO_AUDIO) or S["abitrate"] != MATCH or S["asr"] != MATCH or S["ach"] != MATCH
    if not reenc and not areenc:
        return "⚡ Chế độ COPY: không encode lại, rất nhanh. Điểm cắt có thể lệch về keyframe gần nhất."
    v = "encode lại video" if reenc else "copy video"
    a = "encode lại audio" if areenc else ("bỏ audio" if S["acodec"] == NO_AUDIO else "copy audio")
    extra = " (cắt chính xác từng frame)" if reenc else ""
    return f"🔁 {v.capitalize()}, {a}{extra}. Chậm hơn chế độ copy."


def build_command(info, src_path, out_path, start, end, S):
    """Tạo lệnh ffmpeg cho 1 job. Trả về (cmd, mô_tả)."""
    v, a = info["v"], info["a"]
    cont = ext_of(out_path)
    cv, ca = CONTAINER_V.get(cont), CONTAINER_A.get(cont)

    cmd = [FFMPEG, "-hide_banner", "-nostdin", "-y", "-v", "error", "-progress", "pipe:1", "-nostats"]
    if start and start > 0:
        cmd += ["-ss", f"{start:.3f}"]
    cmd += ["-i", src_path]
    if end is not None:
        cmd += ["-t", f"{end - (start or 0):.3f}"]
    cmd += ["-map", "0:v:0?", "-map", "0:a?", "-sn", "-dn", "-map_metadata", "0", "-map_chapters", "-1"]
    notes = []
    video_reencoded = False

    # ---------------- Video ----------------
    if v:
        enc_name = ENC_BY_LABEL.get(S["vcodec"])
        size, fps = parse_size(S["size"]), parse_fps(S["fps"])
        spec = parse_bitrate(S["bitrate"])
        pix = S["pixfmt"].split()[0] if S["pixfmt"] != MATCH else None
        filters = []
        if size:
            W, H = size
            if v["h"] > v["w"] and W > H:      # video dọc -> đổi chiều khung đích
                W, H = H, W
            filters.append(f"scale={W}:{H}:force_original_aspect_ratio=decrease:force_divisible_by=2")
        if fps:
            filters.append(f"fps={fps}")
        reencode = bool(enc_name or filters or spec[0] != "match" or pix or S["accurate"])
        if not reencode and cv is not None and v["codec"] not in cv:
            reencode = True
            notes.append(f"codec {v['codec']} không copy được vào .{cont}, encode lại")
        video_reencoded = reencode
        if reencode:
            if enc_name:
                enc = enc_name
            else:
                enc = EQUIV_V.get(v["codec"], "libx264")
                if cv is not None and enc_family(enc) not in cv:
                    enc = "libvpx-vp9" if cont == "webm" else "wmv2" if cont == "wmv" else "libx264"
            cmd += ["-c:v", enc] + quality_args(enc, spec, v["br"]) + preset_args(enc, S["preset"])
            if filters:
                cmd += ["-vf", ",".join(filters)]
            if pix:
                cmd += ["-pix_fmt", pix]
            if enc_family(enc) == "hevc" and cont in ("mp4", "m4v", "mov"):
                cmd += ["-tag:v", "hvc1"]
            notes.append(f"video: {enc}")
        else:
            cmd += ["-c:v", "copy", "-avoid_negative_ts", "make_zero"]
            if v["codec"] == "hevc" and cont in ("mp4", "m4v", "mov"):
                cmd += ["-tag:v", "hvc1"]
            notes.append("video: copy")

    # ---------------- Audio ----------------
    if a:
        aenc = ACODEC_BY_LABEL.get(S["acodec"])
        if aenc == "none":
            cmd += ["-an"]
            notes.append("audio: bỏ")
        else:
            abr = S["abitrate"].strip()
            asr = S["asr"].strip()
            ach = re.search(r"\((\d+)\)", S["ach"]) if S["ach"] != MATCH else None
            params = abr != MATCH or asr != MATCH or ach is not None
            copy_ok = ca is None or a["codec"] in ca
            # Nguồn ASF/WMV: nếu video encode lại mà audio copy thì audio bắt đầu từ keyframe -> lệch tiếng/hình
            if video_reencoded and ext_of(src_path) in ("wmv", "asf"):
                copy_ok = False
            if aenc is None and not params and copy_ok:
                cmd += ["-c:a", "copy"]
                notes.append("audio: copy")
            else:
                if aenc:
                    enc = aenc
                else:
                    enc = EQUIV_A.get(a["codec"], "aac")
                    if ca is not None and ENC_FAMILY_A.get(enc, enc) not in ca:
                        enc = "libopus" if cont == "webm" else "libmp3lame" if cont == "avi" else "wmav2" if cont == "wmv" else "aac"
                cmd += ["-c:a", enc]
                if not enc.startswith("pcm") and enc != "flac":
                    if abr != MATCH:
                        cmd += ["-b:a", abr if abr.lower().endswith("k") else abr + "k"]
                    elif a["br"]:
                        cmd += ["-b:a", str(a["br"])]
                    else:
                        cmd += ["-b:a", "192k"]
                if asr != MATCH:
                    cmd += ["-ar", asr]
                if ach:
                    cmd += ["-ac", ach.group(1)]
                notes.append(f"audio: {enc}")

    if cont in ("mp4", "m4v", "mov"):
        cmd += ["-movflags", "+faststart"]
    if cont == "m4v":
        cmd += ["-f", "mp4"]
    cmd += [out_path]
    return cmd, ", ".join(notes)


def unique_path(folder, stem, suffix, ext):
    p = os.path.join(folder, f"{stem}{suffix}.{ext}")
    n = 2
    while os.path.exists(p):
        p = os.path.join(folder, f"{stem}{suffix}_{n}.{ext}")
        n += 1
    return p


# ----------------------------------------------------------------------------
# Timeline (thanh tua có vùng In/Out)
# ----------------------------------------------------------------------------
class Timeline(tk.Canvas):
    PAD = 12

    def __init__(self, master, app, height=44):
        super().__init__(master, height=height, highlightthickness=0, bg="#f3f4f6", cursor="hand2")
        self.app = app
        self.dur = 0.0
        self.pos = 0.0
        self.tin = None
        self.tout = None
        self.drag = None
        self.bind("<Configure>", lambda e: self.redraw())
        self.bind("<ButtonPress-1>", self._press)
        self.bind("<B1-Motion>", self._motion)
        self.bind("<ButtonRelease-1>", self._release)

    def set_state(self, dur=None, pos=None, tin="keep", tout="keep"):
        if dur is not None:
            self.dur = dur
        if pos is not None:
            self.pos = pos
        if tin != "keep":
            self.tin = tin
        if tout != "keep":
            self.tout = tout
        self.redraw()

    def _x(self, t):
        w = max(self.winfo_width(), 2 * self.PAD + 1)
        return self.PAD + (t / self.dur if self.dur > 0 else 0) * (w - 2 * self.PAD)

    def _t(self, x):
        w = max(self.winfo_width(), 2 * self.PAD + 1)
        return min(max((x - self.PAD) / (w - 2 * self.PAD), 0.0), 1.0) * self.dur

    def redraw(self):
        self.delete("all")
        w, h = max(self.winfo_width(), 2), self.winfo_height()
        ty = h - 16
        self.create_rectangle(self.PAD, ty, w - self.PAD, ty + 8, fill="#cfd4da", outline="")
        if self.dur <= 0:
            return
        a = self._x(self.tin) if self.tin is not None else self.PAD
        b = self._x(self.tout) if self.tout is not None else w - self.PAD
        if self.tin is not None or self.tout is not None:
            self.create_rectangle(a, ty, b, ty + 8, fill="#4f9cf9", outline="")
        if self.tin is not None:
            self.create_line(a, 4, a, ty + 12, fill="#1a7f37", width=3)
            self.create_polygon(a, 4, a + 9, 4, a, 14, fill="#1a7f37", outline="")
        if self.tout is not None:
            self.create_line(b, 4, b, ty + 12, fill="#b54708", width=3)
            self.create_polygon(b, 4, b - 9, 4, b, 14, fill="#b54708", outline="")
        p = self._x(self.pos)
        self.create_line(p, 2, p, h - 2, fill="#e5484d", width=2)
        self.create_polygon(p - 5, 2, p + 5, 2, p, 10, fill="#e5484d", outline="")

    def _press(self, e):
        if self.dur <= 0:
            return
        self.focus_set()
        if self.tin is not None and abs(e.x - self._x(self.tin)) <= 7:
            self.drag = "in"
        elif self.tout is not None and abs(e.x - self._x(self.tout)) <= 7:
            self.drag = "out"
        else:
            self.drag = "seek"
        self._motion(e, fast=True)

    def _motion(self, e, fast=True):
        if not self.drag:
            return
        t = self._t(e.x)
        if self.drag == "in":
            self.app.set_in(t)
        elif self.drag == "out":
            self.app.set_out(t)
        self.app.seek(t, fast=fast)

    def _release(self, e):
        if not self.drag:
            return
        t = self._t(e.x)
        self.app.seek(self.app.pos if self.drag != "seek" else t, fast=False)
        self.drag = None


# ----------------------------------------------------------------------------
# Item trong danh sách
# ----------------------------------------------------------------------------
class Item:
    def __init__(self, path):
        self.path = path
        self.name = os.path.basename(path)
        self.info = None
        self.tin = None
        self.tout = None
        self.state = "probing"    # probing | ready | running | done | error | stopped
        self.status = "Đang đọc…"
        self.out_path = None

    def clip_range(self):
        dur = self.info["duration"] if self.info else 0
        start = self.tin or 0.0
        end = self.tout if self.tout is not None else dur
        return start, end


# ----------------------------------------------------------------------------
# Ứng dụng
# ----------------------------------------------------------------------------
PREVIEW_FPS = 15


class App:
    def __init__(self, root):
        self.root = root
        root.title("TrimFile – Cắt video hàng loạt bằng ffmpeg")
        self.sf = max(root.winfo_fpixels("1i") / 96.0, 1.0)
        root.geometry(f"{self.px(1280)}x{self.px(880)}")
        root.minsize(self.px(1100), self.px(740))
        style = ttk.Style()
        for th in ("vista", "clam"):
            if th in style.theme_names():
                style.theme_use(th)
                break
        style.configure("Accent.TButton", font=("Segoe UI", 10, "bold"))
        style.configure("Hint.TLabel", foreground="#555")

        self.q = queue.Queue()
        self.items = {}            # iid -> Item
        self.counter = 0
        self.cur = None
        self.cur_iid = None
        self.pos = 0.0
        self.photo = None

        self.still_gen = 0
        self.still_proc = None
        self.seek_after = None
        self.pending_seek = None
        self.resize_after = None

        self.playing = False
        self.play_gen = 0
        self.play_proc = None
        self.play_t0 = 0.0
        self.play_until = None
        self.play_q = queue.Queue()
        self.play_clock = None
        self.play_pending = None
        self.audio_proc = None

        self.running = False
        self.stop_flag = threading.Event()
        self.job_proc = None
        self.last_out_dir = None

        self.profiles = {}
        self.config = {}
        self.vars = {}
        self._loading = False
        self.modified = False

        self.encoders_text = ""
        self.hw_ok = []

        self._load_config()
        self._load_profiles()
        self._detect_encoders()
        self._build_ui()
        self._apply_profile(self.config.get("last_profile") if self.config.get("last_profile") in self.profiles
                            else next(iter(self.profiles)))
        self._bind_keys()
        root.protocol("WM_DELETE_WINDOW", self.on_close)
        root.after(15, self._poll)
        threading.Thread(target=self._hw_probe_worker, daemon=True).start()

    def px(self, n):
        return int(n * self.sf)

    # ------------------------------------------------------------------ cấu hình
    def _load_config(self):
        try:
            with open(CONFIG_PATH, encoding="utf-8") as f:
                self.config = json.load(f)
        except (OSError, ValueError):
            self.config = {}

    def _save_config(self):
        self.config.update({
            "last_profile": self.profile_var.get(),
            "same_dir": self.same_dir_var.get(),
            "out_dir": self.out_dir_var.get(),
            "suffix": self.suffix_var.get(),
            "add_dir": self.config.get("add_dir", ""),
            "audio_on": self.audio_on.get(),
            "volume": round(self.volume.get()),
        })
        try:
            with open(CONFIG_PATH, "w", encoding="utf-8") as f:
                json.dump(self.config, f, ensure_ascii=False, indent=2)
        except OSError:
            pass

    def _load_profiles(self):
        try:
            with open(PROFILES_PATH, encoding="utf-8") as f:
                data = json.load(f)
            self.profiles = data.get("profiles", {})
        except (OSError, ValueError):
            self.profiles = {}
        if not self.profiles:
            self.profiles = {k: dict(v) for k, v in BUILTIN_PROFILES.items()}
            self._save_profiles()

    def _save_profiles(self):
        try:
            with open(PROFILES_PATH, "w", encoding="utf-8") as f:
                json.dump({"profiles": self.profiles}, f, ensure_ascii=False, indent=2)
        except OSError as e:
            messagebox.showerror("Lỗi", f"Không lưu được profiles.json:\n{e}")

    def _detect_encoders(self):
        try:
            r = run_quiet([FFMPEG, "-hide_banner", "-encoders"], capture_output=True, timeout=30)
            self.encoders_text = r.stdout.decode("utf-8", "replace")
        except Exception:
            self.encoders_text = ""
        names = set()
        for line in self.encoders_text.splitlines():
            parts = line.split()
            if len(parts) >= 2 and parts[0].startswith(("V", "A")):
                names.add(parts[1])
        self.sw_codecs = [l for l, e, hw in VIDEO_CODECS if not hw and (e in names or not names)]
        self.hw_candidates = [e for l, e, hw in VIDEO_CODECS if hw and e in names]

    def _hw_probe_worker(self):
        ok = []
        for enc in self.hw_candidates:
            try:
                r = run_quiet([FFMPEG, "-hide_banner", "-v", "error", "-f", "lavfi", "-i",
                               "color=c=black:s=320x240:r=10:d=0.5", "-frames:v", "2", "-c:v", enc,
                               "-f", "null", "-"], capture_output=True, timeout=25)
                if r.returncode == 0:
                    ok.append(enc)
            except Exception:
                pass
        self.q.put(("hw", ok))

    def _vcodec_values(self):
        hw = [l for l, e, h in VIDEO_CODECS if h and e in self.hw_ok]
        return [MATCH] + self.sw_codecs + hw

    # ------------------------------------------------------------------ giao diện
    def _build_ui(self):
        root = self.root
        root.columnconfigure(0, weight=1)
        root.rowconfigure(2, weight=1)

        # --- thanh công cụ
        bar = ttk.Frame(root, padding=(8, 8, 8, 2))
        bar.grid(row=0, column=0, sticky="ew")
        self.list_buttons = []
        for text, cmd in (("➕ Thêm file…", self.add_files), ("📁 Thêm thư mục…", self.add_folder),
                          ("➖ Xoá", self.remove_selected), ("🗑 Xoá hết", self.clear_all),
                          ("▲ Lên", lambda: self.move(-1)), ("▼ Xuống", lambda: self.move(1)),
                          ("⧉ Nhân đôi", self.duplicate), ("↺ Đặt lại trạng thái", self.reset_status)):
            b = ttk.Button(bar, text=text, command=cmd)
            b.pack(side="left", padx=2)
            self.list_buttons.append(b)

        # --- danh sách
        lf = ttk.Frame(root, padding=(8, 2))
        lf.grid(row=1, column=0, sticky="ew")
        lf.columnconfigure(0, weight=1)
        cols = ("no", "name", "dur", "tin", "tout", "len", "status")
        self.tree = ttk.Treeview(lf, columns=cols, show="headings", height=7, selectmode="extended")
        heads = (("no", "#", 36, "center"), ("name", "Tên file", 380, "w"), ("dur", "Thời lượng", 100, "center"),
                 ("tin", "Mark In", 105, "center"), ("tout", "Mark Out", 105, "center"),
                 ("len", "Độ dài clip", 105, "center"), ("status", "Trạng thái", 240, "w"))
        for c, t, w, anc in heads:
            self.tree.heading(c, text=t)
            self.tree.column(c, width=self.px(w), anchor=anc, stretch=(c == "name"))
        sb = ttk.Scrollbar(lf, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)
        self.tree.grid(row=0, column=0, sticky="ew")
        sb.grid(row=0, column=1, sticky="ns")
        self.tree.tag_configure("done", foreground="#1a7f37")
        self.tree.tag_configure("error", foreground="#cf222e")
        self.tree.tag_configure("running", foreground="#0969da")
        self.tree.bind("<<TreeviewSelect>>", self.on_select)
        self.tree.bind("<Delete>", lambda e: self.remove_selected())
        self.tree.bind("<space>", lambda e: (self.toggle_play(), "break")[1])

        # --- giữa: preview + thông số
        mid = ttk.Frame(root, padding=(8, 4))
        mid.grid(row=2, column=0, sticky="nsew")
        mid.columnconfigure(0, weight=1)
        mid.rowconfigure(0, weight=1)
        self._build_preview(mid)
        self._build_settings(mid)

        # --- đầu ra + Start
        self._build_output(root)

    def _build_preview(self, parent):
        pf = ttk.LabelFrame(parent, text=" Xem trước & Mark In / Mark Out ", padding=6)
        pf.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        pf.columnconfigure(0, weight=1)
        pf.rowconfigure(0, weight=1)

        self.canvas = tk.Canvas(pf, bg="black", highlightthickness=0, width=self.px(560), height=self.px(300))
        self.canvas.grid(row=0, column=0, sticky="nsew")
        self.img_id = self.canvas.create_image(0, 0, anchor="center")
        self.msg_id = self.canvas.create_text(0, 0, fill="#aaa", font=("Segoe UI", 11),
                                              text="Chọn một file trong danh sách để xem trước")
        self.canvas.bind("<Configure>", self._on_canvas_resize)
        self.canvas.bind("<Button-1>", lambda e: (self.canvas.focus_set(), self.toggle_play()))

        self.info_var = tk.StringVar(value="")
        ttk.Label(pf, textvariable=self.info_var, style="Hint.TLabel").grid(row=1, column=0, sticky="w", pady=(4, 0))

        self.timeline = Timeline(pf, self, height=self.px(44))
        self.timeline.grid(row=2, column=0, sticky="ew", pady=(2, 0))

        ctl = ttk.Frame(pf)
        ctl.grid(row=3, column=0, sticky="ew", pady=(4, 0))
        self.play_btn = ttk.Button(ctl, text="▶ Play", width=9, command=self.toggle_play)
        self.play_btn.pack(side="left", padx=2)
        for text, fn in (("◀ 1f", lambda: self.step(-1)), ("1f ▶", lambda: self.step(1)),
                         ("◀◀ 1s", lambda: self.jump(-1)), ("1s ▶▶", lambda: self.jump(1))):
            ttk.Button(ctl, text=text, width=7, command=fn).pack(side="left", padx=2)
        self.time_var = tk.StringVar(value="00:00:00:00 / 00:00:00:00")
        ttk.Label(ctl, textvariable=self.time_var, font=("Consolas", 11)).pack(side="left", padx=12)
        self.audio_on = tk.BooleanVar(value=self.config.get("audio_on", True))
        self.volume = tk.DoubleVar(value=self.config.get("volume", 80))
        if FFPLAY:
            vol = ttk.Scale(ctl, from_=0, to=100, variable=self.volume, length=self.px(90))
            vol.pack(side="right", padx=(2, 6))
            vol.bind("<ButtonRelease-1>", lambda e: self._audio_changed())
            ttk.Checkbutton(ctl, text="🔊 Tiếng", variable=self.audio_on,
                            command=self._audio_changed).pack(side="right", padx=2)

        mark = ttk.Frame(pf)
        mark.grid(row=4, column=0, sticky="ew", pady=(6, 0))
        ttk.Button(mark, text="[ Mark In (I)", command=self.mark_in).pack(side="left", padx=2)
        self.in_var = tk.StringVar()
        e_in = ttk.Entry(mark, textvariable=self.in_var, width=12, justify="center", font=("Consolas", 10))
        e_in.pack(side="left", padx=2)
        ttk.Button(mark, text="Tới In", width=6, command=lambda: self.goto(self.cur.tin if self.cur else None)).pack(side="left")
        ttk.Button(mark, text="Mark Out (O) ]", command=self.mark_out).pack(side="left", padx=(12, 2))
        self.out_var = tk.StringVar()
        e_out = ttk.Entry(mark, textvariable=self.out_var, width=12, justify="center", font=("Consolas", 10))
        e_out.pack(side="left", padx=2)
        ttk.Button(mark, text="Tới Out", width=7, command=lambda: self.goto(self.cur.tout if self.cur else None)).pack(side="left")
        ttk.Label(mark, text="Duration", font=("Segoe UI", 9, "bold")).pack(side="left", padx=(14, 4))
        self.dur_var = tk.StringVar()
        e_dur = ttk.Entry(mark, textvariable=self.dur_var, width=12, justify="center", font=("Consolas", 10))
        e_dur.pack(side="left", padx=2)
        for e, which in ((e_in, "in"), (e_out, "out"), (e_dur, "dur")):
            e.bind("<Return>", lambda ev, w=which: self.entry_commit(w))
            e.bind("<FocusOut>", lambda ev, w=which: self.entry_commit(w))
        act = ttk.Frame(pf)
        act.grid(row=5, column=0, sticky="ew", pady=(4, 0))
        ttk.Button(act, text="▶ Xem đoạn In→Out", command=self.play_selection).pack(side="left", padx=2)
        ttk.Button(act, text="Xoá In/Out", command=self.clear_marks).pack(side="left", padx=2)
        ttk.Label(pf, text=f"Timecode HH:MM:SS:FF ({TC_FPS} frame/giây; gõ '90' = 90 giây). Nhập In + Out → tự tính Duration; "
                           "nhập In + Duration → tự điền Out.\nPhím tắt: Space=Play/Pause · I / O=Mark In/Out · ←/→=±1 frame · "
                           "Shift+←/→=±1s · Ctrl+←/→=±10s · Home/End=tới In/Out",
                  style="Hint.TLabel").grid(row=6, column=0, sticky="w", pady=(4, 0))

    def _add_combo(self, parent, row, label, key, values, editable=False, width=26):
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", pady=2, padx=(0, 6))
        var = tk.StringVar(value=DEFAULT_SETTINGS[key])
        cb = ttk.Combobox(parent, textvariable=var, values=values, width=width,
                          state="normal" if editable else "readonly")
        cb.grid(row=row, column=1, sticky="ew", pady=2)
        var.trace_add("write", self._on_setting_change)
        self.vars[key] = var
        return cb

    def _build_settings(self, parent):
        sf = ttk.LabelFrame(parent, text=" Thông số file thành phẩm ", padding=8)
        sf.grid(row=0, column=1, sticky="ns")
        sf.columnconfigure(1, weight=1)

        ttk.Label(sf, text="Profile").grid(row=0, column=0, sticky="w", pady=2)
        self.profile_var = tk.StringVar()
        self.profile_cb = ttk.Combobox(sf, textvariable=self.profile_var, state="readonly",
                                       values=list(self.profiles), width=32)
        self.profile_cb.grid(row=0, column=1, sticky="ew", pady=2)
        self.profile_cb.bind("<<ComboboxSelected>>", lambda e: self._apply_profile(self.profile_var.get()))
        pb = ttk.Frame(sf)
        pb.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(0, 2))
        ttk.Button(pb, text="Lưu", command=self.save_profile).pack(side="left", padx=(0, 4))
        ttk.Button(pb, text="Lưu thành…", command=self.save_profile_as).pack(side="left", padx=4)
        ttk.Button(pb, text="Xoá", command=self.delete_profile).pack(side="left", padx=4)
        self.mod_var = tk.StringVar()
        ttk.Label(pb, textvariable=self.mod_var, foreground="#b54708").pack(side="left", padx=6)

        ttk.Separator(sf).grid(row=2, column=0, columnspan=2, sticky="ew", pady=4)
        self.vcodec_cb = self._add_combo(sf, 3, "Video codec", "vcodec", self._vcodec_values())
        self._add_combo(sf, 4, "Video size", "size", SIZES, editable=True)
        self._add_combo(sf, 5, "Bitrate", "bitrate", BITRATES, editable=True)
        self._add_combo(sf, 6, "Frame rate", "fps", FPS_LIST, editable=True)
        self._add_combo(sf, 7, "Tốc độ encode (preset)", "preset", PRESETS)
        self._add_combo(sf, 8, "Pixel format", "pixfmt", PIXFMTS)
        ttk.Separator(sf).grid(row=9, column=0, columnspan=2, sticky="ew", pady=4)
        self._add_combo(sf, 10, "Audio codec", "acodec", [l for l, _ in AUDIO_CODECS])
        self._add_combo(sf, 11, "Audio bitrate", "abitrate", ABITRATES, editable=True)
        self._add_combo(sf, 12, "Sample rate", "asr", SAMPLE_RATES, editable=True)
        self._add_combo(sf, 13, "Channels", "ach", CHANNELS)
        ttk.Separator(sf).grid(row=14, column=0, columnspan=2, sticky="ew", pady=4)
        self._add_combo(sf, 15, "Container (đuôi file)", "container", CONTAINERS)

        self.vars["accurate"] = tk.BooleanVar(value=False)
        self.vars["accurate"].trace_add("write", self._on_setting_change)
        ttk.Checkbutton(sf, text="Cắt chính xác từng frame (encode lại video)",
                        variable=self.vars["accurate"]).grid(row=16, column=0, columnspan=2, sticky="w", pady=(6, 0))
        self.hint_var = tk.StringVar()
        ttk.Label(sf, textvariable=self.hint_var, wraplength=self.px(330), justify="left",
                  foreground="#0b4a8f").grid(row=17, column=0, columnspan=2, sticky="w", pady=(6, 0))

    def _build_output(self, root):
        of = ttk.Frame(root, padding=(8, 4, 8, 8))
        of.grid(row=3, column=0, sticky="ew")
        of.columnconfigure(1, weight=1)
        self.same_dir_var = tk.BooleanVar(value=self.config.get("same_dir", True))
        self.out_dir_var = tk.StringVar(value=self.config.get("out_dir", ""))
        self.suffix_var = tk.StringVar(value=self.config.get("suffix", "_cut"))

        ttk.Checkbutton(of, text="Lưu cùng thư mục file gốc", variable=self.same_dir_var,
                        command=self._sync_out_state).grid(row=0, column=0, sticky="w")
        self.out_entry = ttk.Entry(of, textvariable=self.out_dir_var)
        self.out_entry.grid(row=0, column=1, sticky="ew", padx=6)
        self.out_browse = ttk.Button(of, text="Chọn thư mục…", command=self.browse_out)
        self.out_browse.grid(row=0, column=2)
        ttk.Label(of, text="Hậu tố tên file").grid(row=0, column=3, padx=(14, 4))
        ttk.Entry(of, textvariable=self.suffix_var, width=10).grid(row=0, column=4)
        ttk.Button(of, text="📂 Mở thư mục kết quả", command=self.open_out).grid(row=0, column=5, padx=(14, 0))

        self.start_btn = ttk.Button(of, text="▶  START – Cắt tuần tự", style="Accent.TButton", command=self.start)
        self.start_btn.grid(row=1, column=0, pady=(8, 0), sticky="w", ipadx=10, ipady=4)
        self.stop_btn = ttk.Button(of, text="■ Dừng", command=self.stop, state="disabled")
        self.stop_btn.grid(row=1, column=0, pady=(8, 0), padx=(self.px(190), 0), sticky="w", ipady=4)
        self.total_bar = ttk.Progressbar(of, maximum=1000)
        self.total_bar.grid(row=1, column=1, columnspan=4, sticky="ew", padx=6, pady=(8, 0))
        self.status_var = tk.StringVar(value="Sẵn sàng. Thêm file video để bắt đầu.")
        ttk.Label(of, textvariable=self.status_var).grid(row=1, column=5, sticky="w", pady=(8, 0), padx=(14, 0))
        self._sync_out_state()

    def _sync_out_state(self):
        st = "disabled" if self.same_dir_var.get() else "normal"
        self.out_entry.configure(state=st)
        self.out_browse.configure(state=st)

    # ------------------------------------------------------------------ phím tắt
    def _bind_keys(self):
        r = self.root

        def guard(fn):
            def h(e):
                w = self.root.focus_get()
                if w is not None and w.winfo_class() in ("TEntry", "TCombobox", "Entry", "TSpinbox"):
                    return None
                fn()
                return "break"
            return h

        r.bind("<space>", guard(self.toggle_play))
        r.bind("<Key-i>", guard(self.mark_in))
        r.bind("<Key-o>", guard(self.mark_out))
        r.bind("<Left>", guard(lambda: self.step(-1)))
        r.bind("<Right>", guard(lambda: self.step(1)))
        r.bind("<Shift-Left>", guard(lambda: self.jump(-1)))
        r.bind("<Shift-Right>", guard(lambda: self.jump(1)))
        r.bind("<Control-Left>", guard(lambda: self.jump(-10)))
        r.bind("<Control-Right>", guard(lambda: self.jump(10)))
        r.bind("<Home>", guard(lambda: self.goto(self.cur.tin if self.cur else None)))
        r.bind("<End>", guard(lambda: self.goto(self.cur.tout if self.cur else None)))

    # ------------------------------------------------------------------ profile
    def current_settings(self):
        return {k: self.vars[k].get() for k in SETTING_KEYS}

    def _apply_profile(self, name):
        data = self.profiles.get(name)
        if data is None:
            return
        self._loading = True
        try:
            for k in SETTING_KEYS:
                self.vars[k].set(data.get(k, DEFAULT_SETTINGS[k]))
        finally:
            self._loading = False
        self.profile_var.set(name)
        self.profile_cb.configure(values=list(self.profiles))
        self.modified = False
        self.mod_var.set("")
        self.hint_var.set(describe_plan(self.current_settings()))

    def _on_setting_change(self, *_):
        if self._loading:
            return
        self.hint_var.set(describe_plan(self.current_settings()))
        saved = self.profiles.get(self.profile_var.get())
        self.modified = saved is None or any(saved.get(k, DEFAULT_SETTINGS[k]) != v
                                             for k, v in self.current_settings().items())
        self.mod_var.set("● đã sửa" if self.modified else "")

    def save_profile(self):
        name = self.profile_var.get()
        if name not in self.profiles:
            return self.save_profile_as()
        self.profiles[name] = self.current_settings()
        self._save_profiles()
        self._on_setting_change()
        self.status_var.set(f"Đã lưu profile '{name}'")

    def save_profile_as(self):
        name = simpledialog.askstring("Lưu profile", "Tên profile:", parent=self.root)
        if not name or not name.strip():
            return
        name = name.strip()
        if name in self.profiles and not messagebox.askyesno("Ghi đè?", f"Profile '{name}' đã có. Ghi đè?"):
            return
        self.profiles[name] = self.current_settings()
        self._save_profiles()
        self.profile_cb.configure(values=list(self.profiles))
        self.profile_var.set(name)
        self._on_setting_change()
        self.status_var.set(f"Đã lưu profile '{name}'")

    def delete_profile(self):
        name = self.profile_var.get()
        if name not in self.profiles:
            return
        if len(self.profiles) <= 1:
            messagebox.showinfo("Không xoá được", "Phải giữ lại ít nhất một profile.")
            return
        if not messagebox.askyesno("Xoá profile", f"Xoá profile '{name}'?"):
            return
        del self.profiles[name]
        self._save_profiles()
        self._apply_profile(next(iter(self.profiles)))

    # ------------------------------------------------------------------ danh sách file
    def add_files(self):
        paths = filedialog.askopenfilenames(
            title="Chọn file video", initialdir=self.config.get("add_dir") or None,
            filetypes=[("Video", " ".join("*" + e for e in VIDEO_EXTS)), ("Tất cả file", "*.*")])
        if paths:
            self.config["add_dir"] = os.path.dirname(paths[0])
            self._add_paths(list(paths))

    def add_folder(self):
        d = filedialog.askdirectory(title="Chọn thư mục chứa video", initialdir=self.config.get("add_dir") or None)
        if not d:
            return
        self.config["add_dir"] = d
        paths = sorted((os.path.join(d, f) for f in os.listdir(d) if f.lower().endswith(VIDEO_EXTS)),
                       key=lambda p: p.lower())
        if not paths:
            messagebox.showinfo("Không có video", "Thư mục này không có file video nào.")
            return
        self._add_paths(paths)

    def _add_paths(self, paths):
        new = []
        for p in paths:
            p = os.path.normpath(p)
            self.counter += 1
            it = Item(p)
            iid = f"i{self.counter}"
            self.items[iid] = it
            self.tree.insert("", "end", iid=iid, values=self._row_values(it))
            new.append((iid, it))
        self._renumber()
        threading.Thread(target=self._probe_worker, args=(new,), daemon=True).start()
        if not self.tree.selection() and new:
            self.tree.selection_set(new[0][0])

    def _probe_worker(self, pairs):
        for iid, it in pairs:
            try:
                self.q.put(("probe", iid, probe_file(it.path), None))
            except Exception as e:
                self.q.put(("probe", iid, None, str(e)))

    def _row_values(self, it, no=None):
        dur = fmt_tc(it.info["duration"]) if it.info else ""
        s, e = it.clip_range() if it.info else (0, 0)
        ln = fmt_tc(e - s) if it.info and (it.tin is not None or it.tout is not None) else ("(cả file)" if it.info else "")
        return (no if no is not None else "", it.name, dur, fmt_tc(it.tin) if it.tin is not None else "",
                fmt_tc(it.tout) if it.tout is not None else "", ln, it.status)

    def _renumber(self):
        for n, iid in enumerate(self.tree.get_children(), 1):
            self.tree.set(iid, "no", n)

    def refresh_row(self, iid):
        if iid not in self.items:
            return
        it = self.items[iid]
        no = self.tree.set(iid, "no")
        self.tree.item(iid, values=self._row_values(it, no))
        tag = {"done": "done", "error": "error", "running": "running"}.get(it.state, "")
        self.tree.item(iid, tags=(tag,) if tag else ())

    def remove_selected(self):
        if self.running:
            return
        sel = self.tree.selection()
        if self.cur_iid in sel:
            self.unload()
        for iid in sel:
            self.tree.delete(iid)
            self.items.pop(iid, None)
        self._renumber()

    def clear_all(self):
        if self.running or not self.items:
            return
        if messagebox.askyesno("Xoá hết", "Xoá toàn bộ danh sách?"):
            self.unload()
            self.tree.delete(*self.tree.get_children())
            self.items.clear()

    def move(self, d):
        if self.running:
            return
        sel = list(self.tree.selection())
        order = sel if d < 0 else sel[::-1]
        for iid in order:
            idx = self.tree.index(iid) + d
            if 0 <= idx < len(self.tree.get_children()):
                self.tree.move(iid, "", idx)
        self._renumber()

    def duplicate(self):
        if self.running:
            return
        for iid in self.tree.selection():
            src = self.items[iid]
            self.counter += 1
            it = Item(src.path)
            it.info, it.tin, it.tout, it.state, it.status = src.info, src.tin, src.tout, "ready", "Chờ"
            nid = f"i{self.counter}"
            self.items[nid] = it
            self.tree.insert("", self.tree.index(iid) + 1, iid=nid, values=self._row_values(it))
        self._renumber()

    def reset_status(self):
        if self.running:
            return
        for iid, it in self.items.items():
            if it.info and it.state in ("done", "error", "stopped"):
                it.state, it.status = "ready", "Chờ"
                self.refresh_row(iid)
        self.total_bar["value"] = 0

    # ------------------------------------------------------------------ preview
    def unload(self):
        self.stop_play()
        self._kill_still()
        self.cur = self.cur_iid = None
        self.canvas.itemconfig(self.img_id, image="")
        self.canvas.itemconfig(self.msg_id, state="normal")
        self.info_var.set("")
        self.in_var.set("")
        self.out_var.set("")
        self.dur_var.set("")
        self.time_var.set("00:00:00:00 / 00:00:00:00")
        self.timeline.set_state(dur=0, pos=0, tin=None, tout=None)

    def on_select(self, _=None):
        sel = self.tree.selection()
        if not sel:
            return
        iid = sel[0]
        if iid == self.cur_iid:
            return
        self.load_item(iid)

    def load_item(self, iid):
        it = self.items.get(iid)
        if it is None:
            return
        self.stop_play()
        self.cur, self.cur_iid = it, iid
        if not it.info:
            self.canvas.itemconfig(self.msg_id, state="normal", text=it.status)
            self.canvas.itemconfig(self.img_id, image="")
            self.info_var.set("")
            self.timeline.set_state(dur=0, pos=0, tin=None, tout=None)
            return
        self.canvas.itemconfig(self.msg_id, state="hidden")
        self.info_var.set(describe_info(it.info))
        self.refresh_marks()
        self.seek(it.tin or 0.0)

    def refresh_marks(self):
        it = self.cur
        if not it:
            return
        self.in_var.set(fmt_tc(it.tin) if it.tin is not None else "")
        self.out_var.set(fmt_tc(it.tout) if it.tout is not None else "")
        if it.info:
            s, e = it.clip_range()
            self.dur_var.set(fmt_tc(e - s))
        self.timeline.set_state(tin=it.tin, tout=it.tout)
        self.refresh_row(self.cur_iid)

    def _frame_step(self):
        v = self.cur.info.get("v") if self.cur and self.cur.info else None
        return 1.0 / v["fps"] if v and v["fps"] else 1.0 / 25

    def _dur(self):
        return self.cur.info["duration"] if self.cur and self.cur.info else 0.0

    def update_time(self):
        self.time_var.set(f"{fmt_tc(self.pos)} / {fmt_tc(self._dur())}")
        self.timeline.set_state(dur=self._dur(), pos=self.pos)

    def _canvas_size(self):
        return max(self.canvas.winfo_width(), 64), max(self.canvas.winfo_height(), 64)

    def _on_canvas_resize(self, e):
        self.canvas.coords(self.img_id, e.width / 2, e.height / 2)
        self.canvas.coords(self.msg_id, e.width / 2, e.height / 2)
        if self.resize_after:
            self.root.after_cancel(self.resize_after)
        self.resize_after = self.root.after(200, self._after_resize)

    def _after_resize(self):
        self.resize_after = None
        if self.cur and self.cur.info and not self.playing:
            self.seek(self.pos)

    # ---- seek (ảnh tĩnh)
    def seek(self, t, fast=False):
        if not self.cur or not self.cur.info:
            return
        dur = self._dur()
        t = min(max(t, 0.0), max(dur - 0.04, 0.0))
        was_playing = self.playing
        if was_playing:
            self.stop_play()
        self.pos = t
        self.update_time()
        self.pending_seek = (t, fast)
        if self.seek_after is None:
            self.seek_after = self.root.after(25, self._dispatch_still)

    def _kill_still(self):
        p, self.still_proc = self.still_proc, None
        if p and p.poll() is None:
            try:
                p.kill()
            except OSError:
                pass

    def _dispatch_still(self):
        self.seek_after = None
        if self.playing or not self.pending_seek or not self.cur or not self.cur.info or not self.cur.info.get("v"):
            return
        t, fast = self.pending_seek
        self._kill_still()
        self.still_gen += 1
        w, h = self._canvas_size()
        threading.Thread(target=self._still_worker, args=(self.cur.path, t, fast, w, h, self.still_gen),
                         daemon=True).start()

    def _still_worker(self, path, t, fast, w, h, gen):
        cmd = [FFMPEG, "-hide_banner", "-v", "error", "-nostdin"]
        if fast:
            cmd += ["-noaccurate_seek"]
        cmd += ["-ss", f"{t:.3f}", "-i", path, "-an", "-sn", "-frames:v", "1",
                "-vf", f"scale={w}:{h}:force_original_aspect_ratio=decrease:flags=fast_bilinear",
                "-f", "image2pipe", "-c:v", "ppm", "-"]
        try:
            p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL,
                                 creationflags=NO_WINDOW)
            self.still_proc = p
            data = p.stdout.read()
            p.wait()
            if data and p.returncode == 0:
                self.q.put(("still", gen, data))
        except Exception:
            pass

    def _show_ppm(self, data):
        try:
            img = tk.PhotoImage(data=data)
        except tk.TclError:
            return
        self.photo = img
        self.canvas.itemconfig(self.img_id, image=img)
        w, h = self._canvas_size()
        self.canvas.coords(self.img_id, w / 2, h / 2)

    # ---- phát
    def toggle_play(self):
        if self.playing:
            self.stop_play()
        else:
            self.start_play()

    def start_play(self, until=None):
        if not self.cur or not self.cur.info or not self.cur.info.get("v"):
            return
        self.stop_play()
        self._kill_still()
        self.still_gen += 1
        if self.pos >= self._dur() - 0.1:
            self.pos = 0.0
        self.play_gen += 1
        self.play_t0, self.play_until = self.pos, until
        self.play_q = queue.Queue(maxsize=6)
        self.play_clock = None
        self.play_pending = None
        w, h = self._canvas_size()
        cmd = [FFMPEG, "-hide_banner", "-v", "error", "-nostdin", "-ss", f"{self.pos:.3f}",
               "-i", self.cur.path, "-an", "-sn",
               "-vf", f"fps={PREVIEW_FPS},scale={w}:{h}:force_original_aspect_ratio=decrease:flags=fast_bilinear",
               "-f", "image2pipe", "-c:v", "ppm", "-"]
        try:
            self.play_proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                              stdin=subprocess.DEVNULL, creationflags=NO_WINDOW, bufsize=1 << 20)
        except OSError as e:
            messagebox.showerror("Lỗi", str(e))
            return
        self.playing = True
        self.play_btn.configure(text="⏸ Pause")
        threading.Thread(target=self._play_reader, args=(self.play_proc, self.play_gen, self.play_q),
                         daemon=True).start()

    def _play_reader(self, proc, gen, out_q):
        """Đọc luồng PPM từ ffmpeg. Hàng đợi đầy -> chờ (ffmpeg bị chặn theo), nên không tốn RAM."""
        f = proc.stdout

        def put(item):
            while gen == self.play_gen:
                try:
                    out_q.put(item, timeout=0.2)
                    return True
                except queue.Full:
                    pass
            return False

        idx = 0
        try:
            while gen == self.play_gen:
                magic = f.readline()
                if not magic:
                    break
                dims, mx = f.readline(), f.readline()
                w, h = (int(x) for x in dims.split())
                body = f.read(w * h * 3)
                if len(body) < w * h * 3 or not put((idx, magic + dims + mx + body)):
                    break
                idx += 1
        except Exception:
            pass
        finally:
            if gen == self.play_gen:
                put(None)

    def _start_audio(self, pos):
        """Phát tiếng bằng ffplay (chỉ audio, không cửa sổ) từ vị trí pos."""
        self._stop_audio()
        it = self.cur
        if not FFPLAY or not self.audio_on.get() or not it or not it.info or not it.info.get("a"):
            return
        vol = int(self.volume.get())
        if vol <= 0:
            return
        try:
            self.audio_proc = subprocess.Popen(
                [FFPLAY, "-nodisp", "-vn", "-sn", "-autoexit", "-loglevel", "quiet", "-ss", f"{pos:.3f}",
                 "-volume", str(vol), it.path],
                stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                creationflags=NO_WINDOW)
        except OSError:
            self.audio_proc = None

    def _stop_audio(self):
        p, self.audio_proc = self.audio_proc, None
        if p and p.poll() is None:
            try:
                p.kill()
            except OSError:
                pass

    def _audio_changed(self):
        """Đổi bật/tắt hoặc âm lượng khi đang phát -> khởi động lại tiếng từ vị trí hiện tại."""
        if self.playing and self.play_clock is not None:
            self._start_audio(self.pos)
        elif not self.audio_on.get():
            self._stop_audio()

    def stop_play(self):
        self.play_gen += 1
        self._stop_audio()
        p, self.play_proc = self.play_proc, None
        if p and p.poll() is None:
            try:
                p.kill()
            except OSError:
                pass
        if self.playing:
            self.playing = False
            self.play_btn.configure(text="▶ Play")

    def play_selection(self):
        it = self.cur
        if not it or not it.info:
            return
        s, e = it.clip_range()
        self.pos = s
        self.start_play(until=e)

    def step(self, n):
        if self.cur and self.cur.info:
            self.seek(self.pos + n * self._frame_step())
            self.root.after(120, lambda: self.seek(self.pos))

    def jump(self, sec):
        if self.cur and self.cur.info:
            self.seek(self.pos + sec)

    def goto(self, t):
        if t is not None and self.cur and self.cur.info:
            self.seek(t)

    # ---- mark in / out
    def set_in(self, t):
        it = self.cur
        if not it or not it.info:
            return
        t = min(max(t, 0.0), it.info["duration"])
        if it.tout is not None and t >= it.tout:
            t = max(it.tout - self._frame_step(), 0.0)
        it.tin = t
        self._marks_changed()

    def set_out(self, t):
        it = self.cur
        if not it or not it.info:
            return
        dur = it.info["duration"]
        t = min(max(t, 0.0), dur)
        if it.tin is not None and t <= it.tin:
            t = min(it.tin + self._frame_step(), dur)
        it.tout = t
        self._marks_changed()

    def _marks_changed(self):
        it = self.cur
        if it.state in ("done", "error", "stopped"):
            it.state, it.status = "ready", "Chờ"
        self.refresh_marks()

    def mark_in(self):
        self.set_in(self.pos)

    def mark_out(self):
        self.set_out(self.pos)

    def clear_marks(self):
        if self.cur:
            self.cur.tin = self.cur.tout = None
            self._marks_changed()

    def entry_commit(self, which):
        """Nhập tay In / Out / Duration. In+Out -> tính Duration; In+Duration -> điền Out."""
        it = self.cur
        if not it or not it.info:
            return
        dur = it.info["duration"]
        var = {"in": self.in_var, "out": self.out_var, "dur": self.dur_var}[which]
        text = var.get().strip()
        c0, c1 = it.clip_range()
        shown = {"in": it.tin, "out": it.tout, "dur": c1 - c0}[which]
        if text == (fmt_tc(shown) if shown is not None else ""):
            return                              # không đổi -> giữ nguyên giá trị chính xác đang lưu
        seek_to = None
        if not text and which != "dur":
            if which == "in":
                it.tin = None
            else:
                it.tout = None
        else:
            t = parse_tc(text)
            if t is None or (which == "dur" and t <= 0):
                self.refresh_marks()
                return
            if which == "in":
                it.tin = seek_to = min(t, dur)
                if it.tout is not None and it.tout <= it.tin:
                    it.tout = None              # In vượt Out cũ -> bỏ Out, cắt tới hết file
            elif which == "out":
                it.tout = seek_to = min(t, dur)
                if it.tin is not None and it.tin >= it.tout:
                    it.tin = None
            else:
                if it.tin is not None or it.tout is None:
                    it.tin = it.tin or 0.0
                    it.tout = min(it.tin + t, dur)
                else:                           # chỉ có Out -> lùi In lại
                    it.tin = max(it.tout - t, 0.0)
                seek_to = it.tout
        self._marks_changed()
        if seek_to is not None:
            self.seek(seek_to)

    # ------------------------------------------------------------------ xử lý sự kiện nền
    def _poll_playback(self):
        """Lấy các frame đã đến hạn theo đồng hồ, chỉ hiển thị frame mới nhất (rớt frame nếu máy chậm)."""
        shown = None
        ended = False
        now = time.perf_counter()
        while True:
            item = self.play_pending
            self.play_pending = None
            if item is None:
                try:
                    item = self.play_q.get_nowait()
                except queue.Empty:
                    break
            if item is False or item is None:      # None = hết luồng
                ended = True
                break
            if self.play_clock is None:
                self.play_clock = now
                self._start_audio(self.play_t0)      # tiếng bắt đầu cùng lúc với frame đầu tiên
            if item[0] <= (now - self.play_clock) * PREVIEW_FPS:
                shown = item
            else:
                self.play_pending = item
                break
        if shown is not None:
            self._show_ppm(shown[1])
            self.pos = min(self.play_t0 + shown[0] / PREVIEW_FPS, self._dur())
            self.update_time()
            if self.play_until is not None and self.pos >= self.play_until:
                end = self.play_until
                self.stop_play()
                self.seek(end)
                return
        if ended and self.play_pending is None:
            self.stop_play()

    def _poll(self):
        if self.playing:
            self._poll_playback()
        try:
            while True:
                ev = self.q.get_nowait()
                kind = ev[0]
                if kind == "still":
                    if ev[1] == self.still_gen and not self.playing:
                        self._show_ppm(ev[2])
                elif kind == "probe":
                    self._on_probe(*ev[1:])
                elif kind == "hw":
                    self.hw_ok = ev[1]
                    self.vcodec_cb.configure(values=self._vcodec_values())
                elif kind == "job":
                    self._on_job_event(ev)
        except queue.Empty:
            pass
        self.root.after(15, self._poll)

    def _on_probe(self, iid, info, err):
        it = self.items.get(iid)
        if it is None:
            return
        if err:
            it.state, it.status = "error", "Lỗi đọc file"
            it.err = err
        else:
            it.info, it.state, it.status = info, "ready", "Chờ"
        self.refresh_row(iid)
        if iid == self.cur_iid:
            self.cur_iid = None
            self.load_item(iid)
        elif self.cur is None and self.tree.selection() == (iid,):
            self.load_item(iid)

    # ------------------------------------------------------------------ xuất file
    def browse_out(self):
        d = filedialog.askdirectory(title="Thư mục lưu file thành phẩm")
        if d:
            self.out_dir_var.set(os.path.normpath(d))

    def open_out(self):
        d = self.last_out_dir or (self.out_dir_var.get() if not self.same_dir_var.get() else None)
        if not d and self.cur:
            d = os.path.dirname(self.cur.path)
        if d and os.path.isdir(d):
            os.startfile(d)

    def set_busy(self, busy):
        self.running = busy
        st = "disabled" if busy else "normal"
        for b in self.list_buttons:
            b.configure(state=st)
        self.start_btn.configure(state=st)
        self.stop_btn.configure(state="normal" if busy else "disabled")

    def start(self):
        if self.running:
            return
        S = self.current_settings()
        err = validate_settings(S)
        if err:
            messagebox.showwarning("Thông số chưa hợp lệ", err)
            return
        if not self.same_dir_var.get():
            d = self.out_dir_var.get().strip()
            if not d:
                messagebox.showwarning("Thiếu thư mục", "Hãy chọn thư mục lưu file thành phẩm "
                                                         "(hoặc tick 'Lưu cùng thư mục file gốc').")
                return
            try:
                os.makedirs(d, exist_ok=True)
            except OSError as e:
                messagebox.showerror("Lỗi", f"Không tạo được thư mục:\n{e}")
                return
        jobs = []
        for iid in self.tree.get_children():
            it = self.items[iid]
            if it.state in ("ready", "stopped") and it.info:
                s, e = it.clip_range()
                if e - s < 0.05:
                    it.state, it.status = "error", "Lỗi: đoạn cắt quá ngắn"
                    self.refresh_row(iid)
                    continue
                jobs.append((iid, it))
        if not jobs:
            messagebox.showinfo("Không có việc", "Không có file nào đang chờ cắt.\n"
                                                  "(Dùng '↺ Đặt lại trạng thái' để cắt lại các file đã xong.)")
            return
        self._save_config()
        self.stop_flag.clear()
        self.set_busy(True)
        self.total_bar["value"] = 0
        for iid, it in jobs:
            it.state, it.status = "ready", "Đang chờ…"
            self.refresh_row(iid)
        out_cfg = (self.same_dir_var.get(), self.out_dir_var.get().strip(), self.suffix_var.get())
        threading.Thread(target=self._run_jobs, args=(jobs, S, out_cfg), daemon=True).start()

    def stop(self):
        self.stop_flag.set()
        p = self.job_proc
        if p and p.poll() is None:
            try:
                p.kill()
            except OSError:
                pass
        self.status_var.set("Đang dừng…")

    def _run_jobs(self, jobs, S, out_cfg):
        same_dir, out_dir, suffix = out_cfg
        total = len(jobs)
        done = fails = 0
        for n, (iid, it) in enumerate(jobs):
            if self.stop_flag.is_set():
                self.q.put(("job", "stopped", iid, n, total))
                continue
            start, end = it.clip_range()
            clip = end - start
            folder = os.path.dirname(it.path) if same_dir else out_dir
            cont = resolve_container(S, it.path)
            out_path = unique_path(folder, os.path.splitext(it.name)[0], suffix, cont)
            try:
                cmd, note = build_command(it.info, it.path, out_path, start,
                                          end if it.tout is not None else None, S)
            except Exception as e:
                self.q.put(("job", "error", iid, n, total, str(e)))
                fails += 1
                continue
            self.q.put(("job", "start", iid, n, total, note, out_path))
            tail = []
            t0 = time.time()
            try:
                p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                                     creationflags=NO_WINDOW, text=True, encoding="utf-8", errors="replace")
                self.job_proc = p
                for line in p.stdout:
                    line = line.strip()
                    if line.startswith(("out_time_us=", "out_time_ms=")):
                        try:
                            frac = min(int(line.split("=")[1]) / 1e6 / clip, 1.0)
                            self.q.put(("job", "prog", iid, n, total, frac))
                        except (ValueError, ZeroDivisionError):
                            pass
                    elif "=" in line and line.split("=")[0].replace("_", "").isalnum() and " " not in line.split("=")[0]:
                        continue            # các dòng progress khác (fps=, bitrate=, ...)
                    elif line:
                        tail.append(line)
                        tail = tail[-8:]
                p.wait()
                rc = p.returncode
            except Exception as e:
                rc, tail = -1, [str(e)]
            finally:
                self.job_proc = None
            if self.stop_flag.is_set():
                self._try_remove(out_path)
                self.q.put(("job", "stopped", iid, n, total))
            elif rc == 0 and os.path.exists(out_path):
                done += 1
                self.q.put(("job", "done", iid, n, total, out_path, time.time() - t0))
            else:
                fails += 1
                self._try_remove(out_path)
                self.q.put(("job", "error", iid, n, total, " | ".join(tail) or f"ffmpeg thoát mã {rc}"))
        self.q.put(("job", "all", done, fails, total, self.stop_flag.is_set()))

    @staticmethod
    def _try_remove(path):
        try:
            if os.path.exists(path):
                os.remove(path)
        except OSError:
            pass

    def _on_job_event(self, ev):
        kind = ev[1]
        if kind == "all":
            _, _, done, fails, total, stopped = ev
            self.set_busy(False)
            self.total_bar["value"] = 1000 if not stopped else self.total_bar["value"]
            msg = f"Hoàn tất: {done}/{total} file" + (f", {fails} lỗi" if fails else "") + (" (đã dừng)" if stopped else "")
            self.status_var.set(msg)
            if not stopped and not fails:
                self.root.bell()
            return
        iid, n, total = ev[2], ev[3], ev[4]
        it = self.items.get(iid)
        if it is None:
            return
        if kind == "start":
            it.state, it.status, it.out_path = "running", "Đang cắt 0%", ev[6]
            self.status_var.set(f"[{n + 1}/{total}] {it.name} – {ev[5]}")
            self.tree.see(iid)
        elif kind == "prog":
            it.status = f"Đang cắt {ev[5] * 100:.0f}%"
            self.total_bar["value"] = (n + ev[5]) / total * 1000
        elif kind == "done":
            it.state, it.status = "done", f"Xong ✓ ({ev[6]:.1f}s) → {os.path.basename(ev[5])}"
            it.out_path = ev[5]
            self.last_out_dir = os.path.dirname(ev[5])
            self.total_bar["value"] = (n + 1) / total * 1000
        elif kind == "error":
            it.state, it.status = "error", "Lỗi: " + ev[5][:160]
            self.total_bar["value"] = (n + 1) / total * 1000
        elif kind == "stopped":
            it.state, it.status = "stopped", "Đã dừng"
        self.refresh_row(iid)

    # ------------------------------------------------------------------ thoát
    def on_close(self):
        if self.running and not messagebox.askyesno("Đang chạy", "Đang cắt file. Dừng và thoát?"):
            return
        self.stop_flag.set()
        self.stop_play()
        self._kill_still()
        if self.job_proc and self.job_proc.poll() is None:
            try:
                self.job_proc.kill()
            except OSError:
                pass
        self._save_config()
        self.root.destroy()


def main():
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass
    root = tk.Tk()

    def report(exc, val, tb):
        text = "".join(traceback.format_exception(exc, val, tb))
        try:
            with open(ERROR_LOG, "a", encoding="utf-8") as f:
                f.write(time.strftime("%Y-%m-%d %H:%M:%S\n") + text + "\n")
        except OSError:
            pass
        sys.stderr.write(text)

    root.report_callback_exception = report
    if not (FFMPEG and FFPROBE):
        messagebox.showerror("Thiếu ffmpeg", "Không tìm thấy ffmpeg.exe / ffprobe.exe.\n"
                                             f"Hãy đặt chúng cạnh trimfile.py:\n{APP_DIR}")
        return
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
