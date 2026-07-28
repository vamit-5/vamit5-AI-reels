"""
Sastavlja finalni Reels klip:
1. Odredjuje trajanje audio naracije
2. Ako je video kraci od audija -- petlja (loop) video da pokrije ceo audio
   Ako je video duzi -- sece na duzinu audija
3. Nalepljuje caption (donji deo kadra) preko Pillow-a kao providan PNG
   (identican pristup kao u postojecoj automatizaciji, radi pouzdano i
   za emoji i za nase ascii/latinicno pismo)
4. Overlay PNG + audio spaja preko ffmpeg-a, skalira na max 1080px
   (visina za 9:16 Reels format), izlaz H.264/AAC mp4
"""
import json
import os
import subprocess

from PIL import Image, ImageDraw, ImageFont

WIDTH, HEIGHT = 1080, 1920
FONT_PATH = os.environ.get("CAPTION_FONT_PATH", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf")
LOGO_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets", "vamit5_logo.png")


def _ffprobe_duration(path: str) -> float:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "json", path],
        capture_output=True, text=True, check=True,
    )
    return float(json.loads(out.stdout)["format"]["duration"])


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


def _make_caption_overlay(caption_text: str, time_point_label: str, out_png: str):
    img = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    label_font = ImageFont.truetype(FONT_PATH, 54)
    body_font = ImageFont.truetype(FONT_PATH, 46)

    # gornja traka - HOOK (VAMIT-5 vojno-zelena), wrap na vise linija po potrebi
    hook_lines = _wrap_text(draw, time_point_label.upper(), label_font, WIDTH - 100)
    hook_line_height = 66
    hook_block_height = hook_line_height * len(hook_lines) + 40
    draw.rectangle([(0, 90), (WIDTH, 90 + hook_block_height)], fill=(20, 20, 20, 190))
    y = 90 + 20
    for line in hook_lines:
        lw = draw.textlength(line, font=label_font)
        draw.text(((WIDTH - lw) / 2, y), line, font=label_font, fill=(120, 200, 120, 255))
        y += hook_line_height

    # donji caption, wrap na vise linija, sa tamnom pozadinom za citljivost
    lines = _wrap_text(draw, caption_text, body_font, WIDTH - 140)
    line_height = 62
    block_height = line_height * len(lines) + 60
    top = HEIGHT - block_height - 260
    draw.rectangle([(0, top - 30), (WIDTH, top + block_height)], fill=(0, 0, 0, 170))
    y = top
    for line in lines:
        lw = draw.textlength(line, font=body_font)
        draw.text(((WIDTH - lw) / 2, y), line, font=body_font, fill=(255, 255, 255, 255))
        y += line_height

    if os.path.exists(LOGO_PATH):
        logo = Image.open(LOGO_PATH).convert("RGBA")
        logo.thumbnail((260, 260))
        img.alpha_composite(logo, (WIDTH - logo.width - 40, HEIGHT - logo.height - 60))

    img.save(out_png)
    return out_png


def assemble(raw_video_path: str, audio_path: str, caption_text: str,
             time_point_label: str, out_path: str, tmp_dir: str) -> str:
    audio_dur = _ffprobe_duration(audio_path)
    video_dur = _ffprobe_duration(raw_video_path)

    looped_video = os.path.join(tmp_dir, "looped.mp4")
    loops_needed = max(1, int(audio_dur // video_dur) + 1)
    subprocess.run(
        ["ffmpeg", "-y", "-stream_loop", str(loops_needed - 1), "-i", raw_video_path,
         "-t", str(audio_dur + 0.5), "-an", "-c:v", "libx264", "-preset", "veryfast",
         looped_video],
        check=True, capture_output=True,
    )

    overlay_png = os.path.join(tmp_dir, "overlay.png")
    _make_caption_overlay(caption_text, time_point_label, overlay_png)

    subprocess.run(
        [
            "ffmpeg", "-y",
            "-i", looped_video,
            "-i", overlay_png,
            "-i", audio_path,
            "-filter_complex",
            f"[0:v]scale={WIDTH}:{HEIGHT}:force_original_aspect_ratio=increase,"
            f"crop={WIDTH}:{HEIGHT}[base];[base][1:v]overlay=0:0[outv]",
            "-map", "[outv]", "-map", "2:a",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
            "-c:a", "aac", "-b:a", "160k",
            "-shortest",
            out_path,
        ],
        check=True, capture_output=True,
    )
    return out_path
