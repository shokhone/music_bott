import asyncio
import shutil
from pathlib import Path


def _find_ffmpeg() -> str | None:
    p = shutil.which("ffmpeg")
    if p:
        return p
    try:  # встроенный ffmpeg из пакета imageio-ffmpeg (ставится через pip)
        import imageio_ffmpeg

        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return None


FFMPEG = _find_ffmpeg()

# формат -> (название кнопки, расширение)
FORMATS = {
    "mp3": ("🎵 MP3", "mp3"),
    "m4a": ("🍏 M4A (AAC)", "m4a"),
    "mp4": ("🎬 MP4 (видео с обложкой)", "mp4"),
    "ogg": ("🌀 OGG", "ogg"),
    "flac": ("💎 FLAC", "flac"),
    "wav": ("📼 WAV", "wav"),
    "voice": ("🎙 Голосовое сообщение", "ogg"),
    "circle": ("⭕ Кружок", "mp4"),
}

# ключ -> (название кнопки, фильтр ffmpeg)
EFFECTS = {
    "8d": (
        "🎧 8D",
        "aformat=channel_layouts=stereo,"
        "apulsator=mode=sine:hz=0.125:amount=1:offset_l=0:offset_r=0.5,"
        "aecho=0.8:0.6:25:0.2",
    ),
    "concert": (
        "🎤 Концертный зал",
        "aformat=channel_layouts=stereo,"
        "aecho=0.8:0.88:60|110|180:0.35|0.25|0.15,extrastereo=m=1.6,treble=g=2",
    ),
    "hall": ("🏛 Большой зал", "aecho=0.8:0.85:90|200:0.35|0.2"),
    "bass": ("🔊 Бас-буст", "bass=g=12:f=90,equalizer=f=60:t=q:w=1:g=4"),
    "slowed": (
        "🌙 Slowed + Reverb",
        "aresample=44100,asetrate=37485,aresample=44100,aecho=0.8:0.88:70|140:0.35|0.25",
    ),
    "nightcore": ("⚡ Nightcore", "aresample=44100,asetrate=53000,aresample=44100"),
    "lofi": (
        "📻 Lo-Fi",
        "highpass=f=150,lowpass=f=3500,acrusher=bits=10:mode=log:aa=1,volume=1.2",
    ),
    "underwater": ("🌊 Под водой", "lowpass=f=700,aecho=0.8:0.7:40:0.3"),
    "phone": ("📞 Телефон", "highpass=f=400,lowpass=f=3200,volume=1.5"),
    "cave": ("🕳 Пещера", "aecho=0.8:0.9:500|1000:0.4|0.25"),
    "wide": ("🌌 Широкое стерео", "aformat=channel_layouts=stereo,extrastereo=m=2.5"),
    "chorus": (
        "🎼 Хорус",
        "chorus=0.6:0.9:50|60|40:0.4|0.32|0.3:0.25|0.4|0.3:2|2.3|1.3",
    ),
    "flanger": ("🌀 Flanger", "flanger=delay=5:depth=4:regen=3:width=80:speed=0.5"),
    "bitcrush": ("👾 Bit crush", "acrusher=bits=6:mode=lin:aa=0:samples=4:mix=1,volume=0.8"),
}


class FFmpegError(Exception):
    pass


async def _run(*args: str, timeout: float | None = 900):
    if not FFMPEG:
        raise FFmpegError(
            "ffmpeg не найден. Выполни: pip install imageio-ffmpeg "
            "(или установи ffmpeg в систему) и перезапусти бота."
        )
    try:
        p = await asyncio.create_subprocess_exec(
            FFMPEG, *args, stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.PIPE
        )
    except FileNotFoundError:
        raise FFmpegError(f"Не удалось запустить ffmpeg: {FFMPEG}")
    try:
        _, err = await asyncio.wait_for(p.communicate(), timeout)
    except asyncio.TimeoutError:
        p.kill()
        raise FFmpegError("Обработка заняла слишком много времени. Попробуй файл покороче.")
    if p.returncode:
        text = err.decode(errors="ignore").strip().splitlines()
        raise FFmpegError(" | ".join(text[-3:])[-400:])


