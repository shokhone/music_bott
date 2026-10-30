"""Работа с видео: конвертация, кружок, музыка из видео (ffmpeg)."""
import asyncio
import re
from pathlib import Path

from effects import FFMPEG, FFmpegError, _run

TG_LIMIT = 49 * 1024 * 1024  # бот может отправлять файлы до 50 МБ

# цель -> (название кнопки, расширение результата)
VIDEO_TARGETS = {
    "mp4": ("🎬 MP4", "mp4"),
    "mkv": ("📦 MKV", "mkv"),
    "webm": ("🌐 WEBM", "webm"),
    "avi": ("📼 AVI", "avi"),
    "mov": ("🍎 MOV", "mov"),
    "gif": ("🖼 GIF", "gif"),
    "circle": ("⭕ Кружок", "mp4"),
}


async def probe(path) -> dict:
    """Кодеки, размер кадра и длительность — по выводу `ffmpeg -i` (ffprobe не нужен)."""
    info = {"vcodec": None, "acodec": None, "width": None, "height": None, "duration": None}
    if not FFMPEG:
        return info
    try:
        p = await asyncio.create_subprocess_exec(
            FFMPEG, "-hide_banner", "-i", str(path),
            stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.PIPE,
        )
        _, err = await asyncio.wait_for(p.communicate(), 30)
    except Exception:
        return info
    text = err.decode("utf-8", errors="ignore")
    m = re.search(r"Duration: (\d+):(\d+):(\d+(?:\.\d+)?)", text)
    if m:
        info["duration"] = int(round(int(m[1]) * 3600 + int(m[2]) * 60 + float(m[3])))
    m = re.search(r"Video: (\w+)[^\n]*?[ ,](\d{2,5})x(\d{2,5})", text)
    if m:
        info["vcodec"], w, h = m[1], int(m[2]), int(m[3])
        r = re.search(r"rotation of (-?[\d.]+) degrees|rotate\s*:\s*(-?\d+)", text)
        if r and abs(round(float(r[1] or r[2]))) % 180 == 90:  # снято на телефон «боком»
            w, h = h, w
        info["width"], info["height"] = w, h
    m = re.search(r"Audio: (\w+)", text)
    if m:
        info["acodec"] = m[1]
    return info


async def extract_audio(src: str, out_dir: Path) -> Path:
    out = out_dir / "music.mp3"
    await _run("-y", "-i", src, "-vn", "-map", "0:a:0", "-c:a", "libmp3lame",
               "-b:a", "192k", "-ar", "44100", "-ac", "2", str(out))
    return out


async def convert_video(src: str, out_dir: Path, target: str) -> Path:
    ext = VIDEO_TARGETS[target][1]
    out = out_dir / f"result_{target}.{ext}"
    scale = "scale='min(1280,iw)':-2,format=yuv420p"
    h264 = ["-c:v", "libx264", "-preset", "superfast", "-crf", "26"]
    aac = ["-c:a", "aac", "-b:a", "160k"]
    base = ["-y", "-i", src, "-map", "0:v:0", "-map", "0:a:0?"]

    if target in ("mp4", "mov", "mkv"):
        # видео уже h264/aac (так почти всё из Telegram) — просто меняем контейнер
        # без перекодирования: это мгновенно и без потери качества
        info = await probe(src)
        if (info["vcodec"] == "h264" and info["acodec"] in (None, "aac")
                and (info["width"] or 0) <= 1920 and (info["height"] or 0) <= 1920):
            try:
                await _run(*base, "-c", "copy", "-movflags", "+faststart", str(out), timeout=300)
                return out
            except FFmpegError:
                pass
        args = [*base, "-vf", scale, *h264, *aac, "-movflags", "+faststart", str(out)]
    elif target == "webm":
        args = [*base, "-vf", scale, "-c:v", "libvpx-vp9", "-deadline", "realtime",
                "-cpu-used", "8", "-row-mt", "1", "-b:v", "0", "-crf", "36", "-c:a", "libopus",
                "-b:a", "128k", str(out)]
    elif target == "avi":
        args = [*base, "-vf", scale, "-c:v", "mpeg4", "-q:v", "5",
                "-c:a", "libmp3lame", "-b:a", "160k", str(out)]
    elif target == "gif":
        args = ["-y", "-t", "15", "-i", src, "-an", "-vf",
                "fps=12,scale=480:-2:flags=fast_bilinear,split[a][b];"
                "[a]palettegen=stats_mode=diff[p];[b][p]paletteuse=dither=bayer:bayer_scale=5",
                "-loop", "0", str(out)]
    elif target == "circle":  # кружок Telegram: квадрат, до 60 секунд
        args = ["-y", "-t", "60", "-i", src, "-map", "0:v:0", "-map", "0:a:0?",
                "-vf", "crop=w='min(iw,ih)':h='min(iw,ih)',scale=384:384,format=yuv420p",
                "-c:v", "libx264", "-preset", "superfast", "-crf", "27",
                "-c:a", "aac", "-b:a", "96k", "-movflags", "+faststart", str(out)]
    else:
        raise FFmpegError("Неизвестный формат")
    await _run(*args)
    return out
