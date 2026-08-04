"""
Montaza za "volumen" reels tok -- BEZ ElevenLabs glasa (nema naracije).
Samo: original snimak (mutiran ili ne, zavisno od foldera) + opciono
pozadinska muzika + opciono kratak staticni tekst (jedan od 8, ceo trajanje
videa), pozicioniran ISPOD sredine kadra, ne prevelik, crna providna
pozadina, belo slovo.
"""
import json
import os
import subprocess
import urllib.request

from PIL import Image, ImageDraw, ImageFont

WIDTH, HEIGHT = 1080, 1920
FONT_PATH = os.environ.get("CAPTION_FONT_PATH", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf")

LOGO_IMAGE_URL = "https://res.cloudinary.com/dqqljgtna/image/upload/v1778767942/VAMIT-5-removebg-preview_2_uvii77.png"
LOGO_WIDTH = 150
MUSIC_VOLUME = 0.18


def _ffprobe_duration(path: str) -> float:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "json", path],
        capture_output=True, text=True, check=True,
    )
    return float(json.loads(out.stdout)["format"]["duration"])


def _fetch_image(url: str, out_path: str, target_width: int):
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=30) as resp, open(out_path, "wb") as f:
            f.write(resp.read())
        img = Image.open(out_path).convert("RGBA")
        ratio = target_width / img.width
        img = img.resize((target_width, int(img.height * ratio)))
        img.save(out_path)
        return out_path
    except Exception:
        return None


def _wrap_text(draw, text, font, max_width):
    words = text.split()
    lines, current = [], ""
    for w in words:
        trial = (current + " " + w).strip()
        if draw.textlength(trial, font=font) <= max_width:
            current = trial
        else:
            if current:
                lines.append(current)
            current = w
    if current:
        lines.append(current)
    return lines


def _make_caption_overlay(caption_text: str, out_png: str):
    img = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    font = ImageFont.truetype(FONT_PATH, 46)

    max_text_width = WIDTH - 160
    lines = _wrap_text(draw, caption_text, font, max_text_width)

    line_height = 58
    pad_x, pad_y = 36, 28
    block_h = line_height * len(lines) + pad_y * 2
    block_w = min(WIDTH - 100, max(draw.textlength(l, font=font) for l in lines) + pad_x * 2)

    # ispod sredine, ali ne prenisko (ostavlja prostor za IG dugmice/caption)
    top = int(HEIGHT * 0.58)
    left = (WIDTH - block_w) // 2

    draw.rectangle([left, top, left + block_w, top + block_h], fill=(0, 0, 0, 165))

    y = top + pad_y
    for line in lines:
        lw = draw.textlength(line, font=font)
        x = left + (block_w - lw) / 2
        draw.text((x, y), line, font=font, fill=(255, 255, 255, 255))
        y += line_height

    img.save(out_png)
    return out_png


def assemble_volume(raw_video_path: str, mode: str, music_raw_path: str | None,
                     caption_text: str | None, out_path: str, tmp_dir: str) -> str:
    video_dur = _ffprobe_duration(raw_video_path)

    inputs = ["-i", raw_video_path]
    idx = 1
    caption_idx = logo_idx = music_idx = None

    if caption_text:
        caption_png = _make_caption_overlay(caption_text, os.path.join(tmp_dir, "caption.png"))
        inputs += ["-i", caption_png]
        caption_idx = idx
        idx += 1

    logo_path = _fetch_image(LOGO_IMAGE_URL, os.path.join(tmp_dir, "logo.png"), LOGO_WIDTH)
    if logo_path:
        inputs += ["-i", logo_path]
        logo_idx = idx
        idx += 1

    if music_raw_path:
        music_dur_raw = _ffprobe_duration(music_raw_path)
        loops = max(1, int(video_dur // music_dur_raw) + 1)
        music_looped = os.path.join(tmp_dir, "music_looped.m4a")
        subprocess.run(
            ["ffmpeg", "-y", "-stream_loop", str(loops - 1), "-i", music_raw_path,
             "-t", str(video_dur), "-c:a", "aac", "-b:a", "192k", music_looped],
            check=True, capture_output=True,
        )
        inputs += ["-i", music_looped]
        music_idx = idx
        idx += 1

    filter_parts = [
        f"[0:v]scale={WIDTH}:{HEIGHT}:force_original_aspect_ratio=increase,"
        f"crop={WIDTH}:{HEIGHT}[base]",
    ]
    last_v = "base"

    if caption_idx is not None:
        filter_parts.append(f"[{last_v}][{caption_idx}:v]overlay=0:0[vcap]")
        last_v = "vcap"
    if logo_idx is not None:
        filter_parts.append(f"[{last_v}][{logo_idx}:v]overlay=30:50[vlogo]")
        last_v = "vlogo"
    filter_parts.append(f"[{last_v}]null[vout]")

    # audio: MUTE_MUSIC_TEXT i MUTE_MUSIC_NOTEXT -- iskljuci original, koristi
    # muziku. KEEP_TEXT -- zadrzi original zvuk, bez muzike.
    if mode in ("mute_music_text", "mute_music_notext"):
        if music_idx is not None:
            audio_map = f"{music_idx}:a"
        else:
            audio_map = None  # nema muzike na raspolaganju -- ostace bez zvuka
    else:  # keep_text
        audio_map = "0:a"

    filter_complex = ";".join(filter_parts)
    cmd = ["ffmpeg", "-y", *inputs, "-filter_complex", filter_complex,
           "-map", "[vout]"]
    if audio_map:
        cmd += ["-map", audio_map]
    cmd += ["-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
            "-c:a", "aac", "-b:a", "160k", "-t", str(video_dur), out_path]

    subprocess.run(cmd, check=True, capture_output=True)
    return out_path