async def prepare_cover(src: str, out: Path):
    """Квадратная jpg-обложка 500x500."""
    await _run(
        "-y", "-i", src,
        "-vf", "scale=500:500:force_original_aspect_ratio=increase,crop=500:500",
        "-frames:v", "1", "-q:v", "4", str(out),
    )


async def render(src: str, out_dir: Path, fx: str | None, fmt: str, title: str,
                 artist: str, desc: str, cover: str | None) -> Path:
    """Один проход ffmpeg: эффект + конвертация в нужный формат + теги + обложка."""
    out = out_dir / f"out.{FORMATS[fmt][1]}"
    if out.exists():
        out.unlink()
    af = (EFFECTS[fx][1] + "," if fx and EFFECTS[fx][1] else "") + "alimiter=limit=0.95"

    meta = ["-map_metadata", "-1", "-metadata", f"title={title}"]
    if artist:
        meta += ["-metadata", f"artist={artist}"]
    if desc:
        meta += ["-metadata", f"comment={desc}"]

    if fmt == "circle":  # кружок Telegram: квадрат 384x384, до 60 с, обложка крутится
        cmd = ["-y", "-t", "60", "-i", src]
        if cover:
            cmd += ["-loop", "1", "-framerate", "20", "-i", cover]
            # обложка увеличена, чтобы при вращении в круге не было чёрных углов; оборот за 8 секунд
            vf = "scale=560:560,rotate=a='2*PI*t/8':ow=384:oh=384:c=black,format=yuv420p"
        else:
            cmd += ["-f", "lavfi", "-i", "color=c=0x1c1c1e:s=384x384:r=20"]
            vf = "format=yuv420p"
        cmd += [
            "-map", "0:a:0", "-map", "1:v:0", "-vf", vf, "-af", af,
            "-c:v", "libx264", "-preset", "superfast", "-crf", "27", "-r", "20",
            "-c:a", "aac", "-b:a", "128k", "-ar", "44100", "-ac", "2",
            "-shortest", "-t", "60", "-movflags", "+faststart", str(out),
        ]
        await _run(*cmd)
        return out

    if fmt == "mp4":  # видео: обложка (или чёрный фон) + звук
        cmd = ["-y", "-i", src]
        if cover:
            cmd += ["-loop", "1", "-framerate", "2", "-i", cover]
        else:
            cmd += ["-f", "lavfi", "-i", "color=c=black:s=720x720:r=2"]
        cmd += [
            "-map", "0:a:0", "-map", "1:v:0",
            "-vf", "scale=720:720:force_original_aspect_ratio=decrease,"
                   "pad=720:720:(ow-iw)/2:(oh-ih)/2,format=yuv420p",
            "-c:v", "libx264", "-tune", "stillimage", "-preset", "veryfast", "-r", "2",
            "-af", af, "-c:a", "aac", "-b:a", "192k", "-ar", "44100", "-ac", "2",
            "-shortest", "-movflags", "+faststart", *meta, str(out),
        ]
        await _run(*cmd)
        return out

    cmd = ["-y", "-i", src]
    if cover and fmt in ("mp3", "m4a", "flac"):
        cmd += ["-i", cover, "-map", "0:a:0", "-map", "1:v:0", "-c:v", "copy"]
        if fmt == "mp3":
            cmd += ["-id3v2_version", "3", "-metadata:s:v", "title=Cover",
                    "-metadata:s:v", "comment=Cover (front)"]
        else:
            cmd += ["-disposition:v:0", "attached_pic"]
    else:
        cmd += ["-map", "0:a:0"]
    cmd += ["-af", af]
    codec = {
        "mp3": ["-ar", "44100", "-ac", "2", "-c:a", "libmp3lame", "-b:a", "192k"],
        "m4a": ["-ar", "44100", "-ac", "2", "-c:a", "aac", "-b:a", "192k"],
        "ogg": ["-ar", "44100", "-ac", "2", "-c:a", "libvorbis", "-q:a", "5"],
        "flac": ["-ar", "44100", "-ac", "2", "-c:a", "flac", "-sample_fmt", "s16"],
        "wav": ["-ar", "44100", "-ac", "2", "-c:a", "pcm_s16le"],
        "voice": ["-ar", "48000", "-ac", "1", "-c:a", "libopus", "-b:a", "64k"],
    }[fmt]
    await _run(*cmd, *codec, *meta, str(out))
    return out
